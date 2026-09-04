#!/usr/bin/env python3
"""Wave BUG-003 -- Lote F4 HOTFIX: repor `category: 'Espaco'` nas 4 entradas de KPI_DOCUMENTATION.

O commit 27d427e (F4) aplicou o par "Espaco" -> "Espaço" do sidecar do linguista tambem ao campo `category:`
das 4 entradas de Espaco (linhas ~40591/40637/40679/40723). Esse valor NAO e' texto visivel: e' o identificador
da categoria usado por KPI_CATEGORIES (:41524), categoryColors (:41548/:41634), KPI_METADATA (:33450...) e
SPACE_CRITICAL (:30017); o label traduzido vem de tCategory(). Com 'Espaço' nas 4 entradas, o menu de ajuda "?"
deixa de listar os 4 KPIs de Espaco (o filtro por categoria nao encontra nenhum) e a cor cai no default.

Este hotfix: (1) repoe 'Espaco' nas 4 linhas `category:` (e so' nessas -- espera exactamente 4 ocorrencias);
(2) reclassifica o par no sidecar I18N_F4_PAIRS.json para "skip_identifier" com nota (para o script F4 nunca o
voltar a aplicar); (3) corrige a entrada F4 do CHANGELOG (33 -> 32 literais + nota do hotfix).

Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_F4_HOTFIX_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_F4_HOTFIX_PASSO1_apply.py
Rollback: git checkout -- templates/watcherdb_portal.html docs/changelog/CHANGELOG.md docs/context/I18N_F4_PAIRS.json
"""
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
HTML, CHG, SIDE = "templates/watcherdb_portal.html", "docs/changelog/CHANGELOG.md", "docs/context/I18N_F4_PAIRS.json"

OLD_CAT, NEW_CAT, N_CAT = "category: 'Espaço',", "category: 'Espaco',", 4
CHG_OLD = "33 literais. Só texto. [tier: Std]"
CHG_NEW = ("32 literais. Só texto. Hotfix no mesmo dia (27d427e tinha 33): o par \"Espaco\" → \"Espaço\" "
           "entrou também nas 4 linhas `category:` — é o identificador da categoria (`KPI_CATEGORIES`), não texto, "
           "e escondia os 4 KPIs de Espaço do menu de ajuda; reposto e excluído do sidecar. [tier: Std]")
NOTE = ("category e' identificador (KPI_CATEGORIES :41524, categoryColors :41548/:41634, KPI_METADATA :33450, "
        "SPACE_CRITICAL :30017); o label visivel vem de tCategory(). Nao tocar -- partiria o filtro por categoria "
        "do menu de ajuda. Hotfix 2026-09-04.")


def read(p):
    raw = p.read_bytes().decode("utf-8"); return raw, ("\r\n" if "\r\n" in raw else "\n")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(); root = Path(a.root).resolve(); print(f"root: {root}  dry-run={a.dry_run}")
    problems = []
    html, _ = read(root / HTML)
    c = html.count(OLD_CAT)
    if c != N_CAT: problems.append(f"{HTML}: esperado {N_CAT}x {OLD_CAT!r}, encontrado {c}x")
    if html.count("category: 'Espaco',") != 4: problems.append(f"{HTML}: esperado 4x category: 'Espaco' (KPI_METADATA) antes do fix")
    chg, _ = read(root / CHG)
    if chg.count(CHG_OLD) != 1: problems.append(f"{CHG}: esperado 1x {CHG_OLD!r}, encontrado {chg.count(CHG_OLD)}x")
    side_raw = (root / SIDE).read_text(encoding="utf-8")
    pairs = json.loads(side_raw)
    hits = [p for p in pairs if p.get("old") == "Espaco"]
    if len(hits) != 1: problems.append(f"{SIDE}: esperado 1 par 'Espaco', encontrado {len(hits)}")
    elif hits[0].get("class") != "fix": problems.append(f"{SIDE}: par 'Espaco' ja nao e' 'fix' ({hits[0].get('class')}) -- hotfix ja aplicado?")
    if problems:
        print("[ABORT] nada foi escrito:"); [print("   -", x) for x in problems]; sys.exit(2)
    if a.dry_run:
        print(f"[DRY] {HTML}: 4 linhas category 'Espaço'->'Espaco' ; {SIDE}: par reclassificado ; {CHG}: entrada F4 corrigida"); return
    (root / HTML).write_bytes(html.replace(OLD_CAT, NEW_CAT).encode("utf-8")); print(f"[OK] {HTML} (4 ocorrencias)")
    hits[0]["class"] = "skip_identifier"; hits[0]["note"] = NOTE
    (root / SIDE).write_text(json.dumps(pairs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"); print(f"[OK] {SIDE}")
    (root / CHG).write_bytes(chg.replace(CHG_OLD, CHG_NEW, 1).encode("utf-8")); print(f"[OK] {CHG}")
    print("\nSeguir com: browser (Ctrl+F5) -> '?' de um KPI -> menu tem de listar 4 KPIs em Espaço ; PASSO2 commit")


if __name__ == "__main__":
    main()
