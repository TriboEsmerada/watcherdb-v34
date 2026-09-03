# PROMPT — Próxima sessão V3.3 (docs KPIs + accordion Relatório Técnico + D3)

Cola isto na sessão nova:

---

Lê docs/context/CONTEXT.md (entradas 2026-07-23→27) e docs/context/RELATORIO_SESSAO_2026-07-23a25_ANTES_DEPOIS.md. Trabalha em OODA, modo consultor + handshake, memórias owner activas (panorama sempre; BD⇒canonical+docs; commit sempre + plano V6; antes/depois no fecho).

## Itens, por prioridade

1. **Documentação dos KPIs (modal "Documentação dos KPIs")** — audit 27/07: 3 cards SEM doc
   (`backup-log-failed`, `backup-no-checksum`, `mirroring-unhealthy`); menu com nomes EN antigos
   ("DB Not Availability", "Instances OK", "Blocked Sessions") vs cards PT — alinhar nomenclatura
   1:1 com os cards; rever cada texto para linguagem simples e cobertura das mudanças da sessão
   23-25/07 (erro 2571 = limitação de versão SQL <2016SP2, NÃO permissão; P4 CHECKDB>30d conta
   como aviso; modal Não Mensurável tem "Tipo de Falha" no lugar do Veredicto). pt/en/es.
   Dispatch: docs-writer + v33-i18n-coverage. Âncoras: KPI_DOCUMENTATION e KPI_METADATA no
   templates/watcherdb_portal.html (~37664 e ~32060).
2. **Accordion drill-down nas modais do Relatório Técnico** (pedido owner 25/07) — aplicar o
   design F1 (docs/context/DESIGN_ACCORDION_MODAIS_2026-07-23.md; decisão: TODAS as modais,
   rollout faseado). Renderer do relatório: renderKpiReport/kpiReportOpen (~33614+). Browser-test
   obrigatório antes de shipped.
3. **D3 — sidebar/fonte única**: /api/v3/servers passar a ler da INST_ENVS reconciliada (BD como
   fonte; elimina a 3ª cópia servers.json local por máquina — limpa 27/07 para 62, mas volta a
   divergir sem isto). Gate v1-intel se tocar em queries partilhadas.
4. Decisões pequenas: OATXP01 (monitorizado no V1, invisível no portal — manter/expor/descomissionar);
   typo SS301 (JSON id 1-S vs @@SERVERNAME 2-S — corrigir id no servers.json V1, pipeline migra);
   flip DRY_RUN=False do reconcile_inst_envs.py se a semana de dry-run (desde 24/07) estiver limpa
   (rever logs [Reconcile]); tables: órfã KPI_OS_DISK_STG no config.yaml do serviço.

## Contexto operacional
- Reconcile diário corre 03h+ em dry-run; purge manual já feito (INST_ENVS=64).
- vw_OS_*_Current com filtro 30 min (2.25.2) — Relatório Técnico só frota viva.
- Branch: wave-y/sessao-2026-07-21-22 (23 commits da sessão anterior, nunca pushed).
