# PROMPT — Próxima sessão V3.3 (pós-maratona 2026-07-27)

Cola isto na sessão nova:

---

Lê docs/context/CONTEXT.md (entradas 2026-07-27 — foram ~20, sessão grande) e
executa em OODA, modo consultor + GO por lote, memórias owner activas
(panorama sempre; nome-não-número nas modais; validação node 12/12 + py ast;
BD⇒canonical+docs; commit sempre + plano V6; antes/depois no fecho).

## Itens, por prioridade

1. **Pacote aba Space (6 pedidos owner)** — spec executável completa com
   anchors em docs/context/PROMPT_SESSAO_SPACE_2026-07-28.md: ordenação nas 3
   tabelas do drilldown, Free MB/% EFETIVO com a matriz do growth (growth
   ativo+max finito = Σmax−usado; growth=0 = alocado−usado; unlimited =
   disk-bound), Status FULL/MAXED nos datafiles, coluna Used MB (reescrever
   query de files p/ USE+FILEPROPERTY; ag_secondary fica sem), Logical Name
   sem truncagem, e fix do X falso na checklist de loading da tab Space.
2. **Verificar 1º ciclo REAL do reconcile** (logs [Reconcile] ≥03h, Mode
   diferente de DRYRUN, deletes esperados 0) → se limpo, **implementar D3
   híbrido da sidebar** (parecer v1-intel GO-com-condições já emitido:
   INST_ENVS = membership+Env, servers.json = enrichment, fallback, filtro
   enabled; pré-requisitos SS301 e flip DRY_RUN JÁ feitos a 27/07).
   Confirmar também: Collector Health com reconcile FRESH via heartbeat
   (transição NEVER_RAN→idade real) e id SQLHDSSQLT301_I01 a convergir.
3. **Wave collector V1 (gate v1-intel obrigatório)** — findings acumulados de
   27/07: (a) collect_datafiles conflate volume desconhecido com 0 (mount
   points 408/412 + SQL antigo SCCM2012P01/SQLIJSPRD03; fix = CROSS APPLY
   dm_os_volume_stats por ficheiro + fallback xp_fixeddrives + sentinela -1;
   teste de aceitação: query MIN/MAX do owner passa a divergir em hosts
   mount-point); (b) collect_fg_space double-rounding GB→MB (bases pequenas
   mostram 0.00); (c) collector órfão collect_filegroup_usage com sentinela
   divergente (arquivar); (d) opcional Volume_Total_MB na DATAFILES_STG p/ %
   de disco no KPI (handoff V6 FILEGROUP_UNLIMITED_DISKBOUND_MODEL.md).
4. **Audit "nome, não número" nas restantes modais** (regra owner 27/07;
   Deadlocks já feito; candidatos nos campos do sweep A em
   auditorias/SWEEP_BACKEND_RICO_UI_POBRE_2026-07-27.md).
5. **Propagação V6 do lote 27/07 + bulletin** — V6 não é superset, grep
   anchors primeiro; bulletin aos counterparts V5/V6 sobre auto-resolve +
   migração 009 (herdam a BD partilhada — condição 6 do gate).
6. Pendências leves: backfill seletivo do 1 evento offline órfão
   (classificar c/ query do parecer auto-resolve); quick wins do sweep
   (?includeSystem= ignorado no backup summary; cluster.py nunca registado —
   remover); decisões OATXP01 (recomendação: manter fora do portal, SQL 2005
   < piso) e DDL KPI_OS_DISK no canonical (recomendação: incluir, gate
   v1-intel); observação ops drives de LOG apertados (QLT023 L:\ 3.6GB,
   TST023 L:\ 8.1GB).

## Contexto operacional
- Branch: wave-y/sessao-2026-07-21-22 (monorepo). Commits da sessão 27/07:
  confirmar com git log se o owner executou os 2 blocos (V3.3 + V1) — se não,
  os blocos estão na conversa/CONTEXT; nada committar sem GO.
- Serviços: restarts de 27/07 feitos pelo owner; qualquer edit backend novo
  exige novo Restart-Service (classes Python em cache).
- Fecho da sessão 27/07 (relatório antes/depois) pode ser pedido pelo owner —
  material todo no CONTEXT.md (entradas 2026-07-27).
