# PROMPT PROPAGACAO V6 — Backup Delayed signal-vs-noise (council 2026-09-01)

Colar numa sessao V6. Condicao do v1-intel no council: esta propagacao vai no
MESMO lote das outras (nao fica "V3.3 so"). Portal V6 NAO e' superset — grep
anchors primeiro. Ler o doc do council no V3.3:
docs/context/COUNCIL_BACKUP_DELAYED_SIGNAL_2026-09-01.md (as 4 vozes, as
medicoes M1-M4 e as decisoes R1-R5 — a AI de la' deve compreender o PORQUE,
nao so aplicar o diff).

## O que mudou em V3.3 (commit "feat(v33): Backup Delayed conta sinal")

1. Modulo novo `api/routers/intelligence/backup_delayed_classes.py` —
   classificacao PURA e partilhada entre card e modal. O V6 tem o MESMO loop
   duplicado (WATCHERDB_V6/api/routers/intelligence_kpis.py:1859-1882 e
   3705-3729, ja identificado pelo v1-intel) — portar o modulo e apagar os
   dois loops, exactamente como no V3.3.
2. Regras: R1 dedupe por base no executivo (bases, nao linhas); R2 perdao
   limitado do DIFF (chain-reset so enquanto o FULL esta dentro do warning;
   >168h de DIFF = banda "agendamento DIFF parado"); R3 master/model/msdb de
   nos AG -> classe ag_system_gap com CONTADOR VISIVEL (nunca filtro em
   silencio); R4 sem cap de idade (fosseis morrem via dedupe).
3. CONTRATO CRITICO (v1-intel): correlacao FULL<->DIFF nas linhas
   AG_CONSOLIDATED por **(AgName, Database)** — o Instance da view e' o
   representante POR TIPO e diverge entre tipos pos-failover. Mapa via
   KPI_MSSQL_ALWAYSON_STATUS_STG (AG_MAP_QUERY no modulo). Fail-open: sem
   mapa, cai para (Instance,Database).
4. Frontend: 2 rows novas no tile (bandas warn), 2 pseudo-ids no
   KPI_REPORT_GROUPS (backup-diff-stopped, backup-ag-syswarn) com
   *_by_env (sem isto o filtro de ambiente re-cria o bug FIND-105), badge de
   classe nos cards do modal (rotulos da persona: "Cadeia reiniciada — FULL
   cobre" / "Agendamento DIFF parado" / "Politica por-no (AG)") e linha de
   reconciliacao no sumario (parcelas somam ao total).
5. Teste de contrato: tests/unit/test_backup_delayed_classes_20260901.py —
   portar junto (8 casos, incl. invariante RPO e a prova da chave AG).

## Avisos a AI do V6

- ATENCAO aos thresholds: o V6 tem 120/168 hardcoded onde o V3.3 usa o
  registry — finding ja registado; portar o modulo NAO resolve isso (o modulo
  recebe thresholds por parametro; liga ao que o V6 tiver).
- O numero executivo do V6 vai cair (~40-70%). Obrigatorio: linha de
  reconciliacao + CHANGELOG explicito, como no V3.3 — nunca so o numero a
  mudar (condicao da persona no council).
- NAO "optimizar" as classes para filtros silenciosos: o council proibiu
  explicitamente (3 vozes); as bandas contam no warn do executivo.

## ADDENDUM pos-ship (01-02/09, commits V3.3 e81d929..3944e16) — portar JUNTO

A iteracao com o owner apos o ship acrescentou 7 acertos que fazem parte do
pacote (sem eles o V6 repete as MESMAS queixas que o owner levantou):

1. As 4 linhas do tile abrem a modal PRE-FILTRADA pela classe: tokens
   `CLASS:actionable_critical|actionable_warning|diff_schedule_stopped|
   ag_system_gap` passados como preFilterType e aplicados aos DADOS antes do
   render (mesma regra do pre-filtro FULL/DIFF).
2. `Base_Severity` anotada no modulo (pior severidade da base) e usada na
   particao critico/aviso — a linha segue a BASE, igual ao tile. SEM isto:
   "tile 2 vs modal 5" (linhas warning de bases criticas na modal errada).
3. Charts da modal contam BASES distintas via `data-basekey` no card.
4. Cuidado com o selector das barras: o numero da direita e' o
   `lastElementChild` da row — `querySelector('div:last-child')` apanha o
   PREENCHIMENTO da barra (bug real apanhado pelo owner).
5. Rotulos de unidade nos totais: "Total (bases)" / "Bases distintas (uma
   base pode ter mais de um tipo em atraso)" — 59+55+40 vs 75 sem rotulo
   parece erro de soma.
6. Cross-filter entre charts (tipo+instancia recontam ambiente e vice-versa;
   cada chart ignora o proprio filtro).
7. Cabecalho "Mostrando N bases (M linhas por tipo)" e totais seguem TODOS
   os filtros — cabecalho e totais dos 2 charts dizem sempre o mesmo numero.

8. Bandas de aviso contam BASES (regra R1 tambem nelas):
   `ag_system_gap_count` e `diff_schedule_stopped_count` vem de
   `*_bases_count` do modulo (dedupe por Base_Key; by_env idem) — as listas
   `*_instances` continuam por linha. Medido vivo: AG gap 64 linhas -> 40
   bases -> 17 nos.

Testes novos: test_base_severity_segue_o_pior_da_base +
test_bandas_contam_bases_nao_linhas (11 no total).

## BONUS servico (mesmo lote): mutex-wait no arranque

`watcherdb_service.py` do V6 tem o MESMO defeito de single-instance: o stop
reporta STOPPED antes de o processo morrer e o arranque novo aborta ao
encontrar o mutex ocupado (Restart-Service falha a' primeira). Portar o
retry de 45s com SERVICE_START_PENDING (commit 2ea70ce) — e' o 5o item do
boot hardening de 23/07.
