"""QA externo — pauta P2 A-2.2: comparador CSV de pre-flight vs LEAST_PRIVILEGE_SETUP.sql.

NAO liga a nenhuma base de dados. Le:
  1. docs/qa/externo/<data>-p2-preflight.csv (gerado pelo owner com scripts/qa/runtime/p2_preflight_permissoes.py)
  2. docs/security/LEAST_PRIVILEGE_SETUP.sql (fonte da verdade do que DEVE existir)
e imprime desvios por instancia (instancia_id = hash, sem hostnames).

Esperado por coluna (derivado do script SQL, TIER STANDARD):
  sysadmin=0 (P0 se 1) | view_server_state=1 (P1 se 0) | view_any_definition=1 | view_any_database=1
  msdb_connect=1 | msdb_backupset=1 | msdb_sysjobs=1 | sqlagent_reader_role=1 | xp_readerrorlog=1
  login_efectivo: o script cria/concede a `WatcherDBReader`; o servico usa `sql_monitoring`
  (config/servers.json). Divergencia de nome e' registada como aviso (o CSV nao prova que os grants
  do script foram aplicados A ESTA conta, so' que esta conta tem estes bits).

LIMITE CONHECIDO: o CSV so' tem colunas para permissoes ESPERADAS. "E nada mais" (permissoes extra,
roles extra, SHOWPLAN, VIEW SERVER SECURITY STATE, membership em db_owner/db_datawriter noutras BDs)
NAO e' mensuravel com este CSV -> o comparador imprime TESTE EM FALTA para essa metade da afirmacao
ate' o pre-flight exportar sys.server_permissions + sys.server_role_members + roles por BD.

Uso: python3 scripts/qa/runtime/qa_ext_p2_preflight_compare.py --csv docs/qa/externo/2026-09-08-p2-preflight.csv
     [--sql docs/security/LEAST_PRIVILEGE_SETUP.sql] [--allowlist-count 64]
"""
from __future__ import annotations
import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# coluna CSV -> (valor esperado, severidade se falhar, permissao/role no script que a justifica)
EXPECTED = {
    "sysadmin": ("0", "P0", "pre-condicao: 'o login criado NAO sera sysadmin' (LEAST_PRIVILEGE_SETUP.sql:15-16)"),
    "view_server_state": ("1", "P1", "GRANT VIEW SERVER STATE"),
    "view_any_definition": ("1", "P1", "GRANT VIEW ANY DEFINITION"),
    "view_any_database": ("1", "P2", "GRANT VIEW ANY DATABASE"),
    "msdb_connect": ("1", "P1", "CREATE USER ... em msdb"),
    "msdb_backupset": ("1", "P1", "GRANT SELECT ON dbo.backupset"),
    "msdb_sysjobs": ("1", "P1", "GRANT SELECT ON dbo.sysjobs"),
    "sqlagent_reader_role": ("1", "P1", "ALTER ROLE SQLAgentReaderRole ADD MEMBER"),
    "xp_readerrorlog": ("1", "P1", "GRANT EXECUTE ON sys.xp_readerrorlog"),
}
SCRIPT_LOGIN = "WatcherDBReader"
SERVICE_LOGIN = "sql_monitoring"


def grants_in_script(sql_path: Path) -> dict:
    """Extrai GRANT/ALTER ROLE nao comentados do script, por bloco USE <db>. So' para listar."""
    txt = sql_path.read_text(encoding="utf-8", errors="replace")
    txt = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)  # blocos comentados (opcoes A/B, rollback)
    db, out = "master", {}
    for line in txt.splitlines():
        s = line.split("--", 1)[0].strip()
        if not s:
            continue
        m = re.match(r"USE\s+(\w+)\s*;", s, re.I)
        if m:
            db = m.group(1)
            continue
        if re.match(r"(GRANT|ALTER ROLE)\b", s, re.I):
            out.setdefault(db, []).append(s.rstrip(";"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--sql", default=str(ROOT / "docs" / "security" / "LEAST_PRIVILEGE_SETUP.sql"))
    ap.add_argument("--allowlist-count", type=int, default=0,
                    help="n.o de instancias em config/servers.json (para detectar instancias em falta no CSV)")
    a = ap.parse_args()

    csv_path = Path(a.csv)
    if not csv_path.is_file():
        print(f"NAO VERIFICAVEL: CSV ausente ({csv_path.name})")
        return 3
    grants = grants_in_script(Path(a.sql))
    print("== o que o script concede (nao comentado) ==")
    for db, items in grants.items():
        print(f"  [{db}] " + " | ".join(items))
    print("  DENY explicitos: nenhum (o script nao tem DENY; ALTER TRACE fica comentado/opt-in)")

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8", newline="")))
    print(f"\n== CSV: {len(rows)} linha(s); colunas: {sorted(rows[0].keys()) if rows else '-'} ==")
    falta = set(EXPECTED) - set(rows[0].keys() if rows else [])
    if falta:
        print(f"  AVISO colunas esperadas em falta no CSV: {sorted(falta)}")

    p0 = p1 = p2 = 0
    for r in rows:
        iid = r.get("instancia_id", "?")
        if r.get("erro"):
            print(f"[{iid}] NAO CONTACTADA / erro: {r['erro'][:80]}  (modo={r.get('modo_configurado')})")
            continue
        login = (r.get("login_efectivo") or "").strip()
        if login and login.lower() != SERVICE_LOGIN:
            print(f"[{iid}] AVISO login_efectivo != {SERVICE_LOGIN} (o pre-flight devia ligar como a conta do servico)")
        if login.lower() == SERVICE_LOGIN:
            print(f"[{iid}] nota: script concede a {SCRIPT_LOGIN}; conta medida e' {SERVICE_LOGIN} "
                  f"(prova que ESTA conta tem os bits, nao que o script foi o que os deu)")
        for col, (exp, sev, why) in EXPECTED.items():
            got = (r.get(col) or "").strip()
            if got == "":
                print(f"[{iid}] {col}: sem valor (TESTE EM FALTA)")
                continue
            if got != exp:
                print(f"[{iid}] {sev} {col}={got} esperado={exp}  <- {why}")
                if sev == "P0":
                    p0 += 1
                elif sev == "P1":
                    p1 += 1
                else:
                    p2 += 1
    if a.allowlist_count and len(rows) != a.allowlist_count:
        print(f"\nAVISO: CSV tem {len(rows)} instancias; servers.json tem {a.allowlist_count} -> {a.allowlist_count - len(rows)} em falta")
    print(f"\nRESUMO: P0={p0} P1={p1} P2={p2}")
    print("TESTE EM FALTA: 'e nada mais' (permissoes/roles extra) nao e' mensuravel com estas colunas; "
          "o pre-flight precisa de exportar sys.server_permissions, sys.server_role_members e "
          "sys.database_role_members por BD para a conta.")
    return 0 if p0 == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
