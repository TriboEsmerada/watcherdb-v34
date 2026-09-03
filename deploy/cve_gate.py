"""Gate de CVE sobre o relatorio do grype. Falha o build em severidade alta.

Uso:
    python cve_gate.py <grype_report.json> [--fail-on high|critical] [--allowlist <file>]

Exit 0 se nenhuma CVE acima do limiar (fora da allowlist); exit 1 + resumo
caso contrario. Imprime SEMPRE o resumo por severidade na stderr.

PORQUE EXISTE (deploy-architect + security-auditor, 2026-08-20): o SBOM ja'
sai correcto, mas nada o cruzava com CVEs conhecidas. O scan tem de correr
ANTES da assinatura -- um CVE critico depois de assinar obriga a re-assinar num
HSM que custa.

ALLOWLIST (nao "ignorar"): CVEs aceites por decisao documentada -- ex.: CVE do
interpretador Python empacotado que so' se resolve com rebuild sobre um
point-release mais novo, agendado mas nao no proximo build. Cada entrada exige
razao escrita. O ficheiro de allowlist e' JSON:
    { "CVE-2025-4517": "Python 3.11.9->3.11.13 agendado wave X; nao explor. no bundle" }
Um banco ve a allowlist e a razao, nao um scan que passou por magia.
"""

from __future__ import annotations

import json
import sys

_ORDEM = {"critical": 4, "high": 3, "medium": 2, "low": 1, "negligible": 0, "unknown": 2}


def _sev(m: dict) -> str:
    return (m.get("vulnerability", {}).get("severity") or "unknown").lower()


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("uso: cve_gate.py <grype_report.json> [--fail-on high|critical] [--allowlist f]", file=sys.stderr)
        return 2

    report_path = args[0]
    fail_on = "high"
    allow_path = None
    i = 1
    while i < len(args):
        if args[i] == "--fail-on" and i + 1 < len(args):
            fail_on = args[i + 1].lower(); i += 2
        elif args[i] == "--allowlist" and i + 1 < len(args):
            allow_path = args[i + 1]; i += 2
        else:
            print(f"argumento desconhecido: {args[i]}", file=sys.stderr); return 2

    limiar = _ORDEM.get(fail_on, 3)

    allow: dict = {}
    if allow_path:
        try:
            with open(allow_path, encoding="utf-8") as fh:
                allow = json.load(fh)
        except FileNotFoundError:
            pass  # sem allowlist e' o caso normal

    # errors="replace": o report do grype pode trazer bytes nao-UTF8 em
    # descricoes de CVE (apanhado 2026-08-20); nao deixar isso rebentar o gate.
    with open(report_path, encoding="utf-8", errors="replace") as fh:
        report = json.load(fh)
    matches = report.get("matches") or []

    # Contagem por severidade (todas), para o resumo.
    contagem: dict = {}
    for m in matches:
        s = _sev(m)
        contagem[s] = contagem.get(s, 0) + 1

    # Bloqueadores: severidade >= limiar E nao na allowlist.
    bloqueadores = []
    allowlisted = 0
    for m in matches:
        if _ORDEM.get(_sev(m), 2) < limiar:
            continue
        cve = m.get("vulnerability", {}).get("id", "?")
        if cve in allow:
            allowlisted += 1
            continue
        bloqueadores.append((
            cve,
            _sev(m),
            m.get("artifact", {}).get("name", "?"),
            m.get("artifact", {}).get("version", "?"),
            ",".join(m.get("vulnerability", {}).get("fix", {}).get("versions", []) or []),
        ))

    print("=== CVE scan (grype) ===", file=sys.stderr)
    for s in ("critical", "high", "medium", "low", "negligible", "unknown"):
        if contagem.get(s):
            print(f"  {s}: {contagem[s]}", file=sys.stderr)
    if allowlisted:
        print(f"  ({allowlisted} allowlisted com razao documentada)", file=sys.stderr)

    if not bloqueadores:
        print(f"OK: zero CVEs >= {fail_on} fora da allowlist.", file=sys.stderr)
        return 0

    # dedup por (cve, artefacto)
    unicos = sorted(set(bloqueadores))
    print(f"\nBLOQUEIO: {len(unicos)} CVE(s) >= {fail_on} sem allowlist:", file=sys.stderr)
    for cve, sev, nome, ver, fix in unicos:
        fixtxt = f" -> fix {fix}" if fix else " (sem fix conhecido)"
        print(f"  [{sev}] {nome} {ver}: {cve}{fixtxt}", file=sys.stderr)
    print(
        "\nResolver (rebuild com versao corrigida) OU acrescentar a allowlist "
        "com razao documentada (--allowlist).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
