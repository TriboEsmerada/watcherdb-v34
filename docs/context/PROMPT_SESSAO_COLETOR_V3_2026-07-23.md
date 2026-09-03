# PROMPT — Sessão Coletor v3: matar o 2571 com DATABASEPROPERTYEX (OODA)

Cola isto na sessão nova (ou aponta o agente para este ficheiro):

---

Missão: reescrever o coletor de CHECKDB para eliminar as ~965 DBs "não mensuráveis"
(erro 2571) SEM grants — via `DATABASEPROPERTYEX(name, 'LastGoodCheckDbTime')`.
Trabalha em OODA e respeita o CLAUDE.md (modo consultor + handshake).

## OBSERVE (factos — verifica antes de agir)

- Ficheiro alvo: `WATCHERDB INTELLIGENCE V1/scripts/collectors/collect_dbcc_history.py`
  (cursor por DB + `DBCC DBINFO WITH TABLERESULTS` + TRY/CATCH; Item B já grava
  Collection_Status/Error_Number/Error_Message — NÃO regredir isso).
- Frota real 2026-07-23: 1276 DBs avaliadas; ~965 NOT_MEASURABLE, erro dominante
  2571 = `User 'sql_monitoring' does not have permission to run DBCC DBINFO`.
- Owner validou em SSMS: `SELECT d.name, DATABASEPROPERTYEX(d.name,'LastGoodCheckDbTime')
  FROM sys.databases d;` corre com sql_monitoring e devolve as datas.
- Consumidores a jusante (não mexer sem razão): KPI_MSSQL_INTEGRITY_VERDICT_VIEW (22 cols,
  SECAO 16 do canonical + WAVE_X standalone v5), cards V3.3+V6, modal com 3 gráficos +
  strip "porque falhou".
- Memórias relevantes: `feedback-sql-monitoring-select-only` (reescrever > GRANT),
  `project-collector-freshness-findings-2026-07`, `reference-v3-3-schema-catalog`.

## ORIENT (restrições e armadilhas conhecidas)

1. `LastGoodCheckDbTime` só existe em SQL 2016 SP2+ / 2017+ → capability check por
   versão (`SERVERPROPERTY('ProductVersion')`) e FALLBACK ao caminho DBCC DBINFO actual
   para instâncias antigas (a frota tem 2019 RTM e provavelmente mais velhas — PRD211/212).
2. Sentinela `1900-01-01` = NEVER_VALIDATED (semântica já tratada — manter).
3. NULL é ambíguo: distinguir com `HAS_DBACCESS(d.name)` →
   NULL + acesso = COLLECTION_ERROR ('PROPERTYEX NULL');
   NULL + sem acesso = COLLECTION_ERROR ('sem acesso a DB'). Sem ERROR_NUMBER() neste
   caminho — Error_Number = 0 (regra do pipeline: INT nullable com None quebra
   fast_executemany 22003; strings NULL ok; NUNCA astype("Int64")+where → NAType).
4. Infra partilhada V1 (alimenta V3.3 + V6): **GATE obrigatório — parecer do
   watcherdb-v1-intel-specialist antes de aplicar** (tem veto).
5. Edits a produção = handshake por operação. Restart do coletor obrigatório pós-edit
   (classe Python em RAM). Colector roda a cada 60 min.

## DECIDE (decisão já tomada pelo owner em 23/07 — não re-litigar)

Coletor v3 = caminho set-based DATABASEPROPERTYEX como primário + fallback legacy
por versão. O ticket de grants MORRE (superseded). Bucketing v2 (2571→PERMISSION_DENIED)
só se sobrar população com erro após o v3 — provavelmente desnecessário.

## ACT (passos)

1. Dispatch v1-intel-specialist com este desenho → incorporar parecer.
2. Reescrever QUERY do coletor (capability check + set-based + fallback); manter
   COLUMNS/transform/validate compatíveis (schema da STG não muda).
3. Handshake → aplicar → owner reinicia WatcherDBCollector.
4. Validar após 1 ciclo (~60 min): money query — esperado NOT_MEASURABLE a cair de
   ~965 para ~0 nas instâncias 2016SP2+; card "Não mensurável" a drenar; gráfico
   "Tipo de Falha" como tracker.
5. Fechar superfícies: canonical (se QUERY canonical existir no INSTALACAO), CHANGELOG
   V1, memória, secção F propagação (V6 herda via BD).
6. SE sobrar tempo: validação P1 V6 (restart + browser), P2/P3 V6 (gráficos + accordion
   — designs em docs/context/DESIGN_ACCORDION_MODAIS_2026-07-23.md e secção F).

## Lembrete operacional fora de código

DBA_RESOURCE_DB @SQLHDSPRD013_I03: corrupção ACTIVA em aceleração (311k→498k erros
19→23/07). Escalar CHECKDB/plano de correcção nas operações — não espera por sprints.
