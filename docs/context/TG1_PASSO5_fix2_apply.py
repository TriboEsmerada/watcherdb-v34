"""TestGrapete TG-1 - PASSO 5: verde vazio nao e' verde (2.a corrida, 2026-09-09).

O que a 2.a corrida mostrou:
  1. 51/51 casos SALTADOS (sem credenciais em .env.qa) e o job devolveu exit 0.
     Um smoke que nao mede nada nao pode ser verde: e' o mesmo defeito do
     "0 testes recolhidos" do Lote 0, noutra forma.
  2. A linha do NIGHTLY_LOG dizia "5 casos, 4 avisos": eram os JSON da 1.a
     corrida, na mesma pasta do dia. As evidencias do council acumulavam.

Correccoes:
  - nightly: limpa council/cases/ no inicio de cada corrida.
  - nightly: se 0 JSON de caso no fim -> exit 2 ("nada medido") mesmo com pytest 0;
    a linha do log diz SALTADOS quando o pytest.log so' tem 's'.
  - board: corrida sem casos do council = estado cinzento (nao verde nem ambar).

Uso (raiz do repo):  py docs/context/TG1_PASSO5_fix2_apply.py
Depois:              pwsh docs/context/TG1_PASSO6_commit.ps1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NIGHTLY = ROOT / "scripts" / "qa" / "nightly_testgrapete.ps1"
BOARD = ROOT / "scripts" / "qa" / "testgrapete_board.py"


def rep(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        sys.exit(f"ABORT [{label}]: esperava 1, encontrei {n}. Nada escrito.")
    return text.replace(old, new)


N1_OLD = "New-Item -ItemType Directory -Force -Path $council, $externo, (Join-Path $council 'cases') | Out-Null\n"
N1_NEW = (
    "New-Item -ItemType Directory -Force -Path $council, $externo, (Join-Path $council 'cases') | Out-Null\n"
    "# TG-1 PASSO 5: cada corrida comeca sem JSON de caso da anterior (na 2.a corrida o sumario\n"
    "# contou os 5 casos da 1.a). Screenshots/traces ficam (so' existem em falha).\n"
    "Get-ChildItem (Join-Path $council 'cases') -Filter '*.json' -ErrorAction SilentlyContinue | Remove-Item -Force\n"
)

N2_OLD = "$cases = Get-ChildItem (Join-Path $council 'cases') -Filter '*.json' -ErrorAction SilentlyContinue\n"
N2_NEW = (
    "$cases = Get-ChildItem (Join-Path $council 'cases') -Filter '*.json' -ErrorAction SilentlyContinue\n"
    "# TG-1 PASSO 5: verde vazio nao e' verde. Sem casos medidos (todos saltados por falta de\n"
    "# credenciais, ou coleccao vazia) o job falha com 2, mesmo que o pytest tenha devolvido 0.\n"
    "$saltados = (Select-String -Path (Join-Path $council 'pytest.log') -Pattern 'SKIPPED \\[(\\d+)\\]' -AllMatches -ErrorAction SilentlyContinue |\n"
    "    ForEach-Object { $_.Matches } | ForEach-Object { [int]$_.Groups[1].Value } | Measure-Object -Sum).Sum\n"
    "if (-not $saltados) { $saltados = 0 }\n"
    "if (@($cases).Count -eq 0) {\n"
    "    Write-Host \"COUNCIL: nada medido ($saltados casos saltados). Preenche .env.qa (WATCHERDB_QA_VIEWER/DBA/ADMIN_USER+PASS).\"\n"
    "    if ($councilExit -eq 0) { $councilExit = 2 }\n"
    "}\n"
)

N3_OLD = "$logLine = \"| $dia | $head | council exit $councilExit ($($cases.Count) casos, $falhas erro, $warns aviso) |"
N3_NEW = "$logLine = \"| $dia | $head | council exit $councilExit ($(@($cases).Count) casos, $falhas erro, $warns aviso, $saltados saltados) |"

B_OLD = "    if not casos and not ext:\n        estado = \"n\"\n"
B_NEW = (
    "    if not casos:\n"
    "        # TG-1 PASSO 5: sem casos do council a corrida nao mediu nada -> cinzento,\n"
    "        # mesmo que o externo tenha corrido.\n"
    "        estado = \"n\"\n"
)


def main() -> None:
    n = NIGHTLY.read_text(encoding="utf-8")
    if "TG-1 PASSO 5" in n:
        print("Ja aplicado: nightly")
    else:
        n = rep(n, N1_OLD, N1_NEW, "limpa cases")
        n = rep(n, N2_OLD, N2_NEW, "nada medido")
        n = rep(n, N3_OLD, N3_NEW, "logline")
        NIGHTLY.write_text(n, encoding="utf-8", newline="\n")
        print("OK: scripts/qa/nightly_testgrapete.ps1")
    b = BOARD.read_text(encoding="utf-8")
    if "TG-1 PASSO 5" in b:
        print("Ja aplicado: board")
    else:
        b = rep(b, B_OLD, B_NEW, "board estado")
        compile(b, str(BOARD), "exec")
        BOARD.write_text(b, encoding="utf-8", newline="\n")
        print("OK: scripts/qa/testgrapete_board.py")
    print("Proximo: preencher .env.qa e correr pwsh docs/context/TG1_PASSO6_commit.ps1")


if __name__ == "__main__":
    main()
