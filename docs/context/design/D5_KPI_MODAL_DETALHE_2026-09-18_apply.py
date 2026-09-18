# -*- coding: utf-8 -*-
"""Design, lote D5 — detalhe expandido nas modais de KPI (owner, 18/09: "ta dificil de ler assim") (2026-09-18).

Print do owner: modal "FileGroups Usage - Critical" em Light, cartão da instância expandido. O painel de detalhe
(.card-expand) tem fundo fixo rgba(15,23,42,0.55) — azul-marinho do dark a 55% — que sobre o cartão claro vira cinzento
escuro; por cima, links em #818cf8 e badges com o sólido de severidade como texto. Ilegível em Light.

O QUE MUDA (só cor)
 - .card-expand (toggleCardExpand, todas as modais de KPI): background rgba(15,23,42,0.55) -> rgb(var(--rgb-surface-deep)/0.55)
   (dark igual ao de hoje; Light fica claro; HC preto) e borda rgba(71,85,105,0.35) -> var(--color-border).
 - Badge de estado do filegroup: getSevTokens(s).fill + alfa (sólido como texto) -> .bg/.text do mesmo helper (tint/texto).
 - Cartão genérico da modal de KPI: badge CRITICAL/WARNING com fundo #7f1d1d/#78350f/#1e3a5f fixo -> tint do helper;
   pill de ambiente (PRD/QLT/TST) branco sobre sólido -> tint/texto; sólido usado como cor de texto/ícone -> .text;
   hora do cartão em -disabled -> -tertiary.
 - Contagens "N critical"/"N warning" dos cartões (4 renderizadores) e gráfico por ambiente (rótulos PRD/QLT/TST/DEV
   na variante -text da mesma convenção de cor; barra no sólido; botão "limpar filtro") -> contrato.
 - Links "abrir no Space" (#818cf8 indigo do dark): filegroups da modal de KPI e do ecrã Space -> var(--color-text-link);
   "Unlimited" no Space -> var(--sev-info-text).

RAMO: design/tokens-contrato. Requer D2.

Uso (raiz do repo):
  py docs/context/design/D5_KPI_MODAL_DETALHE_2026-09-18_apply.py --check
  py docs/context/design/D5_KPI_MODAL_DETALHE_2026-09-18_apply.py
  py -m pytest tests/unit/test_kpi_env_breakdown_20260818.py tests/unit/test_space_datafiles_clip_20260911.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; KPIs > Filegroups critical > expandir uma instância, em Light
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PORTAL = Path("templates/watcherdb_portal.html")
MARK = "D5 detalhe"
# teste de tema que fixava as duas linhas antigas do cartao generico (o 5-way de ambiente tinha 5 ocorrencias; passa a 4)
_T_ENV_OLD = "        self.assertGreaterEqual(PORTAL.count(\"=== 'DEV' ? getSevTokens('INFO').fill : 'var(--color-text-disabled)'\"), 5)"
_T_ENV_NEW = "        self.assertGreaterEqual(PORTAL.count(\"=== 'DEV' ? getSevTokens('INFO').fill : 'var(--color-text-disabled)'\"), 4)   # D5: o cartao generico da modal de KPI passou a itemEnvSev (tint/texto)"
_T_SEV_OLD = "        self.assertIn(\"const sevColor = itemSev === 'CRITICAL' ? getSevTokens('CRITICAL').fill\", PORTAL)"
_T_SEV_NEW = "        self.assertIn(\"const sevColor = sevTk.text;\", PORTAL)   # D5: solido nao serve de cor de texto; sevTk vem de getSevTokens(itemSev)"
TESTES = {Path("tests/test_theme_v33_foundation_smoke.py"): [(_T_ENV_OLD, _T_ENV_NEW, 1), (_T_SEV_OLD, _T_SEV_NEW, 1)]}

EDITS = [
    ("""                panel.style.cssText = 'display: block; margin-top: 8px; padding: 10px; background: rgba(15, 23, 42, 0.55); border: 1px solid rgba(71, 85, 105, 0.35); border-radius: 6px;';""",
     """                panel.style.cssText = 'display: block; margin-top: 8px; padding: 10px; background: rgb(var(--rgb-surface-deep) / 0.55); border: 1px solid var(--color-border); border-radius: 6px;';   // D5 detalhe: era navy fixo (cinzento escuro em Light)""", 1),
    ("""                                const col = getSevTokens(s).fill;
                                return `<span style="background:${col}22;color:${col};padding:1px 8px;border-radius:4px;font-size:10px;font-weight:700;">${s || '?'}</span>`;""",
     """                                const tk = getSevTokens(s);   // D5 detalhe: tint/texto (era solido como texto)
                                return `<span style="background:${tk.bg};color:${tk.text};padding:1px 8px;border-radius:4px;font-size:10px;font-weight:700;">${s || '?'}</span>`;""", 1),
    ("""style="color:#818cf8;text-decoration:none;" title="Abrir no Space filtrado nesta database">""",
     """style="color:var(--color-text-link);text-decoration:none;" title="Abrir no Space filtrado nesta database">""", 1),
    ("""                const maxColor = maxSz === 'Unlimited' ? '#818cf8' : 'var(--color-text-tertiary)';""",
     """                const maxColor = maxSz === 'Unlimited' ? 'var(--sev-info-text)' : 'var(--color-text-tertiary)';""", 1),
    ("""style="color:#818cf8;text-decoration:none;font-size:11px;cursor:pointer" title=""",
     """style="color:var(--color-text-link);text-decoration:none;font-size:11px;cursor:pointer" title=""", 1),
    # ---- cartao generico da modal de KPI (o do print do owner): badge de severidade com fundo dark fixo,
    #      pill de ambiente branco sobre solido, solido como cor de texto, hora em -disabled ----
    ("""                        const itemEnvColor = itemEnv === 'PRD' ? getSevTokens('CRITICAL').fill : itemEnv === 'QLT' ? getSevTokens('WARNING').fill : itemEnv === 'TST' ? getSevTokens('OK').fill : itemEnv === 'DEV' ? getSevTokens('INFO').fill : 'var(--color-text-disabled)';""",
     """                        const itemEnvSev = itemEnv === 'PRD' ? 'CRITICAL' : itemEnv === 'QLT' ? 'WARNING' : itemEnv === 'TST' ? 'OK' : itemEnv === 'DEV' ? 'INFO' : null;   // D5 detalhe
                        const itemEnvColor = itemEnvSev ? getSevTokens(itemEnvSev).fill : 'var(--color-text-disabled)';
                        const itemEnvPill = itemEnvSev ? `background: ${getSevTokens(itemEnvSev).bg}; color: ${getSevTokens(itemEnvSev).text};` : 'background: rgba(100,116,139,0.15); color: var(--color-text-tertiary);';""", 1),
    ("""                        const sevColor = itemSev === 'CRITICAL' ? getSevTokens('CRITICAL').fill : itemSev === 'WARNING' ? getSevTokens('WARNING').fill : getSevTokens('OK').fill;""",
     """                        const sevTk = itemSev === 'CRITICAL' ? getSevTokens('CRITICAL') : itemSev === 'WARNING' ? getSevTokens('WARNING') : getSevTokens('OK');
                        const sevColor = sevTk.text;   // D5 detalhe: e' cor de TEXTO/icone (era .fill = solido)""", 1),
    ("""                                            <span style="background: ${itemEnvColor}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;">${itemEnv}</span>""",
     """                                            <span style="${itemEnvPill} padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;">${itemEnv}</span>""", 1),
    ("""                                        <span style="background: ${itemSev === 'CRITICAL' ? '#7f1d1d' : itemSev === 'WARNING' ? '#78350f' : '#1e3a5f'}; color: ${sevColor}; padding: 3px 10px; border-radius: 4px; font-size: 11px; font-weight: 700;">""",
     """                                        <span style="background: ${sevTk.bg}; color: ${sevColor}; padding: 3px 10px; border-radius: 4px; font-size: 11px; font-weight: 700;">""", 1),
    ("""                                        ${timeStr ? `<span style="color: var(--color-text-disabled); font-size: 11px;"><i class="fas fa-clock" style="margin-right: 3px;"></i>${timeStr}</span>` : ''}""",
     """                                        ${timeStr ? `<span style="color: var(--color-text-tertiary); font-size: 11px;"><i class="fas fa-clock" style="margin-right: 3px;"></i>${timeStr}</span>` : ''}""", 1),
    # ---- contagens "N critical" / "N warning" nos cartoes (4 renderizadores) ----
    ("""<span style="color: #ef4444; font-weight: 700;">${criticalVal} critical</span>""", """<span style="color: var(--sev-critical-text); font-weight: 700;">${criticalVal} critical</span>""", 2),
    ("""<span style="color: #ef4444; font-weight: 600;">${criticalVal} critical</span>""", """<span style="color: var(--sev-critical-text); font-weight: 600;">${criticalVal} critical</span>""", 1),
    ("""<span style="color: #ef4444; font-weight: 600;" aria-label="${criticalVal} drives criticos">""", """<span style="color: var(--sev-critical-text); font-weight: 600;" aria-label="${criticalVal} drives criticos">""", 1),
    ("""<span style="color: #f59e0b; font-weight: 600;">${warningVal} warning</span>""", """<span style="color: var(--sev-warning-text); font-weight: 600;">${warningVal} warning</span>""", 3),
    ("""<span style="color: #f59e0b; font-weight: 600;" aria-label="${warningVal} drives em warning">""", """<span style="color: var(--sev-warning-text); font-weight: 600;" aria-label="${warningVal} drives em warning">""", 1),
    # ---- grafico por ambiente: rotulos (texto) na variante -text da mesma convencao de cor; barra no solido ----
    ("""                            'PRD': '#ef4444',  // Vermelho para Produção
                            'QLT': '#f59e0b',  // Amarelo para Qualidade
                            'TST': '#22c55e',  // Verde para Teste
                            'DEV': '#3b82f6',  // Azul para Desenvolvimento""",
     """                            'PRD': getSevTokens('CRITICAL').text,  // Vermelho para Produção (D5: variante -text, mesma convencao)
                            'QLT': getSevTokens('WARNING').text,   // Amarelo para Qualidade
                            'TST': getSevTokens('OK').text,        // Verde para Teste
                            'DEV': getSevTokens('INFO').text,      // Azul para Desenvolvimento""", 1),
    ("""                        const modalSevBarColor = kpiType.includes('-warning') ? '#f59e0b'
                            : kpiType.includes('-critical') ? '#ef4444' : null;""",
     """                        const modalSevBarColor = kpiType.includes('-warning') ? getSevTokens('WARNING').fill
                            : kpiType.includes('-critical') ? getSevTokens('CRITICAL').fill : null;   // D5: barra = solido do contrato""", 1),
    ("""<button onclick="clearEnvFilter()" style="margin-left: 8px; background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #fca5a5; padding: 2px 8px;""",
     """<button onclick="clearEnvFilter()" style="margin-left: 8px; background: var(--sev-critical-tint); border: 1px solid var(--sev-critical-border); color: var(--sev-critical-text); padding: 2px 8px;""", 1),
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
    if "D2 contrato" not in portal:
        print("[ABORT] o D2 nao esta aplicado neste template (ramo errado?)"); return 1
    novo = _apply(portal, EDITS, "detalhe")
    print(f"[ok] detalhe das modais de KPI: {len(EDITS)} blocos (painel .card-expand, badge do filegroup, 3 links indigo, cartao generico 5, contagens 5, grafico por ambiente 3)")
    testes_novos = {rel: _apply((base / rel).read_bytes().decode("utf-8"), edits, str(rel)) for rel, edits in TESTES.items()}
    print(f"[ok] {len(TESTES)} teste passa a fixar as linhas novas do cartao generico")
    if check:
        print("--check OK. Nada escrito."); return 0
    src.write_bytes(novo.encode("utf-8")); print(f"[write] {PORTAL}")
    for rel, t in testes_novos.items():
        (base / rel).write_bytes(t.encode("utf-8")); print(f"[write] {rel}")
    print("\nAplicado. Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; KPIs > Filegroups critical > expandir instancia (Light).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
