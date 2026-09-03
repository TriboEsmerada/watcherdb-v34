# PROMPT — Sessão V3.3: pacote aba Space (pedidos owner 2026-07-27, fim de sessão)

Cola isto na sessão nova. Trabalha em OODA, modo consultor + GO por lote,
memórias owner activas (panorama sempre; nome-não-número; validação node 12/12
+ py ast; commit + plano V6 no fim).

## Contexto
Owner pediu 6 melhorias na aba Space (drilldown Databases → FileGroups →
DATAFILES) no fecho da sessão 27/07. Anchors JÁ MAPEADOS (verificados nessa
sessão — revalidar linhas com grep, o portal levou ~30 edits nesse dia).

## Itens

1. **Ordenação em todas as colunas** (3 tabelas: Databases exterior, FileGroups
   aninhada, DATAFILES aninhada). Abordagem recomendada: helper DOM-based
   `sortNestedTable(th, colIdx)` global — ordenar `<tr>` do tbody in-place,
   numeric-aware, tratando PARES (row de dados + row-container seguinte com id
   `fg-row-*`/`files-row-*` movem juntos). Adicionar onclick+cursor aos th.
   Anchors: thead FileGroups portal ~26989-27000; thead DATAFILES ~27188-27198;
   thead Databases exterior (grep `>FileGroups</th>` na zona ~16280).

2. **Free MB / Free % EFETIVOS na tabela FileGroups** — hoje mostra
   alocado−usado (61MB no caso FG_DW_ODS_TAP_ATH_BKDREV_HIST_DAT) enquanto o
   veredicto usa max-aware. MATRIZ DECIDIDA COM O OWNER (inclui resposta a "e
   se o growth não estiver ativo?"):
   | caso | capacidade efetiva | livre efetivo |
   | growth ativo + max finito | Σmax | Σmax − Σusado |
   | growth=0 | Σalocado (max é letra morta) | alocado − usado |
   | unlimited + growth ativo | disco | disk-bound (classificação já cobre; display mantém alocado + tooltip) |
   Backend `modules/monitoring/space_analysis.py` `query_precisa` (~607-662,
   USE [db] + FILEPROPERTY): adicionar
   `SUM(CASE WHEN df.growth > 0 THEN 1 ELSE 0 END) AS GrowthEnabledFiles`,
   `SUM(CASE WHEN df.growth > 0 AND df.max_size = -1 THEN 1 ELSE 0 END) AS UnlimitedGrowableFiles`,
   `EffCapGB = SUM(CASE WHEN df.growth=0 THEN df.size WHEN df.max_size=-1 THEN df.size WHEN df.max_size=268435456 THEN 268435456 ELSE df.max_size END)/128.0/1024.0`.
   Propagar no mapping python (dict do fg; mapping do precisa fica abaixo de
   ~660, o fallback basic_query está ~447-502) e no renderer portal
   ~27084-27088: display eff quando UnlimitedGrowableFiles=0; alinhar TAMBÉM o
   bloco de reclassificação effFree ~27045-27060 (display = veredicto, sempre).
   Nota: conta de verificação do owner: 7.204.003,84 − 7.153.489,92 ≈ 50.513MB.

3. **Status FULL/MAXED nos DATAFILES** (renderer ~27203-27249): com Used por
   ficheiro (item 4): `atCap = !unlimited && max>0 && current>=max`;
   `canGrow = growth>0 && !atCap` (growth raw novo);
   FULL (vermelho) se used>=~99,5% current && !canGrow; MAXED/S_CRESC (âmbar)
   se atCap com espaço interno; manter OVERFLOW existente com precedência.

4. **Coluna Used MB nos DATAFILES**: reescrever a query principal de files
   (space_analysis.py ~332-378, hoje sys.master_files sem used) para
   `USE [{database_name}]` + `sys.database_files` + `FILEPROPERTY(df.name,'SpaceUsed')*8/1024 AS UsedSizeMB`
   + `df.growth AS GrowthRaw` + volume stats `CROSS APPLY sys.dm_os_volume_stats(DB_ID(), df.file_id)`.
   `query_ag_secondary` (~279-329) NÃO pode USE (secundário não legível) —
   mantém sem Used (payload used_size_mb=None → frontend mostra —).
   Mapping python ~407-430: +used_size_mb, +growth_raw.

5. **Logical Name maior**: renderer ~27233-27241 trunca a 35 chars + min-width
   250px → remover truncagem, min-width ~420px, word-break, manter title com
   physical_name.

6. **Checklist de loading da tab Space mente**: mostra "X Filegroups e espaco
   por database — sem resposta (0.4s)" (âmbar, parece erro) enquanto o load
   real continua 9s+. Investigar `loadSpaceAnalysis` + `lc.track` (helper
   startLoadingChecklist, wired 16/07): a promise trackeada resolve/rejeita
   cedo (catch engolido? retry por outro caminho?) — o checklist deve refletir
   os pedidos REAIS e só marcar X em erro verdadeiro; mostrar passos reais do
   que está a carregar.

## Validação
- node 12/12 script blocks + py ast space_analysis.py.
- Browser: FG do caso real (SQLIDSPRD03 / DW_ODS_TAP / FG_..._BKDREV_HIST_DAT):
  Free deve passar de 61MB/0.0% para ~50.5GB/0.7% (continua CRITICAL — correto);
  ficheiro com current=max e used=current → FULL; sort nas 3 tabelas move os
  containers junto; checklist sem X falso.
- Tier: Std puro. Commit + nota de propagação V6 no fim.

## Estado herdado da sessão 27/07 (já shipped, não repetir)
Accordion F2 com nomes+links→Space (com scroll retry+flash), severidade por
modal, Total (filegroups), paleta ambiente clássica mantida, Fase 2 disk-bound
do KPI FileGroups (0=aviso "sem visibilidade"), deep-link navigateToSpaceFilegroup.
