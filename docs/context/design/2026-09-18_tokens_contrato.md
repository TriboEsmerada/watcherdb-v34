# Contrato de tokens de cor — Dark / Light / High-contrast

Data: 2026-09-18 | Autor: ux-design-reviewer (advisor, nada aplicado) | Escopo: só tema/contraste
Mockup: `docs/context/design/mockups/2026-09-18_tokens_swatches.html` (ratios calculados em JS na página)
Evidência: `docs/context/design/capturas/2026-09-18/auditoria_contraste.json` + PNGs na mesma pasta (DEV 8434, dados fictícios)

## 1. Factos verificados (ficheiro:linha)

| Facto | Onde |
|---|---|
| `:root` define 32 `--color-*`, 25 `--sev-*` (ok/info/warning/critical/overflow × text/tint/border/solid/on), 2 `--rgb-*` | `templates/watcherdb_portal.html:61-121` |
| **`--sev-attention-*` não existe em `:root`** — só em Light (L245: text+tint) e HC (L257: text+solid+tint); em Dark o JS cai no fallback fixo `#d97706/#fbbf24` | L35663 `ATTENTION:{ fill: g('--sev-attention-solid') \|\| '#d97706' ...}` |
| Light (L215-246) não redefine `--color-{danger,info,success,warning}{,-bg,-hover}` nem `--sev-*-{solid,border,on}` → herda valores dark | L215-246 vs L74-88, L104-118 |
| HC (L249-258) não redefine `--color-bg-panel` (topbar fica navy `#1e293b`), `--color-bg-elevated/-hover/-sunken`, `--color-text-link/-disabled/-bright`, `--color-accent`, e não define `--sev-*-on` → herda `#ffffff` sobre sólidos claros (`#fff` sobre `#ffcc00` = **1,51:1**) | L249-258 |
| `html[data-theme="high-contrast"] * { background-image:none !important }` apaga o gradiente do avatar (L3848 `linear-gradient(135deg,#3b82f6,#8b5cf6)`) → círculo transparente, iniciais brancas sobre branco em Light-HC (auditoria: ratio 1,0) | L259-261, L3846-3851 |
| `color-scheme` não declarado (computado `normal`) → scrollbars/inputs nativos escuros no Light | auditoria `tokens_cssom.color_scheme = "normal"` |
| `.rep-track` usa `--color-bg-tertiary` (HC `#111` sobre card `#0a0a0a` = **1,05:1**) | L1916, L251 |
| `.crit-bell-badge` `#fff` sobre `#ef4444` fixo (3,76:1 a 11px) | L696 |
| `.user-role` usa `--color-text-disabled` para metadado (não é controlo desactivado): dark 3,12 / light 2,56 / HC 3,33 | L3853 |
| `.vl` (105, 9, 42…) recebe cor inline `#ef4444`/`#3b82f6` a 12px: dark 4,19/4,29, light 3,76/3,68 | L1865, L1918 + inline nos geradores |
| LIVE usa `var(--color-border)` como **cor de texto** nos chips MEM/PLE (dark `#334155` sobre `#1e293b` = 1,41; light 1,48) e `--color-border-strong` no relógio (2,73) | auditoria live.worst (dark/light/HC) — localização exacta fica para o frontend-specialist |

Resultado hoje (auditoria): KPIs dark 7/125, light 7/124, HC 2/124 falhas AA; LIVE dark 43/280, light 56/280, HC 34/281.

## 2. Princípios do contrato

1. **Três papéis por severidade**: `-text` (texto sobre fundo do tema, ≥4,5:1 em primary/panel/elevated), `-solid` (fundo sólido; texto = `-on`, ≥4,5:1), `-tint` (fundo suave para chips/linhas; texto = `-text`, ≥4,5:1). `-border` fica para bordas/ícones/barras (≥3:1 UI).
2. **`--color-{success,warning,danger,info}` passam a ser tokens de UI (ícone/borda/barra, 3:1)** — nunca texto. Texto usa `--sev-*-text`. Os `-bg` são fundos de caixa com `--color-text-primary` por cima; os `-hover` são o estado hover da UI.
3. **`--color-text-disabled` só em controlos desactivados** (isento WCAG 1.4.3). Metadado (`.user-role`, chips PRD/TST, "30d idle") usa `--color-text-tertiary`.
4. Cada tema redefine **todos** os tokens (nada herda do dark por omissão). `color-scheme` declarado por tema.
5. Meta: AA em todos os pares texto/fundo listados, nos três temas. Onde o valor de hoje falha, o novo valor está a negrito na secção 5.

## 3. Fundos e bordas por tema

| Token | Dark (hoje = igual) | Light | HC (novo onde marcado) |
|---|---|---|---|
| --color-bg-primary | `#0a0f1a` | `#eef2f7` | `#000000` |
| --color-bg-secondary | `#1a2332` | `#ffffff` | `#0a0a0a` |
| --color-bg-tertiary / -hover | `#243447` | `#e2e8f0` | **`#1a1a1a`** / **`#1f1f1f`** (hoje `#111`/herda) |
| --color-bg-elevated | `#2d3e52` | `#ffffff` | **`#0a0a0a`** (hoje herda `#2d3e52`) |
| --color-bg-panel / --card-bg | `#1e293b` | `#ffffff` | **`#0a0a0a`** (hoje herda navy → topbar) |
| --color-bg-panel-2 | `#1f2937` | `#f1f5f9` | **`#111111`** |
| --color-bg-sunken | `#0f172a` | `#e9eef5` | **`#000000`** |
| --color-bg-overlay | `rgba(10,15,26,.9)` | `rgb(241 245 249 / .45)` | **`rgba(0,0,0,.9)`** |
| --color-border / -strong | `#334155` / `#475569` | `#cbd5e1` / `#94a3b8` | `#ffffff` / **`#ffffff`** |
| --color-accent | **`#4189f7`** (hoje `#3b82f6`: 2,97 sobre elevated) | `#2563eb` | **`#4da6ff`** |
| --color-text-inverse | `#0a0f1a` | `#f8fafc` | **`#000000`** |
| --rgb-surface-deep / -panel | `15 23 42` / `30 41 59` | `241 245 249` / `255 255 255` | **`0 0 0` / `10 10 10`** |
| `color-scheme` | **`dark`** | **`light`** | **`dark`** |

Bordas neutras não têm exigência de 3:1 (não delimitam controlos sozinhas); `.rep-track` e inputs em HC ganham borda branca explícita (secção 6).

## 4. Texto neutro

### Neutros (texto sobre fundos) - ratio minimo entre bg-primary / bg-secondary / bg-panel / bg-elevated / bg-tertiary
| Token | Dark | Light | HC | min Dark | min Light | min HC |
|---|---|---|---|---|---|---|
| --color-text-primary | `#f1f5f9` | `#0f172a` | `#ffffff` | 9.97 (elevated) | 14.48 (tertiary) | 17.4 (tertiary) |
| --color-text-secondary | `#cbd5e1` | `#334155` | `#f0f0f0` | 7.36 (elevated) | 8.4 (tertiary) | 15.27 (tertiary) |
| --color-text-tertiary | **`#9daabe`** (hoje `#94a3b8`: 4,26 sobre elevated) | `#475569` | `#d0d0d0` | 4.64 (elevated) | 6.15 (tertiary) | 11.28 (tertiary) |
| --color-text-disabled | **`#8e9cb2`** (hoje `#64748b`: 3,07) | **`#59697f`** (hoje `#94a3b8`: 2,56) | **`#a0a0a0`** (hoje herda) | 3.93 (elevated — isento, só disabled) | 4.54 (tertiary) | 6.66 (tertiary) |
| --color-text-bright | `#e2e8f0` | `#0f172a` | **`#ffffff`** | 8.86 (elevated) | 14.48 (tertiary) | 17.4 (tertiary) |
| --color-text-faint | `#e5e7eb` | `#475569` | **`#f0f0f0`** | 8.82 (elevated) | 6.15 (tertiary) | 15.27 (tertiary) |
| --color-text-link | **`#6badfb`** (hoje `#60a5fa`: 4,30 sobre elevated) | **`#1d4ed8`** (hoje `#2563eb`: 4,1 sobre hover) | `#4da6ff` | 4.68 (elevated) | 5.44 (tertiary) | 6.81 (tertiary) |

## 5. Semânticos de UI e escala de severidade

### Semanticos --color-* (papel: UI/icone/borda, 3:1) - ratio minimo sobre bg-secondary/panel/elevated
| Token | Dark | Light | HC | min Dark | min Light | min HC |
|---|---|---|---|---|---|---|
| --color-success | `#10b981` | **`#166534`** | **`#00ff88`** | 4.31 | 7.13 | 14.76 |
| --color-success-hover | `#34d399` | **`#14532d`** | **`#66ffb2`** | 5.68 | 9.11 | 15.57 |
| --color-warning | **`#f59e0b`** (hoje `#d97706`) | **`#a3470a`** | **`#ffcc00`** | 5.09 | 6.06 | 13.09 |
| --color-warning-hover | **`#fbbf24`** | **`#92400e`** | **`#ffe066`** | 6.54 | 7.09 | 15.18 |
| --color-danger | **`#f25050`** (hoje `#dc2626`: 3,27 / 2,9 elevated) | **`#b91c1c`** | **`#ff6666`** | 3.14 | 6.47 | 6.92 |
| --color-danger-hover | **`#fa8a8a`** | **`#991b1b`** | **`#ff9999`** | 4.72 | 8.31 | 9.68 |
| --color-info | **`#6badfb`** (hoje `#2563eb`: 3,05) | **`#1d4ed8`** | **`#4da6ff`** | 4.68 | 6.7 | 7.74 |
| --color-info-hover | **`#93c5fd`** | **`#1e40af`** | **`#80c0ff`** | 6.06 | 8.72 | 10.28 |
| --color-success-bg (texto primario por cima) | `#064e3b` | **`#dcfce7`** | **`#003320`** | 8.87 | 16.26 | 14.05 |
| --color-warning-bg (texto primario por cima) | `#78350f` | **`#fef3c7`** | **`#332900`** | 8.28 | 16.03 | 14.4 |
| --color-danger-bg (texto primario por cima) | `#7f1d1d` | **`#fee2e2`** | **`#330000`** | 9.15 | 14.61 | 18.41 |
| --color-info-bg (texto primario por cima) | `#1e3a8a` | **`#dbeafe`** | **`#001a33`** | 9.45 | 14.63 | 17.56 |

Nota dark: `--color-danger` `#dc2626` → `#f25050` e `--color-info` `#2563eb` → `#6badfb` são as duas mudanças com mais superfície (ícones/bordas ficam mais claros). Se o owner preferir zero mudança visual nos ícones dark, alternativa: manter `#ef4444`/`#3b82f6` e aceitar 2,9/2,7 só sobre `bg-elevated` (modais).

### Severidades --sev-* (ratios: -text/panel, -text/elevated, -on/-solid, -text/-tint, -border UI/panel)
| Severidade | Variante | Dark | Light | HC | Dark ratios | Light ratios | HC ratios |
|---|---|---|---|---|---|---|---|
| critical | -text | **`#fa8a8a`** (hoje `#f87171`: 3,95 elevated) | `#b91c1c` | `#ff6666` | 6.32 / 4.72 | 6.47 / 6.47 | 6.92 / 6.92 |
| critical | -tint | `rgba(220,38,38,0.15)` | `rgba(220,38,38,0.1)` | `rgba(255,102,102,0.15)` | text/tint 5.83 (tint=#3a2938) | text/tint 5.54 (tint=#fce9e9) | text/tint 5.81 (tint=#2f1818) |
| critical | -border | **`#f25050`** (hoje `#ef4444`) | **`#dc2626`** | `#ff6666` | UI 4.21 | UI 4.83 | UI 6.92 |
| critical | -solid | `#dc2626` | **`#b91c1c`** | `#ff6666` | on/solid 4.83 | on/solid 6.47 | on/solid 7.34 |
| critical | -on | `#ffffff` | **`#ffffff`** | **`#000000`** (hoje herda `#fff`: 2,86) | - | - | - |
| warning | -text | `#fbbf24` | **`#a3470a`** (hoje `#b45309`: 4,33 sobre tint) | `#ffcc00` | 8.76 / 6.54 | 6.06 / 6.06 | 13.09 / 13.09 |
| warning | -tint | `rgba(245,158,11,0.13)` | `rgba(217,119,6,0.14)` | `rgba(255,204,0,0.15)` | text/tint 7.0 (tint=#3a3835) | text/tint 5.23 (tint=#faecdc) | text/tint 9.82 (tint=#2f2708) |
| warning | -border | `#f59e0b` | **`#d97706`** | `#ffcc00` | UI 6.81 | UI 3.19 | UI 13.09 |
| warning | -solid | `#d97706` | **`#a3470a`** | `#ffcc00` | on/solid 6.01 | on/solid 6.06 | on/solid 13.89 |
| warning | -on | `#0a0f1a` | **`#ffffff`** (hoje herda `#0a0f1a`: 3,82 sobre `#b45309`) | **`#000000`** (hoje herda `#fff`: 1,51) | - | - | - |
| attention | -text | **`#fcd34d`** (novo em :root) | `#854d0e` | `#ffd000` | 10.15 / 7.58 | 6.85 / 6.85 | 13.46 / 13.46 |
| attention | -tint | **`rgba(234,179,8,0.12)`** | `rgba(161,98,7,0.12)` | `rgba(255,208,0,0.15)` | text/tint 8.03 (tint=#363a35) | text/tint 5.85 (tint=#f4ece1) | text/tint 10.0 (tint=#2f2808) |
| attention | -border | **`#eab308`** | **`#a16207`** | **`#ffd000`** | UI 7.63 | UI 4.92 | UI 13.46 |
| attention | -solid | **`#a16207`** | **`#854d0e`** | `#ffd000` | on/solid 4.92 | on/solid 6.85 | on/solid 14.27 |
| attention | -on | **`#ffffff`** | **`#ffffff`** | **`#000000`** | - | - | - |
| ok | -text | `#34d399` | **`#166534`** (hoje `#15803d`: 4,39 sobre tint) | `#00ff88` | 7.61 / 5.68 | 7.13 / 7.13 | 14.76 / 14.76 |
| ok | -tint | `rgba(16,185,129,0.12)` | `rgba(16,185,129,0.14)` | `rgba(0,255,136,0.15)` | text/tint 6.29 (tint=#1c3a43) | text/tint 6.24 (tint=#def5ed) | text/tint 10.92 (tint=#082f1d) |
| ok | -border | `#10b981` | **`#059669`** | `#00ff88` | UI 5.77 | UI 3.77 | UI 14.76 |
| ok | -solid | **`#047857`** (hoje `#059669`: branco 3,77) | **`#166534`** | `#00ff88` | on/solid 5.48 | on/solid 7.13 | on/solid 15.66 |
| ok | -on | `#ffffff` | **`#ffffff`** | **`#000000`** (hoje herda `#fff`: 1,34) | - | - | - |
| info | -text | **`#6badfb`** (hoje `#60a5fa`: 4,30 elevated) | `#1d4ed8` | `#4da6ff` | 6.27 / 4.68 | 6.7 / 6.7 | 7.74 / 7.74 |
| info | -tint | `rgba(37,99,235,0.14)` | `rgba(37,99,235,0.1)` | `rgba(77,166,255,0.15)` | text/tint 5.53 (tint=#1f3154) | text/tint 5.82 (tint=#e9effd) | text/tint 6.38 (tint=#14212f) |
| info | -border | `#3b82f6` | **`#2563eb`** | `#4da6ff` | UI 3.98 | UI 5.17 | UI 7.74 |
| info | -solid | `#2563eb` | **`#1d4ed8`** | `#4da6ff` | on/solid 5.17 | on/solid 6.7 | on/solid 8.21 |
| info | -on | `#ffffff` | **`#ffffff`** | **`#000000`** (hoje herda `#fff`: 2,56) | - | - | - |
| overflow | -text | `#fca5a5` | **`#7f1d1d`** (hoje `#b91c1c` = critical) | **`#ff9999`** (novo) | 7.71 / 5.76 | 10.02 / 10.02 | 9.68 / 9.68 |
| overflow | -tint | `rgba(124,45,18,0.3)` | `rgba(124,45,18,0.12)` | **`rgba(255,153,153,0.15)`** | text/tint 7.13 (tint=#3a2a2f) | text/tint 8.16 (tint=#efe6e3) | text/tint 7.68 (tint=#2f1f1f) |
| overflow | -border | `#dc2626` | **`#b91c1c`** | **`#ff9999`** | UI 3.03 | UI 6.47 | UI 9.68 |
| overflow | -solid | `#7c2d12` | **`#7c2d12`** | **`#ff9999`** | on/solid 6.48 | on/solid 9.37 | on/solid 10.27 |
| overflow | -on | `#fecaca` | **`#ffffff`** | **`#000000`** | - | - | - |

Pares fora da meta e porquê: `--color-text-disabled` dark sobre `bg-elevated` 3,93 (isento — só controlos desactivados; metadado migra para tertiary). `-solid` contra o painel (dark ok 2,67 / info 2,83 / attention 2,97 / overflow 1,56) é informativo: o sólido carrega texto `-on` a ≥4,5 e não é fronteira de controlo; se o sólido for usado como *barra* sem texto (rep-fill), usar `-border`.

### O que muda visualmente (resumo por tema)

- **Dark**: metadados um tom mais claros (`#94a3b8`→`#9daabe`); links e números info mais claros (`#60a5fa`→`#6badfb`); vermelho de texto mais rosado (`#f87171`→`#fa8a8a`) e ícones/bordas de perigo mais claros (`#ef4444`→`#f25050`); botão OK sólido mais escuro (`#059669`→`#047857`). Fundos intactos.
- **Light**: verde e laranja de texto mais escuros (`#15803d`→`#166534`, `#b45309`→`#a3470a`); "admin/dba" e outros disabled legíveis (`#94a3b8`→`#59697f`); botões sólidos deixam de herdar cores dark (Ping/OK sólido passa a verde-800 com texto branco 7,1:1).
- **HC**: topbar e painéis passam de navy a preto (`--color-bg-panel`); texto sobre sólidos passa a **preto** (era branco sobre amarelo 1,5:1); trilhos com borda branca; avatar mantém disco azul sólido.

## 6. Blocos CSS propostos (NÃO aplicados — diff para o frontend-specialist)

```css
/* :root — completar attention (hoje só existe em light/HC) e color-scheme */
:root { color-scheme: dark;
  --sev-attention-text:#fcd34d; --sev-attention-tint:rgba(234,179,8,.12);
  --sev-attention-border:#eab308; --sev-attention-solid:#a16207; --sev-attention-on:#ffffff; }
html[data-theme="light"] { color-scheme: light; /* + os 12 --color-{success,warning,danger,info}{,-bg,-hover} e os 18 --sev-*-{solid,border,on} da secção 5 */ }
html[data-theme="high-contrast"] { color-scheme: dark; /* + os 25 --color-* em falta (secção 3/4) e --sev-*-on:#000000 */ }

/* HC — substituir o apagador global (L259-261) por selectores específicos */
html[data-theme="high-contrast"] .card, html[data-theme="high-contrast"] .kpi-card,
html[data-theme="high-contrast"] .modal-content, html[data-theme="high-contrast"] .rep-row,
html[data-theme="high-contrast"] .nav-btn, html[data-theme="high-contrast"] .topbar
  { background-image:none !important; box-shadow:none !important; text-shadow:none !important; }
/* e, em qualquer caso, fallback de cor no avatar (L3848) */
.user-badge .user-avatar { background-color: var(--sev-info-solid); background-image: linear-gradient(135deg,#3b82f6,#8b5cf6); color: var(--sev-info-on); }

/* .rep-track (L1916) e .kpi-report-bar .track (L1863): fronteira visível em HC */
.rep-track, .kpi-report-bar .track { background: var(--color-bg-tertiary); border: 1px solid transparent; }
html[data-theme="high-contrast"] .rep-track, html[data-theme="high-contrast"] .kpi-report-bar .track { border-color: var(--color-border); }

/* Quick wins de selector (sem tocar JS) */
.user-badge .user-role { color: var(--color-text-tertiary); }          /* L3853: era text-disabled */
.crit-bell-badge { background: var(--sev-critical-solid); color: var(--sev-critical-on); } /* L696 */
.kpi-report-bar.sel .nm, .rep-row:hover, .rep-row:focus-visible, .kpi-report-bar[role="button"]:focus-visible
  { /* #93c5fd / #3b82f6 fixos (L1869-1872, L1921-1922) → var(--sev-info-text) / var(--color-accent) */ }
```

Se manter o apagador global do HC for preferível (menos risco de esquecer um gradiente), a linha do avatar com `background-color` chega — `background-image:none` deixa o `background-color` intacto.

## 7. Entregável 2 — piloto LIVE em Light: cor fixa → token

Contagens medidas em `_liveRender*` (L47000-52100) por propriedade CSS onde a cor aparece. A regra: `color:` → `-text`; `background:` com texto branco por cima → `-solid` (+ texto `-on`); `background:` de chip/linha → `-tint`; `border*:` → `-border`.

| Cor fixa | Ocorrências (color / background / borda) | Token de destino | Nota |
|---|---|---|---|
| `#10b981` | 25 (10 / 12 / —) | `color:` → `--sev-ok-text`; `background:` → `--sev-ok-solid` + `color: var(--sev-ok-on)` se tiver texto branco, senão `--sev-ok-tint` | em Light hoje é 2,54:1 como texto |
| `#059669` | 14 (3 / 11 / —) | `background:` → `--sev-ok-solid`; `color:` → `--sev-ok-text` | dark `#059669` com branco = 3,77 → sólido passa a `#047857` |
| `#4ade80` | 2 (color) | `--sev-ok-text` | |
| `#ef4444` | 17 (11 / 3 / box-shadow 1) | `color:` → `--sev-critical-text`; `background:` → `--sev-critical-solid` + `-on`; box-shadow → `var(--sev-critical-border)` | |
| `#dc2626` | 6 (2 / 1 / border 3) | `border` → `--sev-critical-border`; `background` → `--sev-critical-solid`; `color` → `--sev-critical-text` | |
| `#fca5a5` | 6 (color) | `--sev-critical-text` quando está sobre `#7f1d1d`/tint; `--sev-overflow-text` quando o contexto é overflow (Sched/fila) | Light hoje: rosa sobre branco ilegível |
| `#7f1d1d` | 4 (background) | `--color-danger-bg` (caixa com `--color-text-primary` por cima) — **não** `-tint` (é caixa de aviso, não chip) | Light `#fee2e2` |
| `#3b82f6` | 17 (7 / 9 / border 1) | `color:` → `--sev-info-text`; `background:` de botão (`.live-prog-btn`) → `--sev-info-solid` + `-on`; border → `--sev-info-border` | HC hoje: branco sobre `#3b82f6` 3,68 |
| `#2563eb` | 5 (1 / 4 / —) | `background` → `--sev-info-solid`; `color` → `--sev-info-text` | |
| `#60a5fa` | 2 (color) | `--sev-info-text` (ou `--color-text-link` se for link) | |
| `#1e3a5f` | 4 (background) | `--sev-info-tint` (fundo de opção seleccionada/hover) | Light `#e9effd` |
| `#f59e0b` | 14 (9 / 1 / border-bottom 1) | `color:` → `--sev-warning-text`; `background` → `--sev-warning-solid` + `-on`; border → `--sev-warning-border` | Light hoje 2,15:1 — o pior caso do LIVE |
| `#d97706` | 2 (color) | `--sev-warning-text` | |
| `#fcd34d` | 2 (color) | `--sev-attention-text` (valor de aviso editável na modal de limiares) | exige attention em `:root` |
| `#f8fafc` | 2 (background) | `--color-bg-panel` (ou `--color-bg-sunken`) — as 2 ocorrências são o **relatório imprimível** (~L49131, L49158), não o modal | não faz parte do piloto |
| `#e2e8f9` | 2 (color) | `--color-text-primary` (inputs ~L47466, L47585 — fora do modal LIVE) | não faz parte do piloto |

Para o frontend-specialist, além das cores: os chips MEM/PLE usam `var(--color-border)` como cor de texto (ratio 1,41/1,48) → `--color-text-tertiary`; o relógio usa `--color-border-strong` → `--color-text-tertiary`; os rótulos de ambiente PRD/TST/QLT usam `--color-text-disabled` → `--color-text-tertiary`.

## 8. Cinco inovações ranqueadas (impacto ÷ esforço), só tema/contraste

| # | Proposta | Referência | Porquê no WatcherDB | Impacto / Esforço |
|---|---|---|---|---|
| 1 | **Teste de guarda de contraste no pytest**: ler o `:root` e os dois overrides do template com regex, calcular os pares deste contrato e falhar abaixo de AA. Zero browser, zero dependência. | Grafana `@grafana/ui` corre `wcag-contrast` sobre os tokens no CI | Fecha o ciclo: o contrato deixa de ser documento e passa a gate, como os testes de guarda i18n (886/294) | Alto / Baixo (≈80 linhas Python) |
| 2 | **`data-sev="crit\|warn\|ok\|info\|attn"` + 3 classes utilitárias** (`.sev-text`, `.sev-solid`, `.sev-tint`) que resolvem para os tokens — os geradores JS emitem atributo, não hex. | Datadog/Linear: status como atributo semântico, cor decidida no CSS | Torna o codemod das 517+469 ocorrências mecânico e revisável (`style="color:#ef4444"` → `data-sev="crit" class="sev-text"`) e garante que HC/Light nunca mais herdam dark | Alto / Médio |
| 3 | **`color-scheme` + `accent-color: var(--color-accent)`** no `html` por tema | Plataforma (CSS Color Adjust L1) | Scrollbars, checkboxes, `<select>` e date pickers nativos seguem o tema sem CSS custom — resolve a barra escura no Light de graça | Médio / Trivial |
| 4 | **Ícone/forma junto à cor nos números de severidade** (`.vl` e chips): prefixo `▲ ▼ ●` ou sufixo textual já existente ("crit") com `aria-label` | WCAG 1.4.1; Grafana stat panel usa ícone+cor | 8% dos DBAs homens com daltonismo; em HC as três severidades amarelas (`#ffcc00`/`#ffd000`) são indistinguíveis só pela cor | Médio / Baixo |
| 5 | **Auditoria Playwright de contraste como script em `tools/`** que gera o mesmo JSON de hoje (KPIs + LIVE, 3 temas) e escreve o resumo em `docs/context/design/capturas/<data>/` | Datadog "a11y snapshots" por PR | Repetível antes de cada lote de codemod; o número de falhas (7/7/2 e 43/56/34) passa a métrica de release | Médio / Médio |

Fora deste relatório por decisão de escopo: as 517 `#ef4444` / 469 `#3b82f6` do resto do template (codemod após o contrato), e qualquer UI Pro.
