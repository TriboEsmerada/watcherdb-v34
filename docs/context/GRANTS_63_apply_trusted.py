"""GRANTS nas 63 instancias com a identidade AD do owner (Trusted_Connection).

[WAIVER aplicado 2026-09-08 13:05 | regra: Regra de Ouro #2 | scope: este script, uma unica vez]
Handshake CLAUDE.md cumprido (challenge/response exactos). Este ficheiro e' a EXCEPCAO autorizada:
liga por Trusted_Connection (identidade de quem o corre) para executar DDL de permissoes que so'
um administrador pode dar. NAO reutilizar para consultas de monitorizacao -- essas sao do sql_monitoring.

O que faz:
  - le config/servers.json (63 entradas enabled), constroi o alvo host\\instancia ou host,porta;
  - liga a cada instancia (master) com Trusted_Connection, autocommit;
  - executa docs/context/GRANTS_SQL_MONITORING_MULTI_SERVER.sql em lotes separados por GO;
    se o 1.o lote falhar (login sql_monitoring ausente) salta os restantes nessa instancia;
  - guarda a linha de verificacao final (EXECUTE AS sql_monitoring) por instancia;
  - --dry-run: liga e corre SO' o ultimo lote (verificacao, sem GRANTs) -- usar primeiro.

Saida: %TEMP%\\grants_63_<data>_<hora>.csv (contem hostnames: fica FORA do repo). Na consola so'
instancia_id (sha256[:8]) + resultado. Rollback por instancia: REVOKE das permissoes do SQL /
ALTER ROLE SQLAgentReaderRole DROP MEMBER [sql_monitoring].

Uso (raiz do repo, shell com a tua sessao AD):
  py docs/context/GRANTS_63_apply_trusted.py --dry-run          # conectividade + estado actual
  py docs/context/GRANTS_63_apply_trusted.py --limit 3          # 3 instancias a serio
  py docs/context/GRANTS_63_apply_trusted.py                    # as 63
  py scripts/qa/runtime/p2_preflight_permissoes.py              # prova final como sql_monitoring
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL_FILE = ROOT / "docs" / "context" / "GRANTS_SQL_MONITORING_MULTI_SERVER.sql"
SERVERS = ROOT / "config" / "servers.json"
DRIVER = "ODBC Driver 17 for SQL Server"


def _iid(server_id: str) -> str:
    return hashlib.sha256(server_id.upper().encode("utf-8")).hexdigest()[:8]


def _target(e: dict) -> str:
    host = (e.get("host") or "").strip()
    inst = (e.get("instance") or "").strip()
    port = e.get("port")
    if inst and inst.upper() not in ("MSSQLSERVER", "DEFAULT"):
        return f"{host}\\{inst}"
    if port and int(port) != 1433:
        return f"{host},{port}"
    return host


def _batches(sql: str) -> list[str]:
    parts = re.split(r"^\s*GO\s*$", sql, flags=re.IGNORECASE | re.MULTILINE)
    return [p.strip() for p in parts if p.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="so' a verificacao (ultimo lote), sem GRANTs")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=15)
    # Sequencia do RUNBOOK_ROLLOUT_SQL_AUTH_LEAST_PRIV_2026-08-21: canario de teste -> lotes -> producao POR ULTIMO
    ap.add_argument("--env", choices=["test", "quality", "production"], help="so' instancias deste ambiente")
    ap.add_argument("--ids", default="", help="lista de server_id separados por virgula (canario / lote)")
    args = ap.parse_args()

    import pyodbc

    sql = SQL_FILE.read_text(encoding="utf-8")
    lotes = _batches(sql)
    if len(lotes) < 3:
        print(f"ABORT: esperava >=3 lotes separados por GO em {SQL_FILE.name}, encontrei {len(lotes)}")
        return 1
    lotes_exec = [lotes[-1]] if args.dry_run else lotes

    with open(SERVERS, encoding="utf-8") as fh:
        cfg = json.load(fh)
    entradas = [e for e in cfg.get("monitored_servers", cfg.get("servers", [])) if e.get("enabled") is not False]
    if args.env:
        entradas = [e for e in entradas if str(e.get("environment") or "").lower() == args.env]
    if args.ids:
        pedidos = {s.strip().upper() for s in args.ids.split(",") if s.strip()}
        entradas = [e for e in entradas if str(e.get("id") or "").strip().upper() in pedidos]
    # ordem: test -> quality -> production (nunca producao primeiro), depois alfabetica
    ordem = {"test": 0, "quality": 1, "production": 2}
    alvos = sorted(
        {((e.get("id") or "").strip(), _target(e), str(e.get("environment") or "")) for e in entradas if e.get("id") and _target(e)},
        key=lambda t: (ordem.get(t[2].lower(), 9), t[0]),
    )
    alvos = [(sid, alvo) for sid, alvo, _amb in alvos]
    if args.limit:
        alvos = alvos[: args.limit]
    if not alvos:
        print("ABORT: nenhuma instancia seleccionada (filtros --env/--ids)")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(os.environ.get("TEMP", ".")) / f"grants_63_{stamp}.csv"
    cols = ["instancia_id", "server_id", "alvo", "modo", "estado", "login_efectivo", "sysadmin", "view_server_state",
            "view_any_definition", "view_any_database", "msdb_connect", "msdb_backupset", "msdb_sysjobs",
            "xp_readerrorlog", "erro"]
    rows = []
    modo = "dry-run" if args.dry_run else "grants"
    print(f"[WAIVER 2026-09-08 | Regra de Ouro #2 | {modo}] {len(alvos)} instancias, {len(lotes_exec)} lote(s) cada; identidade = sessao AD actual")

    for sid, alvo in alvos:
        iid = _iid(sid)
        row = {c: "" for c in cols}
        row.update(instancia_id=iid, server_id=sid, alvo=alvo, modo=modo)
        conn_str = (f"DRIVER={{{DRIVER}}};SERVER={alvo};DATABASE=master;Trusted_Connection=yes;"
                    f"TrustServerCertificate=yes;Connection Timeout={args.timeout};APP=WatcherDB-GRANTS-63")
        try:
            conn = pyodbc.connect(conn_str, autocommit=True, timeout=args.timeout)
            conn.timeout = args.timeout
            cur = conn.cursor()
            estado = "ok"
            for i, lote in enumerate(lotes_exec):
                try:
                    cur.execute(lote)
                    # o lote de verificacao tem USE/EXECUTE AS antes do SELECT: o 1.o result set pode
                    # vir vazio -> percorrer todos os result sets e capturar o que tiver colunas
                    while True:
                        if cur.description:
                            r1 = cur.fetchone()
                            if r1 is not None:
                                vals = dict(zip([d[0] for d in cur.description], r1))
                                for k, v in vals.items():
                                    if k in row:
                                        row[k] = "" if v is None else v
                        if not cur.nextset():
                            break
                except Exception as e:
                    msg = str(e)
                    if "login NAO existe" in msg or "nao existe nesta instancia" in msg:
                        estado = "login_ausente"
                    else:
                        estado = f"erro_lote_{i + 1}"
                    row["erro"] = msg[:200].replace("\n", " ")
                    break
            cur.close()
            conn.close()
            row["estado"] = estado
        except Exception as e:
            row["estado"] = "erro_ligacao"
            row["erro"] = str(e)[:200].replace("\n", " ")
        rows.append(row)
        ok = row["estado"] == "ok"
        print(f"{iid}  {row['estado']:14}  login={row['login_efectivo'] or '-'}  sysadmin={row['sysadmin']}  "
              f"vss={row['view_server_state']} vad={row['view_any_definition']} vadb={row['view_any_database']}  "
              f"msdb={row['msdb_connect']}/{row['msdb_backupset']}/{row['msdb_sysjobs']}  xp={row['xp_readerrorlog']}"
              + ("" if ok else f"  {row['erro'][:90]}"))

    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    okc = sum(1 for r in rows if r["estado"] == "ok")
    tudo1 = sum(1 for r in rows if r["estado"] == "ok" and all(str(r[c]) == "1" for c in cols[7:14]) and str(r["sysadmin"]) == "0")
    print(f"\n{n} instancias: {okc} ok, {n - okc} com erro; {tudo1} com as 7 verificacoes a 1 e sysadmin=0")
    print(f"CSV (com hostnames, fora do repo): {out}")
    return 0 if okc == n else 2


if __name__ == "__main__":
    sys.exit(main())
