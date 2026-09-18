# -*- coding: utf-8 -*-
"""Filegroups com problema: "72.4 GB Free / 7,192.1 GB Total" em vez de "72.4 GB / 7,192.1 GB" (owner, 18/09).

As palavras são texto visível: entram como chaves kpi_modal.fg_free / kpi_modal.fg_total em pt ("Livre"/"Total"),
en ("Free"/"Total") e es ("Libre"/"Total"); pt-BR não precisa de overlay (igual ao pt). O template usa _kpiT(chave, fallback).
Inserção textual das duas chaves logo a seguir a "kpi_modal": { em cada ficheiro (sem reformatar o JSON).

Requer FG_LIVRE_TOTAL aplicado.

Uso (raiz do repo):
  py docs/context/FG_LIVRE_TOTAL_ROTULOS_2026-09-18_apply.py --check
  py docs/context/FG_LIVRE_TOTAL_ROTULOS_2026-09-18_apply.py
  py -m pytest tests/unit/test_i18n_parity.py tests/unit/test_i18n_texto_a_mao_20260918.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = Path("templates/watcherdb_portal.html")
MARK = "kpi_modal.fg_free"
LOCALES = {"pt": ("Livre", "Total"), "en": ("Free", "Total"), "es": ("Libre", "Total")}

EDIT_PORTAL = (
    """                                return `<div class="fg-cell-size" title="${tip}">${_fgFmt(livre)} / ${_fgFmt(f.Total_MB)}</div>`;""",
    """                                return `<div class="fg-cell-size" title="${tip}">${_fgFmt(livre)} ${_kpiT('kpi_modal.fg_free', 'Livre')} / ${_fgFmt(f.Total_MB)} ${_kpiT('kpi_modal.fg_total', 'Total')}</div>`;""",
)


def _apply1(text, old, new, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    o, n = old.replace("\n", eol), new.replace("\n", eol)
    got = text.count(o)
    if got != 1:
        raise SystemExit(f"[ABORT] {label}: anchor esperado 1x, encontrado {got}x -- nada escrito")
    return text.replace(o, n)


def _inserir(texto_json, livre, total, label):
    eol = "\r\n" if "\r\n" in texto_json else "\n"
    anc = '  "kpi_modal": {' + eol
    if texto_json.count(anc) != 1:
        raise SystemExit(f"[ABORT] {label}: grupo kpi_modal nao encontrado 1x")
    novo = texto_json.replace(anc, anc + f'    "fg_free": {json.dumps(livre, ensure_ascii=False)},{eol}    "fg_total": {json.dumps(total, ensure_ascii=False)},{eol}', 1)
    antes, depois = json.loads(texto_json), json.loads(novo)
    if set(depois["kpi_modal"]) - set(antes["kpi_modal"]) != {"fg_free", "fg_total"}:
        raise SystemExit(f"[ABORT] {label}: insercao inesperada")
    depois["kpi_modal"].pop("fg_free"); depois["kpi_modal"].pop("fg_total")
    if depois != antes:
        raise SystemExit(f"[ABORT] {label}: o resto do JSON mudou")
    return novo


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = base / PORTAL
    portal = src.read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    if "fg-cell-size" not in portal:
        print("[ABORT] FG_LIVRE_TOTAL nao esta aplicado (aplicar primeiro)"); return 1
    novo_portal = _apply1(portal, EDIT_PORTAL[0], EDIT_PORTAL[1], "portal")
    novos = {}
    for loc, (livre, total) in LOCALES.items():
        p = base / "static/i18n" / f"{loc}.json"
        if not p.exists():
            print(f"[skip] {p} ausente na copia"); continue
        t = p.read_bytes().decode("utf-8")
        if '"fg_free"' in t:
            print(f"[ABORT] {loc}.json ja tem fg_free"); return 1
        novos[p] = _inserir(t, livre, total, loc)
    print(f"[ok] rotulos Free/Total: template + {len(novos)} locales (kpi_modal.fg_free, kpi_modal.fg_total)")
    if check:
        print("--check OK. Nada escrito."); return 0
    src.write_bytes(novo_portal.encode("utf-8")); print(f"[write] {PORTAL}")
    for p, t in novos.items():
        p.write_bytes(t.encode("utf-8")); print(f"[write] {p.relative_to(base)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
