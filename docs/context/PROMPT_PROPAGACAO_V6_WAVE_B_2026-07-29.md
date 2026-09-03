# Propagação V6 — Wave B 2026-07-29 (Indexação dirigida por DMV + integridade da BD partilhada)

> Repo V6 é **próprio** (`WATCHERDB_V6`, git local-only — o parent `projetosPython`
> NÃO o segue). `git status` por repo antes de commitar.
> Portal V6 **não é superset** do V3.3 — grep os anchors antes de assumir que existe.
> Commit de origem: **pendente**. Os índices foram criados directamente na BD em
> 2026-07-28; a propagação para `INSTALACAO_COMPLETA_UNIFICADA.sql` ainda não está
> aplicada à data deste documento. **Confirmar antes de assumir que o canonical já os tem.**

---

## Contexto: porque é que esta wave interessa mais ao V6 do que ao V3.3

O diagnóstico partiu de uma pergunta sobre o V3.3, mas os dados apontaram para o outro
lado. Os dois maiores consumidores em falta de índice na `WatcherDB_Intelligence`
**não são lidos por código V3.3** — `grep` em `WATCHERDB_V3.3/api/` devolve zero
referências a `KPI_MSSQL_ANOMALY_DETECTION` e a `KPI_MSSQL_ALWAYSON_FAILOVER_HIST`.

São tabelas escritas e lidas pelo lado V5/V6. Logo: **o ganho é do V6, e o trabalho
de fundo que sobra também é do V6.**

---

## A. HERDA VIA BD — verificar apenas, zero código

A BD `WatcherDB_Intelligence` é partilhada. Nada nesta secção precisa de código em V6.

| O quê | Porquê herda |
|---|---|
| `IX_ANOMALY_DETECTION_Abertas` — filtrado `WHERE resolved_at IS NULL`, sobre `(anomaly_type, instance, database_name)` INCLUDE `(severity, detected_at)` | Índice na BD partilhada; consolida ~11 pedidos distintos do optimizador, impacto estimado até 2.24M |
| `IX_ALWAYSON_FAILOVER_HIST_TS_Source` — `(event_timestamp, source)` | Idem; 651.601 seeks sem suporte de índice |
| Primeiro `DBCC CHECKDB` da base (2026-07-28) | Infraestrutura; a base nunca tinha sido verificada desde a criação em 2026-04-06 |

**Verificação (read-only):**
```sql
USE [WatcherDB_Intelligence];
SELECT OBJECT_NAME(object_id) AS Tabela, name AS Indice, has_filter, filter_definition
FROM sys.indexes
WHERE name IN ('IX_ANOMALY_DETECTION_Abertas', 'IX_ALWAYSON_FAILOVER_HIST_TS_Source');
```

---

## B. TRABALHO REAL EM V6 — o diagnóstico expôs código do lado V6

### B1. 651.601 seeks numa tabela de failovers *(prioridade alta)*

`sys.dm_db_missing_index_group_stats` reportou **651.601 seeks** sobre
`KPI_MSSQL_ALWAYSON_FAILOVER_HIST` por `(event_timestamp, source)`.

Isto é uma tabela de **eventos raros** — failovers num ambiente saudável acontecem
dezenas de vezes por mês, não centenas de milhares. Um número desta ordem é assinatura
de **verificação linha-a-linha dentro de um ciclo**, tipicamente um "este evento já
existe?" antes de cada insert.

O índice novo trata o sintoma. A causa está no lado escritor, que é V6.

**Anchors a procurar em V6:** `KPI_MSSQL_ALWAYSON_FAILOVER_HIST`, `failover`,
`event_timestamp`, e qualquer `SELECT ... WHERE event_timestamp = ... AND source = ...`
dentro de um loop de deduplicação.

**Correcção preferida:** substituir a verificação por registo (`UNIQUE` +
`INSERT ... WHERE NOT EXISTS` em conjunto, ou `MERGE` em lote) em vez de uma query por
linha candidata. Se o volume vier de reprocessamento de janelas já lidas, o problema é
a janela, não a query.

### B2. Grafo de conhecimento reescrito de fio a pavio *(prioridade alta)*

`sys.dm_db_index_usage_stats` sobre a BD partilhada:

| Tabela | Linhas | Índices sem uma única leitura | Escritas por índice |
|---|---|---|---|
| `kg_relations` | 32.025 | 4 | 4.992.824 |
| `kg_entities` | 33.066 | 3 | 4.631.166 |

Cerca de **34 milhões de operações de manutenção de índice** sobre tabelas com 32 mil
linhas, e **zero leituras** através desses índices. Duas leituras distintas, ambas a
investigar em V6:

1. O grafo está a ser **reconstruído integralmente** de forma repetida, em vez de
   actualizado incrementalmente.
2. Os 7 índices `IX_kg_*` não servem nenhum plano — são custo puro na escrita.

**Anchors:** `kg_entities`, `kg_relations`, `kg_knowledge_base`, e o serviço que
popula o Knowledge Graph (`rag_engine` / `cognitive_rag` / ingestão do KG).

> **Não dropar os índices `IX_kg_*` a partir de uma sessão V3.3.** Ver secção E.

### B3. Restrição de SET options introduzida pelo índice filtrado

`IX_ANOMALY_DETECTION_Abertas` é um **índice filtrado**. A partir de agora, qualquer
`INSERT`/`UPDATE`/`DELETE` em `KPI_MSSQL_ANOMALY_DETECTION` exige `ANSI_NULLS` e
`QUOTED_IDENTIFIER` a `ON` na sessão que escreve, ou a operação falha.

O ODBC liga com ambos a `ON` por omissão, portanto não se espera problema. Mas se
começarem a falhar inserts de anomalias em V6, **a causa é esta** — não procurar noutro
lado. Verificar em qualquer caminho que use `pymssql`, cursores com SET explícito, ou
SQL dinâmico dentro de procedures.

Predicado confirmado no código V6 durante o diagnóstico:
`prompts/melhorias AIOps - 24022026/absence_detector.py:392` e
`absence_detector_router.py:228` usam `resolved_at IS NULL` — coerente com o filtro.

---

## C. PORTAL V6 — nada nesta wave

Wave B não altera UI. Não há anchors a procurar.

**Candidato futuro, não desta wave:** `KPI_MSSQL_DBCC_HISTORY_STG_BLUE/GREEN` já recolhe
`Last_CheckDB_Date`, `Days_Since_CheckDB` e `Collection_Status` de todos os servidores
monitorizados, e **não está exposto em portal nenhum** — nem V3.3 nem V6. "Bases sem
CHECKDB limpo há N dias" é superfície de produto com valor comercial directo.
Classificação de tier por decidir antes de qualquer código.

---

## D. Regra de canonical que o V6 também tem de conhecer

Descoberto nesta wave, aplica-se a **qualquer** sessão que acrescente índices ao
`INSTALACAO_COMPLETA_UNIFICADA.sql`:

> Índices declarados **dentro** do bloco `IF NOT EXISTS (SELECT 1 FROM sys.tables ...)`
> **nunca chegam a instalações existentes** — o bloco não reentra quando a tabela já
> existe. Só funcionam em fresh install.

Foi o caso das secções 23.1 (`KPI_MSSQL_ALWAYSON_FAILOVER_HIST`, linhas 12718-12723) e
31.1 (`KPI_MSSQL_ANOMALY_DETECTION`, linhas 14367-14375).

**Padrão correcto**, já presente no ficheiro nas linhas 1943, 2003 e 6818: guard próprio
por índice, fora do bloco da tabela.

```sql
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = '<nome>' AND object_id = OBJECT_ID('dbo.<tabela>'))
BEGIN
    CREATE NONCLUSTERED INDEX <nome> ON dbo.<tabela> (...);
    PRINT '  [OK] Index <nome> criado (Wave B)';
END
ELSE PRINT '  [SKIP] Index <nome> ja existe';
GO
```

---

## E. Validação antes de declarar propagado

1. `git status` no repo `WATCHERDB_V6` — é git próprio, não é seguido pelo parent.
2. Confirmar que os dois índices existem na BD (query da secção A).
3. Confirmar que o canonical já os tem — à data deste documento **ainda não tinha**:
   ```bash
   grep -c "IX_ANOMALY_DETECTION_Abertas\|IX_ALWAYSON_FAILOVER_HIST_TS_Source" \
     "WATCHERDB INTELLIGENCE V1/database/INSTALACAO_COMPLETA_UNIFICADA.sql"
   ```
4. Para B1 e B2: medir antes e depois. `sys.dm_db_index_usage_stats` zera no restart da
   instância — registar `sqlserver_start_time` junto com a medição, ou a comparação não
   significa nada.

---

## F. Pendentes que NÃO devem ser propagados ainda

| Item | Porquê está travado |
|---|---|
| Limpeza de ~250 índices sem leituras | Falta `sqlserver_start_time`: os contadores zeram no restart e "zero leituras" pode significar "zero leituras desde ontem". **E a maioria das tabelas afectadas é schema V5/V6** (`kg_*`, `tribunal_*`, `dream_state_*`, `WatcherDB_Ensemble_*`, `consciousness_*`, `war_rooms`). O `watcherdb-v1-intel-specialist` tem veto declarado sobre a BD partilhada |
| Duplicados confirmados: `IX_ALWAYSON_Instance_Database` + `IX_STG_BLUE_PRD_InstDB`; `IX_DB_State` + `IX_DB_AVAIL_BLUE_State` (e pares GREEN) | Mesmo bloqueio. São duplicados a sério — dois índices sobre as mesmas colunas na mesma tabela |
| Tabelas `_OLD` sobreviventes de migração (`ERRORLOG_STG_OLD`, `SERVICE_STATUS_STG_OLD`, `DB_IO_STATS_STG_OLD`, `BACKUPS_STG_OLD`) ainda com índices | Confirmar que nenhum consumidor V5/V6 as lê antes de propor drop |
| Rotinas de manutenção agendadas (Ola Hallengren) | Decisão fechada: instalar **só no host da equipa**, nunca no instalador do cliente. Para o cliente é runbook, não software |

---

## G. Coisas que o diagnóstico *desmentiu* — não repetir o trabalho

Registado para que uma sessão futura não volte a partir das mesmas hipóteses:

- **A fragmentação não é problema.** Numa base de ~3 GB, apenas 2 índices acima de 5%
  (`IX_Anomaly_Instance` 5.60%, `PK_KPI_OS_CPU_HIST` 5.18%), ambos com poucos milhares de
  páginas. Rebuild de índices não tinha nada de útil para fazer.
- **As estatísticas estão saudáveis.** `auto_update_stats` ligado e a funcionar; as
  estatísticas com `last_updated NULL` pertencem todas a tabelas vazias.
- **`page_verify` já estava em `CHECKSUM`** e `msdb.dbo.suspect_pages` vazia — a detecção
  de corrupção estava armada, só nunca tinha sido disparada.
- **A BD `[WatcherDB]`** (schemas `kpi.`/`monitoring.`/`config.`/`history.`, criada por
  `WATCHERDB_V3.3/database/00_WATCHERDB_MASTER_DEPLOY.sql` e indexada por
  `02_WATCHERDB_INDEXES.sql`) **não existe no servidor** e não é referenciada por código
  aplicacional nenhum. São ~14 índices de scaffolding morto no repositório. Não confundir
  com a `WatcherDB_Intelligence`, que é a base real.
