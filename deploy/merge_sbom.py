"""Funde o SBOM do Syft (bundle) com o do environment filtrado ao runtime.

Uso:
    python merge_sbom.py <syft_sbom.json> <env_sbom.json> <requirements.txt>

Escreve o resultado de VOLTA no primeiro argumento (o SBOM do Syft, no sitio
que o resto do pipeline espera) e imprime o path na stdout.

PORQUE ASSIM (decidido por teste real, 2026-08-20):
  - Syft dir:bundle  -> ve os .pyd/.dll nativos, mas so' cataloga pacotes cujo
    dist-info sobreviveu ao PyInstaller. Omitiu 26 directas, incluindo pyodbc.
  - cyclonedx-py `environment` -> versoes EXACTAS do que esta instalado (as que
    foram congeladas no bundle), mas traz o venv INTEIRO, com pyinstaller/pytest
    que sao ferramentas de build e NAO entram no MSI.
  - cyclonedx-py `requirements` -> componentes SEM versao (o requirements.txt tem
    ranges); inuteis para o CVE scan a jusante. Descartado.

A solucao: environment (versoes reais) FILTRADO ao fecho transitivo de runtime
do requirements.txt. Exclui as build-tools, mantem as transitivas de runtime
(certifi, cffi, etc.). Funde isso com o Syft por (nome, versao) normalizado.
O resultado nao afirma componentes que nao estao no artefacto NEM omite runtime.
"""

from __future__ import annotations

import importlib.metadata as _md
import json
import re
import sys


def _norm(nome: str) -> str:
    return (nome or "").strip().lower().replace("_", "-").replace(".", "-")


def _directos_do_requirements(path: str) -> set[str]:
    nomes: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for linha in fh:
            s = linha.strip()
            if not s or s.startswith("#") or s.startswith("-"):
                continue
            s = s.split("[", 1)[0]
            m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", s)
            if m:
                nomes.add(_norm(m.group(1)))
    return nomes


def _fecho_runtime(directos: set[str]) -> set[str]:
    """Fecho transitivo dos directos, via Requires-Dist da metadata instalada.

    Ignora deps marcadas com environment markers de extra (linhas '; extra ==')
    para nao arrastar dependencias opcionais que nao entram no runtime base.
    """
    instalados = {}
    for dist in _md.distributions():
        try:
            instalados[_norm(dist.metadata["Name"])] = dist
        except Exception:
            continue

    fecho: set[str] = set()
    pilha = list(directos)
    while pilha:
        n = pilha.pop()
        if n in fecho:
            continue
        fecho.add(n)
        dist = instalados.get(n)
        if not dist:
            continue
        for req in (dist.requires or []):
            # 'pkg (>=1); extra == "x"'  -> nao seguir extras
            if "; extra ==" in req or "extra ==" in req.split(";", 1)[-1]:
                continue
            m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", req)
            if m:
                pilha.append(_norm(m.group(1)))
    return fecho


def _chave(comp: dict) -> tuple:
    return (_norm(comp.get("name", "")), (comp.get("version") or "").strip())


def _carrega(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    if len(sys.argv) != 4:
        print("uso: merge_sbom.py <syft.json> <env.json> <requirements.txt>", file=sys.stderr)
        return 2

    syft_path, env_path, req_path = sys.argv[1], sys.argv[2], sys.argv[3]
    syft = _carrega(syft_path)
    env = _carrega(env_path)

    if syft.get("bomFormat") != "CycloneDX":
        print(f"{syft_path} nao e' CycloneDX", file=sys.stderr)
        return 1

    runtime = _fecho_runtime(_directos_do_requirements(req_path))

    componentes = list(syft.get("components") or [])
    vistos = {_chave(c) for c in componentes}

    acrescentados = 0
    excluidos_build = 0
    for comp in env.get("components") or []:
        nome = _norm(comp.get("name", ""))
        if nome not in runtime:
            # build-tool ou dep de build (pyinstaller, pytest, ...) -- nao vai no MSI
            excluidos_build += 1
            continue
        ch = _chave(comp)
        if ch in vistos:
            continue
        vistos.add(ch)
        componentes.append(comp)
        acrescentados += 1

    syft["components"] = componentes

    meta = syft.setdefault("metadata", {})
    props = meta.setdefault("properties", [])
    props.append({"name": "watcherdb:sbom:merged", "value": "syft+environment(runtime-filtered)"})
    props.append({"name": "watcherdb:sbom:components_from_environment", "value": str(acrescentados)})
    props.append({"name": "watcherdb:sbom:build_tools_excluded", "value": str(excluidos_build)})

    with open(syft_path, "w", encoding="utf-8") as fh:
        json.dump(syft, fh, indent=2)

    print(syft_path)
    print(
        f"[merge] {len(componentes)} componentes "
        f"(+{acrescentados} do environment runtime; {excluidos_build} build-tools excluidas)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
