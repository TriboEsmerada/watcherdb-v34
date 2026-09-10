"""TestGrapete TG-1 - PASSO 7: o job deriva WATCHERDB_QA_URL e o modelo do .env.qa
inclui as variaveis do qa-externo (3.a corrida, 2026-09-09: .env.qa nao existia;
as corridas 1-2 viviam de variaveis da shell anterior; os qa_ext_*.py leem
WATCHERDB_QA_URL/USER/PASS, que o job nao derivava -> 5/5 KeyError em 6 s).

Uso (raiz do repo):  py docs/context/TG1_PASSO7_envqa_apply.py
Depois: criar .env.qa (modelo abaixo) e correr pwsh docs/context/TG1_PASSO6_commit.ps1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NIGHTLY = ROOT / "scripts" / "qa" / "nightly_testgrapete.ps1"

OLD_HDR = """#   WATCHERDB_QA_SERVER=<nome ou server_id de um TST>
"""
NEW_HDR = """#   WATCHERDB_QA_SERVER=<nome ou server_id de um TST>
#   # qa-externo (scripts/qa/runtime/qa_ext_*.py): conta unica + URL proprio
#   WATCHERDB_QA_USER=qa_viewer
#   WATCHERDB_QA_PASS=...
#   WATCHERDB_QA_ROLE=viewer
#   # WATCHERDB_QA_URL e' derivado de WATCHERDB_BASE_URL se faltar
"""

OLD_URL = """if (-not $env:WATCHERDB_BASE_URL) { $env:WATCHERDB_BASE_URL = 'https://localhost:8434' }
"""
NEW_URL = """if (-not $env:WATCHERDB_BASE_URL) { $env:WATCHERDB_BASE_URL = 'https://localhost:8434' }
# TG-1 PASSO 7: os scripts do qa-externo leem WATCHERDB_QA_URL (convencao deles, intocada)
if (-not $env:WATCHERDB_QA_URL) { $env:WATCHERDB_QA_URL = $env:WATCHERDB_BASE_URL }
if (-not (Test-Path $envFile)) { Write-Host "AVISO: $envFile nao existe; a usar so' o ambiente da shell (ver cabecalho deste script)." }
"""


def rep(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        sys.exit(f"ABORT [{label}]: esperava 1, encontrei {n}. Nada escrito.")
    return text.replace(old, new)


def main() -> None:
    n = NIGHTLY.read_text(encoding="utf-8")
    if "TG-1 PASSO 7" in n:
        print("Ja aplicado.")
        return
    n = rep(n, OLD_HDR, NEW_HDR, "cabecalho")
    n = rep(n, OLD_URL, NEW_URL, "url")
    NIGHTLY.write_text(n, encoding="utf-8", newline="\n")
    print("OK: scripts/qa/nightly_testgrapete.ps1 (WATCHERDB_QA_URL derivado + aviso sem .env.qa)")
    print("Proximo: criar .env.qa na raiz e correr pwsh docs/context/TG1_PASSO6_commit.ps1")


if __name__ == "__main__":
    main()
