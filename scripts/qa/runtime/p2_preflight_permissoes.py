"""P2 pre-flight: permissoes efectivas da conta sql_monitoring em cada instancia monitorizada.

QUEM CORRE: o owner (regra 5 do projecto), na maquina onde esta o config/servers.json do servico.
IDENTIDADE: SQL Auth com as credenciais do servers.json (sql_monitoring), NUNCA Trusted_Connection --
a regra de ouro 2 proibe o utilizador de dominio de tocar em qualquer BD. Instancias sem credenciais
SQL no servers.json NAO sao contactadas: ficam registadas como "sem_credenciais_sql" (e isso e', por si,
um achado: o servico so' as consegue ler como a conta de servico Windows).
SO' LEITURA: SUSER_SNAME(), IS_SRVROLEMEMBER, HAS_PERMS_BY_NAME, IS_ROLEMEMBER. Nenhuma escrita.

SAIDA:
  docs/qa/externo/<data>-p2-preflight.csv   -> para o QA externo (instancia_id = sha256(server_id)[:8],
                                               sem hostnames; login_efectivo e' o nome da conta SQL)
  docs/context/p2_mapa_instancias_<data>.csv -> so' council/owner: instancia_id -> server_id

REFERENCIA (docs/security/LEAST_PRIVILEGE_SETUP.sql + PLANO_LEAST_PRIVILEGE_SQL_2026-08-20.md):
  server: VIEW SERVER STATE, VIEW ANY DEFINITION, VIEW ANY DATABASE; msdb: CONNECT + SELECT backupset/
  sysjobs (+ SQLAgentReaderRole); master: EXECUTE xp_readerrorlog. sysadmin NAO e' exigido por nada.

Uso (raiz do repo):  py scripts/qa/runtime/p2_preflight_permissoes.py [--limit N] [--timeout 15]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

QUERY_MASTER = """
SELECT SUSER_SNAME() AS login_efectivo,
       IS_SRVROLEMEMBER('sysadmin') AS sysadmin,
       HAS_PERMS_BY_NAME(NULL, NULL, 'VIEW SERVER STATE') AS view_server_state,
       HAS_PERMS_BY_NAME(NULL, NULL, 'VIEW ANY DEFINITION') AS view_any_definition,
       HAS_PERMS_BY_NAME(NULL, NULL, 'VIEW ANY DATABASE') AS view_any_database,
       HAS_PERMS_BY_NAME('msdb', 'DATABASE', 'CONNECT') AS msdb_connect,
       HAS_PERMS_BY_NAME('msdb.dbo.backupset', 'OBJECT', 'SELECT') AS msdb_backupset,
       HAS_PERMS_BY_NAME('msdb.dbo.sysjobs', 'OBJECT', 'SELECT') AS msdb_sysjobs,
       HAS_PERMS_BY_NAME('master.dbo.xp_readerrorlog', 'OBJECT', 'EXECUTE') AS xp_readerrorlog,
       CAST(SERVERPROPERTY('ProductMajorVersion') AS INT) AS sql_major
"""
QUERY_MSDB = "SELECT IS_ROLEMEMBER('SQLAgentReaderRole') AS sqlagent_reader_role"

COLS = [
    "instancia_id", "ambiente", "modo_configurado", "login_efectivo", "sysadmin", "view_server_state",
    "view_any_definition", "view_any_database", "msdb_connect", "msdb_backupset", "msdb_sysjobs",
    "sqlagent_reader_role", "xp_readerrorlog", "sql_major", "erro", "ms",
]


def _iid(server_id: str) -> str:
    return hashlib.sha256(server_id.upper().encode("utf-8")).hexdigest()[:8]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="so' as N primeiras instancias (teste)")
    ap.add_argument("--timeout", type=int, default=15, help="login + command timeout em segundos")
    args = ap.parse_args()

    # O servico carrega o .env "3-tier" (WATCHERDB_DATA_DIR/.env -> ProgramData (frozen) -> raiz do repo)
    # ANTES de qualquer import (watcherdb_main.py:16-42). Sem isto a chave mestra (WATCHERDB_ENCRYPTION_KEY
    # ou _DPAPI) nao existe neste processo e as passwords do servers.json ficam cifradas.
    try:
        from dotenv import load_dotenv

        _cands = []
        _wdd = __import__("os").environ.get("WATCHERDB_DATA_DIR")
        if _wdd:
            _cands.append(Path(_wdd) / ".env")
        # ordem do servico em dev (nao-frozen): WATCHERDB_DATA_DIR, depois a raiz do repo;
        # ProgramData so' conta no bundle congelado -- fica em ultimo como fallback
        _cands.append(ROOT / ".env")
        _cands.append(Path(r"C:\ProgramData\WatcherDB") / ".env")
        for _c in _cands:
            if _c.exists():
                load_dotenv(_c)
                print(f"[env] carregado: {_c}")
                break
        else:
            print("[env] nenhum .env encontrado (WATCHERDB_DATA_DIR / ProgramData / raiz) -- a chave mestra tem de vir do ambiente")
    except ImportError:
        print("[env] python-dotenv indisponivel -- a chave mestra tem de vir do ambiente")

    import pyodbc  # noqa: WPS433 -- o mesmo driver do servico
    from api.connection_pool import get_sql_server_pool

    pool = get_sql_server_pool()
    pool._load_credentials_cache()
    # Iterar as ENTRADAS do servers.json (63), nao as chaves do cache do pool: o cache indexa cada
    # servidor duas vezes (id e host) -> 118 chaves e cada instancia contactada em duplicado.
    import json

    with open(pool._creds_cache_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    entradas = [e for e in cfg.get("monitored_servers", cfg.get("servers", [])) if e.get("enabled") is not False]
    ambiente = {}
    server_ids = []
    for e in entradas:
        sid = (e.get("id") or e.get("server_id") or "").strip()
        if sid:
            server_ids.append(sid)
            ambiente[sid] = str(e.get("environment") or "")
    server_ids = sorted(set(server_ids))
    if args.limit:
        server_ids = server_ids[: args.limit]
    if not server_ids:
        print("ABORT: servers.json sem instancias (ou nao encontrado em", pool._creds_cache_path, ")")
        return 1

    # Guarda (2026-09-08): sem a chave mestra neste processo, as passwords ficam "encrypted:..." e o
    # script faria 63 logins falhados com um literal cifrado. Aborta ANTES de tocar em qualquer instancia.
    cifradas = [s for s in server_ids if str((pool._resolve_credentials(s) or {}).get("password") or "").startswith("encrypted:")]
    if cifradas:
        print(f"ABORT: {len(cifradas)}/{len(server_ids)} passwords continuam cifradas -- a chave mestra nao esta "
              f"disponivel neste processo (services.secrets.try_get_master_key() devolveu vazio).")
        print("       Corre na shell onde a chave resolve (ver services/secrets.py: ficheiro DPAPI machine-scope,")
        print("       env DPAPI user-scope ou chave em claro) ou com a identidade do servico. Nenhuma instancia foi contactada.")
        return 2

    data = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_qa = ROOT / "docs" / "qa" / "externo" / f"{data}-p2-preflight.csv"
    out_map = ROOT / "docs" / "context" / f"p2_mapa_instancias_{data}.csv"
    out_qa.parent.mkdir(parents=True, exist_ok=True)

    rows, mapa = [], []
    for sid in server_ids:
        iid = _iid(sid)
        mapa.append({"instancia_id": iid, "server_id": sid})
        creds = pool._resolve_credentials(sid) or {}
        modo = "sql_auth_allowlist" if pool._sql_auth_enabled_for(sid) else (
            "windows_auth_config" if creds.get("use_windows_auth", True) else "sql_auth_config")
        row = {c: "" for c in COLS}
        row.update(instancia_id=iid, ambiente=ambiente.get(sid, ""), modo_configurado=modo)
        conn_str = pool._build_connection_string_sql_auth(sid, "master")
        if not conn_str:
            row["erro"] = "sem_credenciais_sql"  # nao contactada: seria Trusted_Connection do owner
            rows.append(row)
            print(f"{iid}  {modo:22}  SEM CREDENCIAIS SQL -> nao contactada")
            continue
        t0 = datetime.now()
        try:
            conn = pyodbc.connect(conn_str, timeout=args.timeout)
            conn.timeout = args.timeout
            cur = conn.cursor()
            cur.execute(QUERY_MASTER)
            cols = [d[0] for d in cur.description]
            vals = dict(zip(cols, cur.fetchone()))
            for k, v in vals.items():
                row[k] = "" if v is None else v
            try:
                cur.execute("USE msdb;")
                cur.execute(QUERY_MSDB)
                r2 = cur.fetchone()
                row["sqlagent_reader_role"] = "" if r2 is None or r2[0] is None else r2[0]
            except Exception as e2:
                row["sqlagent_reader_role"] = f"erro:{str(e2)[:40]}"
            cur.close()
            conn.close()
        except Exception as e:
            row["erro"] = str(e)[:160].replace("\n", " ")
        row["ms"] = int((datetime.now() - t0).total_seconds() * 1000)
        rows.append(row)
        flag = "OK" if not row["erro"] else "ERRO"
        print(f"{iid}  {modo:22}  {flag:4}  login={row['login_efectivo'] or '-'}  sysadmin={row['sysadmin']}  "
              f"vss={row['view_server_state']}  vad={row['view_any_definition']}  msdb={row['msdb_connect']}/{row['msdb_backupset']}/{row['msdb_sysjobs']}  "
              f"agent={row['sqlagent_reader_role']}  xp={row['xp_readerrorlog']}  {row['ms']}ms  {row['erro']}")

    with out_qa.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    with out_map.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["instancia_id", "server_id"])
        w.writeheader()
        w.writerows(mapa)

    n = len(rows)
    ok = sum(1 for r in rows if not r["erro"])
    sem = sum(1 for r in rows if r["erro"] == "sem_credenciais_sql")
    sysadm = sum(1 for r in rows if str(r["sysadmin"]) == "1")
    falta_vss = sum(1 for r in rows if not r["erro"] and str(r["view_server_state"]) != "1")
    print(f"\n{n} instancias: {ok} lidas, {sem} sem credenciais SQL, {n - ok - sem} com erro de ligacao; "
          f"sysadmin={sysadm}; sem VIEW SERVER STATE={falta_vss}")
    print(f"CSV para o QA:   {out_qa}")
    print(f"Mapa (council):  {out_map}  <- NAO partilhar com o QA externo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
