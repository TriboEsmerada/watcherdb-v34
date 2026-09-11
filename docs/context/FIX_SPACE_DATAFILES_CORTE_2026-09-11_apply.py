"""FIX 2026-09-11 -- Space > Databases > FileGroups > DATAFILES: coluna "Disk Avail GB"
cortada a meio e coluna "Status" invisivel (screenshot do owner, SQLHDSPRD406 / MYBAGP2).

Causa (nao e' falta de largura, e' um clip):
  A regra GLOBAL de celulas do portal (templates/watcherdb_portal.html ~2717)
      td { max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  aplica-se tambem as celulas que HOSPEDAM os paineis de expansao:
    - <tr id="files-row-{fg}"> <td colspan="8"> ... painel de datafiles ...   (~28527)
    - <tr id="fg-row-{db}" class="space-fg-expansion"> <td colspan="5"> ... filegroups ... (~17407)
  O painel de datafiles e' uma tabela `width: max-content` (regra global de <table>),
  mais larga que a celula que a contem -> a celula corta na propria borda (o corte cai
  a meio de "Disk Avail GB", nao na borda do contentor exterior). Agravantes:
    - colspan="8" numa tabela de filegroups com 9 colunas (a coluna "Acoes" fica de fora
      e o painel perde ~80 px de largura util);
    - "Logical Name" com min-width 420 px + white-space nowrap herdado.

Fix (so portal; a decisao de 2026-07-31 -- painel sem scroll proprio para o thead fazer
sticky no scroll exterior -- fica INTACTA, `.space-datafiles-scroll { overflow: visible }`
nao e' tocado):
  1. CSS: as celulas de expansao saem da regra global
       .space-fg-expansion > td, .space-files-expansion > td { overflow: visible; max-width: none;
                                                               white-space: normal; min-width: 0; }
     e o painel de datafiles fica mais denso (padding 8/10 em vez de 12/16), scoped ao painel.
  2. <tr files-row> ganha class="space-files-expansion" e colspan 8 -> 9.
  3. "Logical Name": min-width 420 -> 260 px, max-width 420 px, white-space normal (nome longo
     quebra dentro da coluna em vez de empurrar tudo).
  Com isto o painel cabe no contentor a 1366 px; quando nao couber (muitas colunas largas),
  a largura propaga-se a tabela-mae e o contentor exterior (.table-container, overflow-x auto)
  rola na horizontal em vez de cortar.

Uso (raiz do repo):
  py docs/context/FIX_SPACE_DATAFILES_CORTE_2026-09-11_apply.py --check
  py docs/context/FIX_SPACE_DATAFILES_CORTE_2026-09-11_apply.py --preview DIR
  py docs/context/FIX_SPACE_DATAFILES_CORTE_2026-09-11_apply.py

Depois de aplicar:
  py -m pytest tests/unit/test_space_datafiles_clip_20260911.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34   (template em cache) ; Ctrl+F5
  Space > qualquer database > expandir um filegroup: 9 colunas visiveis ate "Status".
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "templates" / "watcherdb_portal.html"
TEST = ROOT / "tests" / "unit" / "test_space_datafiles_clip_20260911.py"

EDITS: list[tuple[Path, str, str, int]] = []


def edit(path: Path, old: str, new: str, count: int = 1) -> None:
    EDITS.append((path, old, new, count))


# 1. CSS -- logo a seguir a regra que preserva a decisao de 2026-07-31
edit(PORTAL,
     "        .space-datafiles-scroll { overflow: visible; }\n",
     "        .space-datafiles-scroll { overflow: visible; }\n"
     "        /* 2026-09-11 (owner: \"Disk Avail GB\" cortada a meio, \"Status\" invisivel): a regra\n"
     "           global `td { overflow: hidden; max-width: 400px; white-space: nowrap }` (~2717)\n"
     "           tambem apanhava as celulas que HOSPEDAM os paineis de expansao (filegroups de\n"
     "           uma base; datafiles de um filegroup) e cortava o painel na borda da celula.\n"
     "           Estas celulas sao contentores, nao dados: saem da regra. A largura do painel\n"
     "           passa a propagar-se a tabela-mae e, se nao couber, .table-container rola. */\n"
     "        .space-fg-expansion > td, .space-files-expansion > td {\n"
     "            overflow: visible; max-width: none; white-space: normal; min-width: 0;\n"
     "        }\n"
     "        /* Painel de datafiles mais denso (9 colunas): 8/10 em vez do 12/16 global. */\n"
     "        .space-datafiles-panel .nested-table th, .space-datafiles-panel .nested-table td { padding: 8px 10px; }\n")

# 2. linha/celula que hospeda o painel: classe + colspan certo (a tabela de filegroups tem 9 colunas)
edit(PORTAL,
     '                        <tr id="files-row-${fgId}" style="display: none;">\n'
     '                            <td colspan="8" style="padding: 0; background: var(--color-bg-sunken);">\n',
     '                        <tr id="files-row-${fgId}" class="space-files-expansion" style="display: none;">\n'
     '                            <td colspan="9" style="padding: 0; background: var(--color-bg-sunken);">\n')

# 3. Logical Name: 420 px minimos -> 260 min / 420 max com quebra (th e td)
edit(PORTAL,
     "padding-left: 48px; min-width: 420px; word-break: break-all;",
     "padding-left: 48px; min-width: 260px; max-width: 420px; white-space: normal; word-break: break-all;",
     count=2)

TEST_SRC = '''"""
2026-09-11 -- Space > DATAFILES: o painel era cortado pela regra global de <td>
(overflow hidden / max-width 400) aplicada a celula que o hospeda. Guardas estaticas.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


def test_expansion_cells_opt_out_of_global_td_clip():
    assert ".space-fg-expansion > td, .space-files-expansion > td {" in PORTAL
    rule = PORTAL.split(".space-fg-expansion > td, .space-files-expansion > td {", 1)[1].split("}", 1)[0]
    assert "overflow: visible" in rule and "max-width: none" in rule and "white-space: normal" in rule


def test_files_row_spans_all_nine_filegroup_columns():
    assert 'id="files-row-${fgId}" class="space-files-expansion"' in PORTAL
    row = PORTAL.split('id="files-row-${fgId}"', 1)[1].split("</tr>", 1)[0]
    assert 'colspan="9"' in row and 'colspan="8"' not in row


def test_logical_name_column_no_longer_forces_420px():
    assert "min-width: 420px; word-break: break-all;" not in PORTAL
    assert PORTAL.count("min-width: 260px; max-width: 420px; white-space: normal; word-break: break-all;") == 2


def test_decision_20260731_sticky_header_preserved():
    # o painel embutido continua SEM scroll proprio (thead sticky no scroll exterior)
    assert ".space-datafiles-scroll { overflow: visible; }" in PORTAL
'''


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    preview_dir = None
    if "--preview" in argv:
        i = argv.index("--preview")
        if i + 1 >= len(argv):
            print("--preview precisa de DIR")
            return 2
        preview_dir = Path(argv[i + 1]).resolve()

    raw = PORTAL.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    text = raw
    problems = applied = skipped = 0
    for path, old, new, count in EDITS:
        old = old.replace("\n", eol); new = new.replace("\n", eol)
        if new in text and old not in text:
            skipped += 1; print(f"[skip] ja aplicado: {old[:60]!r}"); continue
        n = text.count(old)
        if n != count:
            problems += 1; print(f"[ABORT] esperado {count}x, encontrado {n}x: {old[:90]!r}"); continue
        text = text.replace(old, new); applied += 1
        print(f"[ok] {count}x {old[:60]!r}")
    if problems:
        print(f"\n{problems} anchor(s) falharam -- NADA escrito."); return 1
    if check_only:
        print(f"\n--check OK: {applied} edicoes aplicaveis, {skipped} ja aplicadas; 1 teste novo. Nada escrito."); return 0

    target_root = preview_dir if preview_dir is not None else ROOT
    out = target_root / PORTAL.relative_to(ROOT); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(text.encode("utf-8")); print(f"[write] {out.relative_to(target_root)}")
    tout = target_root / TEST.relative_to(ROOT); tout.parent.mkdir(parents=True, exist_ok=True)
    tout.write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {tout.relative_to(target_root)}")
    if preview_dir is not None:
        print(f"\n--preview OK: copias em {preview_dir}. Repo intacto.")
    else:
        print("\nAplicado. Corre agora:\n  py -m pytest tests/unit/test_space_datafiles_clip_20260911.py -q --no-cov\n  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
