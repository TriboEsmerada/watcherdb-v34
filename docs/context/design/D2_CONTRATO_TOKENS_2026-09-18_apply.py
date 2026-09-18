# -*- coding: utf-8 -*-
"""Design, lote D2 — contrato de tokens nos três temas (2026-09-18).

Origem: docs/context/design/2026-09-18_tokens_contrato.md (ux-design-reviewer) e a prova do D1 (2026-09-18_review.md §5).
Só CSS dos blocos de tema (L59-261), sete regras de selector e duas asserções de teste. Nenhum JS, nenhuma string (i18n intocado).

O QUE MUDA
 Dark (:root)  color-scheme:dark; texto terciário #94a3b8->#9daabe (4,26->4,64 sobre elevated); disabled #64748b->#8e9cb2;
               link #60a5fa->#6badfb; accent #3b82f6->#4189f7; --sev-critical-text #f87171->#fa8a8a; --sev-critical-border
               #ef4444->#f25050; --sev-info-text #60a5fa->#6badfb; --sev-ok-solid #059669->#047857; família attention entra
               em :root (hoje só existe em Light/HC e o JS cai num fallback fixo).
               DESVIO DECLARADO ao contrato: --color-danger/info/warning/success ficam como estão em Dark. O contrato
               propunha #f25050/#6badfb (papel ícone/borda), mas o template usa-os como FUNDO de botão com texto branco
               em 10 sítios (L1136, 2791, 2892, 2943, 4258, 50794, 50809, 51000, 51229 …): branco sobre #6badfb = 2,5.
               Esses call-sites migram para --sev-*-solid/-on no codemod; só então os semânticos mudam de tom.
 Light         color-scheme:light; disabled #94a3b8->#59697f (2,56->4,5); link #2563eb->#1d4ed8; --sev-ok-text
               #15803d->#166534; --sev-warning-text #b45309->#a3470a (as 2 falhas que restaram no D1); --sev-overflow-text
               #b91c1c->#7f1d1d (deixa de ser igual a critical); e deixa de HERDAR do dark: 12 --color-{success,warning,
               danger,info}{,-bg,-hover} e 18 --sev-*-{border,solid,on} ganham valor claro.
 HC            color-scheme:dark; deixa de herdar navy/azuis do dark: bg-elevated/panel/panel-2/sunken/overlay, hover,
               border-strong, accent, text-inverse/bright/faint/link/disabled, canais RGB, --color-*-bg, --sev-*-on = #000
               (era branco sobre amarelo/verde fluorescente 1,3-1,5), attention-border/-on, família overflow.
               Mesmo desvio que em Dark: --color-danger/info/warning/success continuam a herdar (fundo de botão com texto
               branco; #4da6ff daria 2,2).
               O apagador global de background-image fica (menos risco de esquecer um gradiente); o avatar ganha
               background-color de fallback (sev-info-solid) e texto -on, como o contrato admite.
 Selectores    .gap-card-ico, .gap-pill e .rep-exec-stat b: -solid usado como cor de texto/icone -> -text (Dark: '100%' em
               #047857 deu 2,88 na prova);
               .user-badge .user-role: -disabled -> -tertiary (era "admin/dba" ilegível nos 3 temas);
               .rep-track e .kpi-report-bar .track: borda transparente que em HC passa a branca (trilho visível).

RAMO: design/tokens-contrato (o owner faz checkout antes de aplicar).

Uso (raiz do repo):
  git checkout design/tokens-contrato
  py docs/context/design/D2_CONTRATO_TOKENS_2026-09-18_apply.py --check
  py docs/context/design/D2_CONTRATO_TOKENS_2026-09-18_apply.py
  py -m pytest tests/test_theme_v33_foundation_smoke.py tests/test_live_gap_theming_smoke.py tests/unit/test_live_typography_tokens.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; KPIs e LIVE nos 3 temas
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PORTAL = Path("templates/watcherdb_portal.html")
MARK = "D2 contrato"
# testes que fixavam -solid como cor de texto (passam a fixar -text)
TESTES = {
    Path("tests/test_exec_summary_redesign_smoke.py"): [
        ('        self.assertIn(".rep-exec-stat b.ok { color:var(--sev-ok-solid); }", PORTAL)',
         '        self.assertIn(".rep-exec-stat b.ok { color:var(--sev-ok-text); }", PORTAL)   # D2: -solid nao serve de cor de texto', 1)],
    Path("tests/test_live_gap_theming_smoke.py"): [
        ('        self.assertIn(".gap-pill.crit { background: var(--sev-critical-tint); color: var(--sev-critical-solid); }", PORTAL)',
         '        self.assertIn(".gap-pill.crit { background: var(--sev-critical-tint); color: var(--sev-critical-text); }", PORTAL)   # D2', 1)],
}

EDITS = [
    # ---------------- Dark (:root) ----------------
    ("""        :root {
            /* === CORES BASE === */
""", """        :root {
            color-scheme: dark;   /* D2 contrato: scrollbars, inputs e selects nativos seguem o tema */
            /* === CORES BASE === */
""", 1),
    ("            --color-text-tertiary: #94a3b8;   /* Metadados (6.8:1) */",
     "            --color-text-tertiary: #9daabe;   /* Metadados (D2: 4,64 sobre bg-elevated; era #94a3b8 = 4,26) */", 1),
    ("            --color-text-disabled: #64748b;   /* Texto desabilitado */",
     "            --color-text-disabled: #8e9cb2;   /* Texto desabilitado (D2: só controlos desactivados; era #64748b = 3,07) */", 1),
    ("            --color-text-link:     #60a5fa;   /* links e accents */",
     "            --color-text-link:     #6badfb;   /* links e accents (D2: 4,68 sobre bg-elevated; era #60a5fa = 4,30) */", 1),
    ("            --color-accent:        #3b82f6;   /* T-tabs: barra/borda selecao metric-cards (CPU/Mem/Overview) */",
     "            --color-accent:        #4189f7;   /* T-tabs: barra/borda selecao metric-cards (D2: 3,0 sobre bg-elevated) */", 1),
    ("            --sev-ok-border: #10b981;     --sev-ok-solid: #059669;     --sev-ok-on: #ffffff;",
     "            --sev-ok-border: #10b981;     --sev-ok-solid: #047857;     --sev-ok-on: #ffffff;   /* D2: branco sobre solid 5,48 (era 3,77) */", 1),
    ("            --sev-info-text: #60a5fa;     --sev-info-tint: rgba(37,99,235,0.14);",
     "            --sev-info-text: #6badfb;     --sev-info-tint: rgba(37,99,235,0.14);   /* D2 */", 1),
    ("            --sev-critical-text: #f87171; --sev-critical-tint: rgba(220,38,38,0.15);",
     "            --sev-critical-text: #fa8a8a; --sev-critical-tint: rgba(220,38,38,0.15);   /* D2: 4,72 sobre bg-elevated (era 3,95) */", 1),
    ("            --sev-critical-border: #ef4444;--sev-critical-solid: #dc2626;--sev-critical-on: #ffffff;",
     "            --sev-critical-border: #f25050;--sev-critical-solid: #dc2626;--sev-critical-on: #ffffff;", 1),
    ("""            --sev-overflow-border: #dc2626;--sev-overflow-solid: #7c2d12;--sev-overflow-on: #fecaca;
""", """            --sev-overflow-border: #dc2626;--sev-overflow-solid: #7c2d12;--sev-overflow-on: #fecaca;
            /* D2 contrato: attention existia só em Light/HC; em Dark o JS caía num fallback fixo */
            --sev-attention-text: #fcd34d;  --sev-attention-tint: rgba(234,179,8,0.12);
            --sev-attention-border: #eab308;--sev-attention-solid: #a16207;--sev-attention-on: #ffffff;
""", 1),
    # ---------------- Light ----------------
    ("            --color-text-disabled: #94a3b8;\n",
     "            --color-text-disabled: #59697f;   /* D2: 4,5 sobre bg-tertiary (era #94a3b8 = 2,56) */\n", 1),
    ("            --color-text-link:     #2563eb;\n",
     "            --color-text-link:     #1d4ed8;   /* D2: 5,44 sobre bg-tertiary */\n", 1),
    ("            --sev-ok-text:       #15803d;  --sev-ok-tint: rgba(16,185,129,0.14);",
     "            --sev-ok-text:       #166534;  --sev-ok-tint: rgba(16,185,129,0.14);   /* D2: era #15803d = 4,39 sobre tint */", 1),
    ("            --sev-warning-text:  #b45309;  --sev-warning-tint: rgba(217,119,6,0.14);",
     "            --sev-warning-text:  #a3470a;  --sev-warning-tint: rgba(217,119,6,0.14);   /* D2: era #b45309 = 4,31 sobre bg-sunken */", 1),
    ("            --sev-overflow-text: #b91c1c;  --sev-overflow-tint: rgba(124,45,18,0.12);",
     "            --sev-overflow-text: #7f1d1d;  --sev-overflow-tint: rgba(124,45,18,0.12);   /* D2: distinto de critical */", 1),
    ("""            --sev-attention-text: #854d0e;  --sev-attention-tint: rgba(161,98,7,0.12);
        }
""", """            --sev-attention-text: #854d0e;  --sev-attention-tint: rgba(161,98,7,0.12);
            /* D2 contrato: o que abaixo herdava o dark passa a ter valor claro */
            color-scheme: light;
            --color-success: #166534;  --color-success-bg: #dcfce7;  --color-success-hover: #14532d;
            --color-warning: #a3470a;  --color-warning-bg: #fef3c7;  --color-warning-hover: #92400e;
            --color-danger:  #b91c1c;  --color-danger-bg:  #fee2e2;  --color-danger-hover:  #991b1b;
            --color-info:    #1d4ed8;  --color-info-bg:    #dbeafe;  --color-info-hover:    #1e40af;
            --sev-ok-border: #059669;        --sev-ok-solid: #166534;        --sev-ok-on: #ffffff;
            --sev-info-border: #2563eb;      --sev-info-solid: #1d4ed8;      --sev-info-on: #ffffff;
            --sev-warning-border: #d97706;   --sev-warning-solid: #a3470a;   --sev-warning-on: #ffffff;
            --sev-critical-border: #dc2626;  --sev-critical-solid: #b91c1c;  --sev-critical-on: #ffffff;
            --sev-attention-border: #a16207; --sev-attention-solid: #854d0e; --sev-attention-on: #ffffff;
            --sev-overflow-border: #b91c1c;  --sev-overflow-solid: #7c2d12;  --sev-overflow-on: #ffffff;
        }
""", 1),
    # ---------------- High contrast ----------------
    ("            --color-bg-primary: #000000;  --color-bg-secondary: #0a0a0a;  --color-bg-tertiary: #111111;",
     "            --color-bg-primary: #000000;  --color-bg-secondary: #0a0a0a;  --color-bg-tertiary: #1a1a1a;   /* D2: hover distinguível */", 1),
    ("""            --sev-attention-text:#ffd000; --sev-attention-solid:#ffd000; --sev-attention-tint:rgba(255,208,0,0.15);
        }
""", """            --sev-attention-text:#ffd000; --sev-attention-solid:#ffd000; --sev-attention-tint:rgba(255,208,0,0.15);
            /* D2 contrato: deixa de herdar navy/azuis do dark */
            color-scheme: dark;
            --color-bg-hover: #1f1f1f;  --color-bg-elevated: #0a0a0a;  --color-bg-panel: #0a0a0a;  --card-bg: #0a0a0a;
            --color-bg-panel-2: #111111;  --color-bg-sunken: #000000;  --color-bg-overlay: rgba(0,0,0,0.9);
            --color-border-strong: #ffffff;  --color-accent: #4da6ff;  --color-text-inverse: #000000;
            --color-text-disabled: #a0a0a0;  --color-text-bright: #ffffff;  --color-text-faint: #f0f0f0;  --color-text-link: #4da6ff;
            --rgb-surface-deep: 0 0 0;  --rgb-surface-panel: 10 10 10;
            --color-success-bg: #003320;  --color-warning-bg: #332900;  --color-danger-bg: #330000;  --color-info-bg: #001a33;
            /* texto sobre sólidos fluorescentes: preto (era branco herdado: 1,3-1,5 sobre amarelo/verde) */
            --sev-ok-on: #000000;  --sev-info-on: #000000;  --sev-warning-on: #000000;  --sev-critical-on: #000000;
            --sev-attention-border: #ffd000;  --sev-attention-on: #000000;
            --sev-overflow-text: #ff9999;  --sev-overflow-tint: rgba(255,153,153,0.15);  --sev-overflow-border: #ff9999;  --sev-overflow-solid: #ff9999;  --sev-overflow-on: #000000;
        }
""", 1),
    ("""            background-image: none !important; box-shadow: none !important; text-shadow: none !important;
        }
""", """            background-image: none !important; box-shadow: none !important; text-shadow: none !important;
        }
        /* D2 contrato: trilhos das barras de relatório com fronteira visível em HC */
        html[data-theme="high-contrast"] .rep-track, html[data-theme="high-contrast"] .kpi-report-bar .track { border-color: var(--color-border); }
""", 1),
    # ---------------- selectores ----------------
    ("""        .user-badge .user-avatar {
            width: 28px; height: 28px; border-radius: 50%;
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
            display: flex; align-items: center; justify-content: center;
            color: white; font-size: 12px; font-weight: 700;
""", """        .user-badge .user-avatar {
            width: 28px; height: 28px; border-radius: 50%;
            background-color: var(--sev-info-solid);   /* D2: fallback quando o HC apaga o gradiente */
            background-image: linear-gradient(135deg, #3b82f6, #8b5cf6);
            display: flex; align-items: center; justify-content: center;
            color: var(--sev-info-on); font-size: 12px; font-weight: 700;
""", 1),
    ("        .user-badge .user-role { color: var(--color-text-disabled); font-size: 10px; text-transform: uppercase; }",
     "        .user-badge .user-role { color: var(--color-text-tertiary); font-size: 10px; text-transform: uppercase; }   /* D2: era -disabled */", 1),
    ("        .rep-track { flex:1; height:8px; background:var(--color-bg-tertiary); border-radius:99px; overflow:hidden; }",
     "        .rep-track { flex:1; height:8px; background:var(--color-bg-tertiary); border:1px solid transparent; border-radius:99px; overflow:hidden; }", 1),
    ("        .kpi-report-bar .track { flex:1; height:12px; background:var(--color-bg-tertiary); border-radius:3px; overflow:hidden; }",
     "        .kpi-report-bar .track { flex:1; height:12px; background:var(--color-bg-tertiary); border:1px solid transparent; border-radius:3px; overflow:hidden; }", 1),
    # -solid usado como cor de TEXTO/icone (o contrato reserva -solid a fundos com texto -on). Em Dark, --sev-ok-solid
    # #047857 como texto de "100%" deu 2,88 na prova; -text e' o token certo para estas tres regras.
    ("""        .gap-card.crit .gap-card-ico { color: var(--sev-critical-solid); }
        .gap-card.warn .gap-card-ico { color: var(--sev-warning-solid); }
        .gap-card.info .gap-card-ico { color: var(--sev-info-solid); }
""", """        .gap-card.crit .gap-card-ico { color: var(--sev-critical-text); }   /* D2: -solid nao e' cor de texto/icone */
        .gap-card.warn .gap-card-ico { color: var(--sev-warning-text); }
        .gap-card.info .gap-card-ico { color: var(--sev-info-text); }
""", 1),
    ("""        .gap-pill.crit { background: var(--sev-critical-tint); color: var(--sev-critical-solid); }
        .gap-pill.warn { background: var(--sev-warning-tint); color: var(--sev-warning-solid); }
        .gap-pill.info { background: var(--sev-info-tint); color: var(--sev-info-solid); }
""", """        .gap-pill.crit { background: var(--sev-critical-tint); color: var(--sev-critical-text); }   /* D2 */
        .gap-pill.warn { background: var(--sev-warning-tint); color: var(--sev-warning-text); }
        .gap-pill.info { background: var(--sev-info-tint); color: var(--sev-info-text); }
""", 1),
    ("        .rep-exec-stat b.ok { color:var(--sev-ok-solid); } .rep-exec-stat b.crit { color:var(--sev-critical-solid); } .rep-exec-stat b.warn { color:var(--sev-warning-solid); }",
     "        .rep-exec-stat b.ok { color:var(--sev-ok-text); } .rep-exec-stat b.crit { color:var(--sev-critical-text); } .rep-exec-stat b.warn { color:var(--sev-warning-text); }   /* D2: era -solid como texto */", 1),
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
    if "D1 piloto LIVE" not in portal:
        print("[ABORT] o D1 nao esta aplicado neste template (ramo errado?)"); return 1
    novo = _apply(portal, EDITS, "temas")
    print(f"[ok] {len(EDITS)} blocos: :root (dark) 10, light 6, HC 3, selectores 7")
    testes_novos = {}
    for rel, edits in TESTES.items():
        testes_novos[rel] = _apply((base / rel).read_bytes().decode("utf-8"), edits, str(rel))
    print(f"[ok] {len(TESTES)} testes passam a fixar -text em vez de -solid")
    if check:
        print("--check OK. Nada escrito."); return 0
    src.write_bytes(novo.encode("utf-8")); print(f"[write] {PORTAL}")
    for rel, t in testes_novos.items():
        (base / rel).write_bytes(t.encode("utf-8")); print(f"[write] {rel}")
    print("\nAplicado (ramo design/tokens-contrato). Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; KPIs e LIVE nos 3 temas.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
