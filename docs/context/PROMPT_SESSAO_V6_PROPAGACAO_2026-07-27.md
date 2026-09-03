# PROMPT — Sessão V6: propagar as mudanças de 2026-07-23→27

Cola isto na sessão nova (cwd: WATCHERDB_V6):

---

Lê WATCHERDB_V3.3/docs/context/RELATORIO_SESSAO_2026-07-23a25_ANTES_DEPOIS.md (secção
"Plano V6 — checklist de replicação") e o CONTEXT.md (2026-07-23→27). Modo consultor +
handshake. ATENÇÃO: portal V6 NÃO é superset do V3.3 — grep anchors antes de cada item.

## Já feito (NÃO repetir — commits na branch wave-X-integridade do repo V6)
55c1abd Always On→tab alwayson · 487c066 copy 2571 · b6fc1e3 sort categorias ·
91c85a3 filtro severidade nos cards · 68da4b0 opção B (P4 aviso via pseudo-id integrity-p4).
Backend (coletor v3, reconcile, Wave v3.1, hotfix Env PRD/TST, vw_OS_* freshness) HERDA
via BD partilhada — zero código V6.

## A fazer
1. **F3 — modal Integridade "Não Mensurável"** (PROPAGACAO_V6_SESSAO_2026-07-21.md secção F):
   drilldown unmeasurable + gráficos interativos + strip "porque falhou" + i18n + grid — MAS com
   o design REVISTO de 25/07: **"Tipo de Falha" no lugar do gráfico Veredicto** (não implementar
   o Veredicto nesse modal); card 2571 já tem o texto de versão (487c066). Referência de código:
   V3.3 templates/watcherdb_portal.html ~34930 (errnumChartHtml) e ~35011 (assembly).
2. **servers.json local da instalação V6**: verificar se existe cópia própria com descomissionados
   (o V3.3 tinha 99→limpo para 62 em 27/07; ficheiro gitignored — edição no disco + backup datado
   + restart do serviço V6).
3. **Browser-test V6** dos 5 itens já commitados (Always On, 2571, sort, filtro severidade, aviso
   P4=384 na categoria Integridade) — restart do serviço V6 (porta 8660) + Ctrl+F5.
4. **Validar herança BD**: modal Integridade V6 deve mostrar NOT_MEASURABLE=270 e P1=1
   (DW_ODS_TAP); Relatório Técnico V6 sem fantasmas de CPU (vw_OS_*_Current filtradas).
5. No fecho: merge da branch wave-X-integridade a main = decisão do maintainer (precedente
   wave-T); CHANGELOG V6; antes/depois.
