# PROMPT — Sprint: Tema Claro (Claro/Escuro) no portal V3.3

> **ESTADO: v1 IMPLEMENTADO 2026-06-17 (commit efa3c7b).** Feito: tokenização dos
> **neutros** (3412 `#hex` → `--color-*` com valor dark exato) + 72 fundos `rgba()`
> escuros → `rgb(var(--rgb-surface-*)/alpha)` + bloco `html[data-theme="light"]` +
> `applyTheme`/`cycleTheme` + toggle no cabeçalho dos KPIs + i18n. Dark = zero
> regressão (valores dark preservados). **FALTA (iteração):** tokenizar a
> **severidade/acento** (vermelhos/âmbar/verdes/azuis/roxos #hex e tints `rgba`)
> para contraste fino no claro — hoje ficam iguais nos dois temas (sólidos OK em
> claro; textos de severidade claros podem ter contraste fraco). O texto abaixo é o
> plano original/completo; usar para a 2ª vaga (severidade + QA portal-wide).

---


> Colar numa sessão Claude Code dedicada **com browser** (verificação visual é o gate).
> Tarefa **frontend** + QA portal-wide. Origem: pedido do user 2026-06-17 ao portar a
> vista Avançada + Relatório Técnico dos KPIs (commit `d4f5155`) — faltava o seletor
> Claro/Escuro que o V6 tem. Foi **adiado de propósito** para sprint próprio porque
> não é "só o botão".

## Porquê é um sprint, não um botão

Medição 2026-06-17 em `templates/watcherdb_portal.html`:

| Métrica | Valor |
|---|---|
| `var(--color-*)` (tokenizado) | **251** |
| Cores hex fixas inline (`#xxxxxx`) | **7260** |
| `background` inline com hex | 953 |

O portal V3.3 é **~97% dark hardcoded**. Um tema claro por troca de tokens
(`[data-theme="light"]`) só afeta ~251 sítios e deixa **~7000 cores escuras fixas**
→ caixas/texto escuros sobre fundo claro = modo claro **partido**. Entregar isso
viola a regra "cada feature funciona como demo a cliente pagante / nunca fingir".

(O V6 só tem Claro/Escuro porque **já está tokenizado** — usar como modelo.)

## Objetivo

Tema **Claro** selecionável (paridade com o V6), banking-grade (WCAG 2.1 AA — banking
audita contraste), **zero regressão** no dark atual. Seletor Claro/Escuro no cabeçalho
dos KPIs (e/ou global), tal como o V6.

## Abordagem faseada (QA visual a cada lote — zero regressão dark)

1. **Inventário** — mapear as ~7260 cores hex por ecrã/componente; reduzir à paleta
   real (quantas cores distintas? provavelmente poucas dezenas). Agrupar em tokens.
2. **Tokenizar** — substituir hex → `var(--color-*)` / `var(--sev-*)` (criar os
   `--sev-*` no portal; hoje só existem no `Claude Design/` kit, não no portal). Fazer
   **por ecrã/tab**, validando o dark a cada lote (tem de ficar idêntico).
3. **Paleta clara** — `[data-theme="light"]` com overrides dos tokens; espelhar os
   light overrides do V6 (`:root` claro). Garantir contraste AA.
4. **Mecânica** — `applyTheme()`/`cycleTheme()` + `data-theme` no `<html>` +
   persistência `localStorage` + seguir `prefers-color-scheme` na 1ª vez.
5. **Seletor** — segmented control Claro/Escuro no cabeçalho dos KPIs (`.kpi-layout-seg`
   já lá está como referência de estilo) e/ou global.
6. **QA** — TODOS os tabs (Overview, Performance, Space, Backup, AlwaysOn, SQL Diag,
   Service Logs, KPIs Simples+Avançado, Relatório Técnico…) em **ambos** os temas;
   modais; gráficos Chart.js.

## Riscos conhecidos

- **Chart.js**: cores hardcoded nos datasets → ler do tema (CSS vars via getComputedStyle).
- **Inline styles gerados em JS**: muitos `style="background:#..."` em template strings.
- **SVG**: `var()` NÃO resolve em atributos `fill=`/`stroke=` → usar `style="fill:var(...)"`.
- **Severidade**: criar `--sev-*` no portal e usar (a vista Avançada + Relatório dos
  KPIs usam hoje hex de severidade — passariam a token nesta sprint).

## Referências

- Modelo tokenizado: **WATCHERDB_V6** `templates/watcherdb_portal.html` (`:root` +
  light overrides + `data-theme` + `applyTheme`/`cycleTheme`).
- Design kit V3.3: `Claude Design/kit.jsx` (`--sev-*` + paleta), `severity.css`.
- Feature já portada que ganha tema: KPIs vista Avançada + Relatório Técnico (commit `d4f5155`).

## Aceitação

- Dark **idêntico** ao atual (zero regressão visual).
- Claro **consistente** em todos os ecrãs (sem ilhas escuras), WCAG AA.
- Toggle persiste; segue o sistema na 1ª vez.
- Banking GA / backward compat preservados.
