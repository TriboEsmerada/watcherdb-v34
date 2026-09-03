#!/usr/bin/env python3
"""knowledge_base/index.json -- registar o glossario i18n + corrigir checksum drift (parecer v33-knowledge-base-curator 2026-09-03).

Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/KB_INDEX_PASSO1_apply.py --dry-run
    py -3.14 docs/context/KB_INDEX_PASSO1_apply.py
Impacto: so' knowledge_base/index.json (JSON normal, round-trip seguro). Rollback: git checkout -- knowledge_base/index.json
Nao faz onboarding dos 4 docs de architecture/ sem entrada (intelligence_db_schema, inventario_servers_json_fonte_unica,
backups_kpis, modules/backups) -- isso passa pelos 5 gates do core-librarian.
"""
import argparse, hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(); root = Path(a.root).resolve()
    idx_p = root / "knowledge_base/index.json"
    idx = json.loads(idx_p.read_text(encoding="utf-8"))
    gl = root / "knowledge_base/domain/i18n_glossary.md"
    ad = root / "knowledge_base/operations/seed/ad_service_account_rotation.md"
    if not gl.exists() or not ad.exists():
        print("[ABORT] ficheiros em falta"); sys.exit(2)
    domain = idx["namespaces"]["domain"]["docs"]
    if any(d.get("path") == "domain/i18n_glossary.md" for d in domain):
        print("[ABORT] glossario ja registado"); sys.exit(2)
    domain.append({
        "id": "domain-i18n-glossary-v34",
        "path": "domain/i18n_glossary.md",
        "title": "Glossário i18n — WatcherDB V3.4",
        "tags": ["i18n", "glossary", "locales", "en-default", "pt-pt", "pt-br", "es", "terminology", "acentuacao"],
        "license": "internal",
        "doc_type": "domain-glossary",
        "added": "2026-09-03",
        "last_validated": "2026-09-03",
        "ingested_by": "orquestrador (script I18N_PTBR_PASSO1_apply.py, commit 5612d68; editado ed4e514)",
        "owner_specialist": "v33-i18n-linguist",
        "sensitivity": "internal-only",
        "size_bytes": gl.stat().st_size,
        "checksum_sha256": sha(gl),
        "gates_passed": [],
        "gates_note": "pendente: core-librarian deve correr os 5 gates (dedup, license, quality, sensitivity, namespace)",
        "description": "Glossário de termos i18n para en/pt/pt-BR/es — termos que ficam em inglês, pares pt-PT↔pt-BR e regra de acentuação rigorosa; fonte para v33-i18n-linguist e v33-i18n-coverage.",
    })
    for d in idx["namespaces"]["operations"]["docs"]:
        if d["id"] == "ops-ad-service-account-rotation-seed":
            old, new = d["checksum_sha256"], sha(ad)
            if old != new:
                d["checksum_sha256"] = new; d["last_validated"] = "2026-09-03"
                print(f"checksum ad_service_account_rotation: {old[:12]}.. -> {new[:12]}..")
    idx["stats"]["total_docs"] = sum(len(ns["docs"]) for ns in idx["namespaces"].values())
    idx["updated"] = "2026-09-03"
    idx["notes"] = idx.get("notes", "") + " 2026-09-03: glossário i18n registado (gates pendentes) + checksum AD rotation recalculado; drift aberto: 4 docs em architecture/ sem entrada (onboarding core-librarian)."
    out = json.dumps(idx, ensure_ascii=False, indent=2) + "\n"
    if a.dry_run:
        print(f"[DRY] total_docs={idx['stats']['total_docs']}; glossario sha={sha(gl)[:12]}.."); return
    idx_p.write_text(out, encoding="utf-8"); print("[OK] knowledge_base/index.json")


if __name__ == "__main__":
    main()
