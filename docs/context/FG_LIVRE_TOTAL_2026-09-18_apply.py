# -*- coding: utf-8 -*-
"""Filegroups com problema (modal de KPI): espaço livre / total ao lado da percentagem (owner, 18/09).

Pedido: "além do percentual eu gostaria de ver ao lado do percentual o Freespace / total".
O endpoint /api/intelligence-kpis/detail/filegroup-usage/{instancia} já devolve Total_MB, Used_MB, Free_MB e Max_Size_MB
(api/routers/intelligence/admin.py, KPI_MSSQL_FG_USAGE_STG, leitura via sql_monitoring): é só frontend.

O QUE MUDA
 - Grelha .fg-problem-grid ganha uma 5.ª coluna .fg-cell-size entre a percentagem e o badge: "livre / total"
   (ex.: "1,2 GB / 120 GB"), tabular, cor terciária, com title com os MB exactos e o usado. Sem Total_MB fica vazia.
 - Modo estreito (@container <= 640px): a coluna entra na linha 1 (db + % + livre/total + badge); o nome do filegroup
   continua em linha própria.
 - Formatador local _fgFmt (MB -> GB com 1 casa; abaixo de 1 GB em MB), com o separador do idioma da página
   (toLocaleString(document.documentElement.lang)). Sem texto novo para o i18n (só números e unidades).

RAMO: o mesmo onde estiver o D5 (toca nas mesmas linhas do painel). Requer D5 aplicado.

Uso (raiz do repo):
  py docs/context/FG_LIVRE_TOTAL_2026-09-18_apply.py --check
  py docs/context/FG_LIVRE_TOTAL_2026-09-18_apply.py
  py -m pytest tests/unit/test_kpi_env_breakdown_20260818.py tests/unit/test_i18n_texto_a_mao_20260918.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; KPIs > Filegroups critical > expandir uma instância
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = Path("templates/watcherdb_portal.html")
MARK = "fg-cell-size"

EDITS = [
    # CSS: 5 colunas no modo largo
    ("""        .fg-problem-grid {
            display: grid;
            grid-template-columns: auto auto max-content max-content;""",
     """        .fg-problem-grid {
            display: grid;
            grid-template-columns: auto auto max-content max-content max-content;   /* 2026-09-18: + livre/total */""", 1),
    ("""        .fg-problem-grid .fg-cell-pct {
            color: var(--color-text-tertiary);
            font-size: 11px;
            text-align: right;
            font-variant-numeric: tabular-nums;
        }""",
     """        .fg-problem-grid .fg-cell-pct {
            color: var(--color-text-tertiary);
            font-size: 11px;
            text-align: right;
            font-variant-numeric: tabular-nums;
        }
        .fg-problem-grid .fg-cell-size {   /* 2026-09-18 (owner): livre / total ao lado da percentagem */
            color: var(--color-text-tertiary);
            font-size: 11px;
            text-align: right;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }""", 1),
    # CSS: modo estreito -- db + % + livre/total + badge na linha 1
    ("""            .fg-problem-grid .fg-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) max-content max-content;""",
     """            .fg-problem-grid .fg-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) max-content max-content max-content;""", 1),
    # JS: formatador local + celula
    ("""                            const instDisplay = String(card.dataset.instanceName || '');
                            const badge = st => {""",
     """                            const instDisplay = String(card.dataset.instanceName || '');
                            // 2026-09-18 (owner): livre / total ao lado da percentagem (o endpoint ja devolve Total_MB/Used_MB/Free_MB)
                            const _lang = document.documentElement.lang || undefined;
                            const _fgFmt = mb => { const n = Number(mb); if (!isFinite(n)) return ''; return n >= 1024 ? (n / 1024).toLocaleString(_lang, { maximumFractionDigits: 1 }) + ' GB' : Math.round(n).toLocaleString(_lang) + ' MB'; };
                            const sizeCell = f => {
                                if (f.Total_MB == null) return '<div class="fg-cell-size"></div>';
                                const livre = f.Free_MB != null ? Number(f.Free_MB) : Math.max(0, Number(f.Total_MB) - Number(f.Used_MB || 0));
                                const tip = `${Math.round(livre).toLocaleString(_lang)} MB / ${Math.round(Number(f.Total_MB)).toLocaleString(_lang)} MB` + (f.Used_MB != null ? ` (${Math.round(Number(f.Used_MB)).toLocaleString(_lang)} MB)` : '');
                                return `<div class="fg-cell-size" title="${tip}">${_fgFmt(livre)} / ${_fgFmt(f.Total_MB)}</div>`;
                            };
                            const badge = st => {""", 1),
    ("""                                        <div class="fg-cell-pct">${f.Percent_Used != null ? Number(f.Percent_Used).toFixed(1) + '%' : ''}</div>
                                        <div class="fg-cell-badge">${badge(f.Status)}</div>""",
     """                                        <div class="fg-cell-pct">${f.Percent_Used != null ? Number(f.Percent_Used).toFixed(1) + '%' : ''}</div>
                                        ${sizeCell(f)}
                                        <div class="fg-cell-badge">${badge(f.Status)}</div>""", 1),
]


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:160]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = base / PORTAL
    portal = src.read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    if "D5 detalhe" not in portal:
        print("[ABORT] o D5 nao esta aplicado neste template (aplicar primeiro)"); return 1
    novo = _apply(portal, EDITS, "fg livre/total")
    print(f"[ok] filegroups: {len(EDITS)} blocos (grelha 5 colunas + modo estreito + celula livre/total)")
    if check:
        print("--check OK. Nada escrito."); return 0
    src.write_bytes(novo.encode("utf-8")); print(f"[write] {PORTAL}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
