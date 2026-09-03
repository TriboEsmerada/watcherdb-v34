"""Falha se o SBOM omitir alguma dependencia DIRECTA do lockfile.

Uso:
    python verify_sbom_coverage.py <sbom.cyclonedx.json> <requirements.lock>

Exit 0 se todas as libs do lockfile estao no SBOM; exit 1 + lista na stderr
caso contrario. E' o gate que impede o SBOM de voltar a mentir por omissao
(o de 2026-08-20 omitia o pyodbc e passava despercebido porque nada comparava
o SBOM contra o lockfile).

So' compara nomes de pacote (nao versoes): o objectivo e' garantir que nenhuma
dependencia declarada DESAPARECE do SBOM, nao auditar drift de versao (isso e'
trabalho do CVE scan a jusante).
"""

from __future__ import annotations

import json
import re
import sys


def _norm(nome: str) -> str:
    return (nome or "").strip().lower().replace("_", "-").replace(".", "-")


# Linha de requirements/lock -> nome do pacote (ignora versao, markers, extras,
# comentarios, -e, hashes, opcoes). Devolve None para linhas nao-pacote.
_PKG = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _pacotes_do_lock(path: str) -> set[str]:
    nomes: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for linha in fh:
            s = linha.strip()
            if not s or s.startswith("#") or s.startswith("-"):
                continue
            # tira extras: pkg[extra]  ->  pkg
            s = s.split("[", 1)[0]
            m = _PKG.match(s)
            if m:
                nomes.add(_norm(m.group(1)))
    return nomes


def _pacotes_do_sbom(path: str) -> set[str]:
    with open(path, encoding="utf-8") as fh:
        sbom = json.load(fh)
    return {_norm(c.get("name", "")) for c in (sbom.get("components") or [])}


def main() -> int:
    if len(sys.argv) != 3:
        print("uso: verify_sbom_coverage.py <sbom.json> <lock>", file=sys.stderr)
        return 2

    sbom_pkgs = _pacotes_do_sbom(sys.argv[1])
    lock_pkgs = _pacotes_do_lock(sys.argv[2])

    faltam = sorted(lock_pkgs - sbom_pkgs)
    if faltam:
        print(
            f"{len(faltam)} dependencia(s) do lockfile AUSENTES do SBOM "
            "(SBOM a mentir por omissao):",
            file=sys.stderr,
        )
        for nome in faltam:
            print(f"  - {nome}", file=sys.stderr)
        return 1

    print(f"OK: {len(lock_pkgs)} pacotes do lockfile, todos no SBOM.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
