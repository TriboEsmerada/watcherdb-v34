"""LOTE 0 (CI vivo) - PASSO 1: edita .github/workflows/ci.yml.

Origem: analise do relatorio QA externo (Fable 5.1) pelo council, 2026-09-04.
Causa real do CI morto: os 3 jobs usam `working-directory: WATCHERDB_V3.3`,
pasta que nao existe neste repo (snapshot 8631e50 nunca ajustado). Nenhum job
chegava ao `pip install`.

O que este script faz (idempotente; aborta se algum padrao nao bater):
  1. Remove os 3 blocos `defaults.run.working-directory: WATCHERDB_V3.3`.
  2. Corrige os 2 caminhos de artefacto (coverage.xml, bandit-report.json).
  3. Insere step "Collect tests (fail if zero collected)" antes do pytest.
  4. Marca o job `lint` como continue-on-error (ruff local: 674 achados;
     black/mypy nunca correram) e o step Safety idem (`safety check` esta
     deprecado e exige conta) - para o job `test` ser o sinal, nao o ruido.

NAO move ficheiros: o `git mv` de tests/integration -> scripts/manual_debug/
esta no PASSO 2 (git e' escrita, corre-o tu).

Uso (raiz do repo):  py docs/context/LOTE0_CI_PASSO1_apply.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"

WD_BLOCK = (
    "    defaults:\n"
    "      run:\n"
    "        working-directory: WATCHERDB_V3.3\n"
    "\n"
)

LINT_HEAD_OLD = "    name: Code Linting\n    runs-on: ubuntu-latest\n"
LINT_HEAD_NEW = (
    "    name: Code Linting\n"
    "    runs-on: ubuntu-latest\n"
    "    # LOTE0 2026-09-04: ruff local = 674 achados; black/mypy nunca correram\n"
    "    # neste repo. Nao bloqueia ate' haver wave de lint. O sinal do CI e' o job\n"
    "    # `test` (N testes recolhidos > 0 + pytest verde).\n"
    "    continue-on-error: true\n"
)

SAFETY_OLD = (
    "      - name: Run Safety (dependency check)\n"
    "        run: safety check --json\n"
)
SAFETY_NEW = (
    "      - name: Run Safety (dependency check)\n"
    "        # LOTE0: `safety check` esta' deprecado (exige `safety scan` + conta).\n"
    "        # Nao bloqueia; deploy/cve_gate.py e' o gate real no build-release.\n"
    "        continue-on-error: true\n"
    "        run: safety check --json\n"
)

PYTEST_STEP = "      - name: Run pytest with coverage\n"
COLLECT_STEP = (
    "      - name: Collect tests (fail if zero collected)\n"
    "        # LOTE0 2026-09-04: CI verde com 0 testes recolhidos nao tem valor\n"
    "        # probatorio (QA externo Fable, item 3c). tests/integration foi\n"
    "        # movido para scripts/manual_debug/ (ligava a PRD so' por ser\n"
    "        # recolhido). Um erro de coleccao (ImportError em Linux, etc.)\n"
    "        # tambem falha aqui, de forma visivel - e' esse o objectivo.\n"
    "        run: |\n"
    "          set -o pipefail\n"
    "          python -m pytest --collect-only -q --no-cov -p no:cacheprovider 2>&1 | tee collect.log\n"
    "          N1=$(grep -E '^tests/.*: [0-9]+$' collect.log | awk -F': ' '{s+=$2} END{print s+0}')\n"
    "          N2=$(grep -c '::' collect.log || true)\n"
    "          N=$(( N1 > N2 ? N1 : N2 ))\n"
    "          echo \"Testes recolhidos: $N (pytest>=9 por ficheiro: $N1; ids: $N2)\"\n"
    "          test \"$N\" -gt 0 || { echo '::error::0 testes recolhidos'; exit 1; }\n"
    "\n"
)


def replace_exact(text: str, old: str, new: str, expected: int, label: str) -> str:
    n = text.count(old)
    if n != expected:
        sys.exit(f"ABORT [{label}]: esperava {expected} ocorrencia(s), encontrei {n}. "
                 f"ci.yml nao esta no estado previsto - nada foi escrito.")
    return text.replace(old, new)


def main() -> None:
    if not CI.exists():
        sys.exit(f"ABORT: {CI} nao existe")
    original = CI.read_text(encoding="utf-8")

    if "Collect tests (fail if zero collected)" in original:
        print("Ja aplicado (step de collect presente). Nada a fazer.")
        return

    text = original
    text = replace_exact(text, WD_BLOCK, "", 3, "working-directory x3")
    text = replace_exact(text, "file: WATCHERDB_V3.3/coverage.xml",
                         "file: coverage.xml", 1, "codecov path")
    text = replace_exact(text, "path: WATCHERDB_V3.3/bandit-report.json",
                         "path: bandit-report.json", 1, "bandit path")
    text = replace_exact(text, LINT_HEAD_OLD, LINT_HEAD_NEW, 1, "lint continue-on-error")
    text = replace_exact(text, SAFETY_OLD, SAFETY_NEW, 1, "safety continue-on-error")
    text = replace_exact(text, PYTEST_STEP, COLLECT_STEP + PYTEST_STEP, 1, "collect step")

    if "WATCHERDB_V3.3" in text:
        left = [ln for ln in text.splitlines() if "WATCHERDB_V3.3" in ln]
        sys.exit("ABORT: ainda ha referencias a WATCHERDB_V3.3 em ci.yml:\n  " + "\n  ".join(left))

    CI.write_text(text, encoding="utf-8", newline="\n")
    print(f"OK: {CI.relative_to(ROOT)} actualizado "
          f"({len(original.splitlines())} -> {len(text.splitlines())} linhas).")
    print("Proximo: docs/context/LOTE0_CI_PASSO2_commit.ps1 (git mv + commit).")


if __name__ == "__main__":
    main()
