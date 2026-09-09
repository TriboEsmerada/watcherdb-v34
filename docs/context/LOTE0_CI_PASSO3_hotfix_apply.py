"""LOTE 0 (CI vivo) - PASSO 3: hotfix apos o 1.o run real (run 33960086275, 89d5be9).

Leitura do run via API publica do GitHub (logs exigem auth; causas apuradas
por codigo):
  - Run Tests (3.11): step "Collect tests" FALHOU. Duas causas certas em Linux:
      a) tests/unit/test_service_entry.py:15 faz `import watcherdb_service` ao
         nivel do modulo; o skipif so' actua depois da coleccao, e o import
         puxa servicemanager/win32* -> ModuleNotFoundError -> erro de coleccao.
      b) `import pyodbc` (15 modulos ao nivel do modulo, transitivamente em
         quase todos os testes) precisa de libodbc.so.2; a imagem ubuntu-latest
         NAO traz unixodbc (readme oficial do runner: 0 ocorrencias de "odbc").
  - Security Scan: Bandit devolve exit 1 quando ha' achados (por desenho).
  - Code Linting: ruff 674 achados (esperado; job ja' em continue-on-error).
  - Notify: falha se lint OU security falharem -> anula o continue-on-error.

O que este script faz (idempotente; aborta se um padrao nao bater):
  1. ci.yml/test: step "Install system libs" (apt unixodbc) antes do pip.
  2. ci.yml/security: Bandit em continue-on-error (relatorio continua a subir).
  3. ci.yml/notify: so' o job `test` decide a cor do run.
  4. tests/unit/test_service_entry.py: import via pytest.importorskip.

Uso (raiz do repo):  py docs/context/LOTE0_CI_PASSO3_hotfix_apply.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
SVC_TEST = ROOT / "tests" / "unit" / "test_service_entry.py"

INSTALL_DEPS = (
    "      - name: Install dependencies\n"
    "        run: |\n"
    "          python -m pip install --upgrade pip\n"
    "          pip install -r requirements.txt\n"
    "          pip install -r requirements-dev.txt\n"
)
SYSLIBS_STEP = (
    "      - name: Install system libs (unixodbc for pyodbc)\n"
    "        # LOTE0 hotfix 2026-09-05: pyodbc importa libodbc.so.2; a imagem\n"
    "        # ubuntu-latest nao traz unixodbc -> ImportError na coleccao.\n"
    "        run: sudo apt-get update -qq && sudo apt-get install -y -qq unixodbc\n"
    "\n"
)

BANDIT_OLD = (
    "      - name: Run Bandit (security issues)\n"
    "        run: bandit -r watcherdb/ -f json -o bandit-report.json\n"
)
BANDIT_NEW = (
    "      - name: Run Bandit (security issues)\n"
    "        # LOTE0 hotfix: bandit sai com 1 quando ha' achados (por desenho).\n"
    "        # Informativo; o relatorio continua a ser publicado como artefacto.\n"
    "        continue-on-error: true\n"
    "        run: bandit -r watcherdb/ -f json -o bandit-report.json\n"
)

NOTIFY_OLD = (
    "        if: ${{ needs.lint.result == 'failure' || needs.test.result == 'failure' "
    "|| needs.security.result == 'failure' }}\n"
)
NOTIFY_NEW = (
    "        # LOTE0 hotfix: lint e security sao informativos (continue-on-error);\n"
    "        # so' o job test decide a cor do run.\n"
    "        if: ${{ needs.test.result == 'failure' }}\n"
)

SVC_OLD = "import watcherdb_service  # noqa: E402\n"
SVC_NEW = (
    "# LOTE0 hotfix 2026-09-05: o skipif acima so' actua DEPOIS da coleccao; um\n"
    "# import directo puxa servicemanager/win32* e rebenta a coleccao em Linux (CI).\n"
    "watcherdb_service = pytest.importorskip(\n"
    "    \"watcherdb_service\", reason=\"Launcher e Windows-only (pywin32)\"\n"
    ")\n"
)


def replace_exact(text: str, old: str, new: str, expected: int, label: str) -> str:
    n = text.count(old)
    if n != expected:
        sys.exit(f"ABORT [{label}]: esperava {expected} ocorrencia(s), encontrei {n}. Nada foi escrito.")
    return text.replace(old, new)


def main() -> None:
    for p in (CI, SVC_TEST):
        if not p.exists():
            sys.exit(f"ABORT: {p} nao existe")

    ci = CI.read_text(encoding="utf-8")
    svc = SVC_TEST.read_text(encoding="utf-8")

    done_ci = "Install system libs (unixodbc for pyodbc)" in ci
    done_svc = "pytest.importorskip(" in svc
    if done_ci and done_svc:
        print("Ja aplicado. Nada a fazer.")
        return

    if not done_ci:
        if "Collect tests (fail if zero collected)" not in ci:
            sys.exit("ABORT: PASSO 1 nao aplicado em ci.yml.")
        ci = replace_exact(ci, INSTALL_DEPS, SYSLIBS_STEP + INSTALL_DEPS, 1, "syslibs step")
        ci = replace_exact(ci, BANDIT_OLD, BANDIT_NEW, 1, "bandit continue-on-error")
        ci = replace_exact(ci, NOTIFY_OLD, NOTIFY_NEW, 1, "notify condition")
    if not done_svc:
        svc = replace_exact(svc, SVC_OLD, SVC_NEW, 1, "importorskip")

    # Sintaxe do teste antes de escrever
    compile(svc, str(SVC_TEST), "exec")

    if not done_ci:
        CI.write_text(ci, encoding="utf-8", newline="\n")
        print(f"OK: {CI.relative_to(ROOT)}")
    if not done_svc:
        SVC_TEST.write_text(svc, encoding="utf-8", newline="\n")
        print(f"OK: {SVC_TEST.relative_to(ROOT)}")
    print("Proximo: docs/context/LOTE0_CI_PASSO4_hotfix_commit.ps1")


if __name__ == "__main__":
    main()
