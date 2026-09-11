# PROPAGAÇÃO V6 — painel LIVE: 4 canais por instância + falso "tudo limpo" (lote 2026-09-11)

> Para a AI do V6. **Verificar primeiro, assumir nunca.** O V6 tem um router LIVE irmão do V3.4
> (`api/routers/live_monitoring.py` no V3.4; confirma o caminho no V6 por grep de `dm_io_virtual_file_stats`).
> Origem: `docs/context/FIX_LIVE_CANAIS_2026-09-11_apply.py` (código integral: SQL, JS, chaves, testes).

## 0. Factos medidos (não são hipóteses)

Reproduzido por SELECT via `sql_monitoring` em CAGENPRD06 (2016 SP2), SQLHDSGENPRD01 (2022, primária de AG)
e SQLHDSGENPRD02 (2022, secundária **não legível**):

1. `FROM sys.dm_io_virtual_file_stats(NULL, NULL) vfs WITH (NOLOCK)` → erro 319 em todas as versões.
   `FROM sys.dm_db_log_stats(NULL) WITH (NOLOCK)` → 319 em 2016, 102 near ')' em 2022. Um hint de tabela
   não faz parte da gramática de uma função de tabela; o parser lê `WITH` como CTE. **Não é** "CTE sem ;".
2. `sys.dm_db_log_stats(NULL)` devolve 0 linhas em 2016 SP2 e só a master em 2022. E a DMV **não tem**
   `log_reuse_wait_desc` (vem de `sys.databases`) nem `log_space_in_bytes_since_last_backup` (a coluna é
   `log_since_last_log_backup_mb`). O 319 escondia este 207.
3. `sys.dm_hadr_database_replica_states` **não tem** `database_name` (207). Vem de
   `sys.availability_databases_cluster` por `group_database_id`.
4. `CROSS APPLY sys.dm_db_log_stats(d.database_id)` numa secundária não legível **não rebenta**: devolve as
   colunas da DMV a NULL e `HAS_DBACCESS = 0`, com `d.log_reuse_wait_desc` preenchido. Guarda suficiente:
   `d.state = 0 AND d.source_database_id IS NULL`. **Não** filtrar por `HAS_DBACCESS` (perderias as linhas
   `AVAILABILITY_REPLICA`, que são o que interessa numa secundária).
5. `1024.0` numa expressão devolve `Decimal` → `JSONResponse` dá 500 puro ("Object of type Decimal is not
   JSON serializable"). Só disparava quando havia uso activo de tempdb.

## 1. Backend (grep no V6 por cada âncora)

| Grep | O que fazer |
|---|---|
| `dm_io_virtual_file_stats(NULL, NULL) vfs WITH (NOLOCK)` | tirar o hint (`AS vfs`) |
| `dm_db_log_stats(NULL) WITH (NOLOCK)` | reescrever como no V3.4: `FROM sys.databases d CROSS APPLY sys.dm_db_log_stats(d.database_id) ls WHERE d.database_id > 4 AND d.state = 0 AND d.source_database_id IS NULL`; colunas `ls.log_since_last_log_backup_mb`, `d.log_reuse_wait_desc` |
| `drs.database_name` | `LEFT JOIN sys.availability_databases_cluster adc ON adc.group_database_id = drs.group_database_id` → `adc.database_name`. **Há duas ocorrências no V3.4** (ALWAYSON_SQL e o resumo de saúde `ag_queues`, este engolido por `except: pass`); procura as duas no V6 |
| `DATEDIFF(SECOND, drs.last_commit_time, GETDATE())` | lag = delta entre o commit da primária e o da réplica: `OUTER APPLY (SELECT MAX(p.last_commit_time) FROM dm_hadr_database_replica_states p JOIN dm_hadr_availability_replica_states pa ON pa.replica_id = p.replica_id AND pa.role = 1 WHERE p.group_database_id = drs.group_database_id) pc` e `CASE WHEN ars.role = 1 THEN 0 WHEN ... IS NULL THEN NULL ELSE DATEDIFF(SECOND, drs.last_commit_time, pc.primary_commit) END`. Usa `role` (2012-safe), **não** `is_primary_replica` (2014+; a frota tem 4 × 2012). NULL numa secundária é normal: só vê a sua linha |
| `JSONResponse(content=` no router LIVE | helper único `JSONResponse(status_code=..., content=jsonable_encoder(payload, custom_encoder={bytes: lambda b: b.hex()}))`; torna redundantes os `.isoformat()` manuais |

Fallback legado do T-Log (2012/2014, `FILEPROPERTY(mf.name,'SpaceUsed')` em master) devolve `log_used_mb`
NULL para bases que não a corrente — objecção registada pelo sql-deep-reviewer, **fora deste lote**;
alternativa `DBCC SQLPERF(LOGSPACE)` ou o contador 'Log File(s) Used Size (KB)'.

## 2. Portal (se o V6 tiver o painel LIVE com programas por instância)

- Sem instância e programa ≠ fleet: estado neutro (ícone + "Selecione uma instância no Canal para ver
  {program}"), carimbo `--`, intervalo limpo. Nunca deixar o render anterior (Queries/Blocking/Jobs/AG têm
  todos um empty-state com check verde — um "No running queries" sem pedido é falso positivo).
- Canal limpo: mesmo estado neutro com a chave `live.select_channel` já existente.
- Erro HTTP do programa: o carimbo passa a "Erro HTTP {code}" a vermelho (antes ficava o último horário verde).
- Guarda de corrida em `_liveRefresh`: capturar instância/programa no início e descartar a resposta se
  mudaram durante o `await`.
- `commit_lag_sec` pode vir NULL → "n/d" em cinzento; suspensa → cor de aviso antes do lag (o lag só cresce
  quando a primária commita).
- Chaves: `live.select_instance_for_program` ({program}), `live.error_http` ({code}); pt-BR herda.

## 3. Testes a portar

`tests/unit/test_live_channels_20260911.py` (8): sem hint em TVF; colunas reais de `dm_db_log_stats`;
`database_name` via `availability_databases_cluster` em todo o router; lag sem GETDATE e sem
`is_primary_replica`; todas as respostas pelo helper; helper serializa Decimal/datetime/bytes; fallback
legado do T-Log quando o erro contém `dm_db_log_stats`; portal com estado neutro, carimbo de erro, guarda de
corrida e lag nulo; chaves nos 3 locales.

## 4. Achados que ficam (não herdar, não corrigir às cegas)

- Gauges (`gaugesResp` não-ok) ficam congelados no último valor bom sem sinal de idade — mesma classe do
  carimbo; lote próprio.
- As mensagens usam a chave interna do programa (`alwayson`, `plancache`) em vez do rótulo visível
  (`AG`, `Plan Cache`); precedente em `live.loading_program`; mapa `PROGRAM_LABELS` numa wave futura.
- O resumo de saúde filtra filas por `> 1024` KB (1 MB) — mesma classe do "KB vs 1000" do Always On;
  decisão de limiar, não bug de sintaxe.
