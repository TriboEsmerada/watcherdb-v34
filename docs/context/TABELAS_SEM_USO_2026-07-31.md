# Tabelas sem uso na WatcherDB_Intelligence — levantamento de 2026-07-31

> **REV. 3 (31/07 tarde) — este documento foi corrigido duas vezes e a versão
> operativa é a do V6:** `WATCHERDB_V6/docs/context/auditorias/2026-07-31_tabelas_sem_uso.md`
> (rev. 2, organizada por remediação), **com os números de volume corrigidos abaixo**.
>
> **Correcção 1 (V6, rev. 2):** as 7 tabelas da minha categoria A ("ninguém lê")
> TÊM leitor em código — falta o último elo (router não registado, UI inexistente).
> Verificado por mim no código V6: confirma-se 7/7.
>
> **Correcção 2 (minha, rev. 3):** a query da varredura juntava
> `dm_db_index_usage_stats` SEM `index_id` — cada partição multiplicada pelas
> linhas de uso da tabela. **As colunas MB e Escritas desta varredura estão
> infladas ~N× (N = nº de índices)** nas tabelas multi-índice. Números certos:
>
> | Tabela | MB errado (rev. 1-2) | **MB real** | Escritas erradas | **Operações reais (35d)** |
> |---|---|---|---|---|
> | `audit_log_v6` | 568,2 | **113,6** | 111.905 | ~5.569 |
> | `WatcherDB_Ensemble_Votes` | 270,4 | **135,3** | 829.204 | ~208.045 |
> | `WatcherDB_Briefing_Items` | 29,8 | **7,4** | 38.560 | ~2.410 |
> | `WatcherDB_Briefings` | 8,5 | **4,2** | 28 | ~7 |
> | `tribunal_decisions` | 6,2 | **1,6** | 19.280 | ~1.205 |
> | `tribunal_sessions` | 2,0 | **0,7** | 675 | ~75 |
> | `WatcherDB_Auth_Log` | 0,5 | **0,3** | 424 | ~106 |
>
> Consequência directa: **o "achado (b)" do V6 (14 KB/linha no audit_log_v6)
> dissolve-se** — a largura real é ~2,9 KB/linha (medido: `evidence_dump` médio
> 1-3 KB, máximo 124 KB em picos). Não há problema de esquema; retenção chega.
> O achado (a) — **job de archive atestado para DORA Art. 28 e NÃO agendado
> nesta máquina** — foi verificado no Task Scheduler e MANTÉM-SE. É o único
> item com prazo.

> Base: `sys.dm_db_index_usage_stats` com janela desde o arranque do SQL Server
> (**2026-06-26**, 35 dias) + varreduras das sessões 30-31/07. Critério da
> varredura principal: **zero leituras** (seeks+scans+lookups) em toda a janela.
>
> **Três vieses a ter em conta antes de condenar uma tabela:**
> 1. A janela é de 35 dias — uso sazonal (relatórios mensais/trimestrais) não aparece.
> 2. As minhas próprias auditorias de 30-31/07 **acrescentaram leituras** a algumas
>    tabelas (pares BLUE/GREEN, `_OLD`) — essas saíram do filtro automático e
>    entram abaixo por evidência anterior.
> 3. Zero leituras ≠ inútil em tabelas de **auditoria** — escrever sem ler é o
>    comportamento normal até ao dia em que se precisa.

## Resumo

| Categoria | Tabelas | Volume | Pergunta a fazer |
|---|---|---|---|
| A. Pro/AI write-only (escrevem muito, ninguém lê) | 7 | ~880 MB | vale a pena o custo de escrita? |
| B. Pro/AI experimental congelada (parou início Jul) | 4 | ~6 MB | experiência terminada? |
| C. Pro/AI experimental **vazia** (nunca escrita) | ~33 | ~0 | por que existe o DDL? |
| D. Legado V1 vazio/substituído | 9 | ~0 | apagar? |
| E. Congeladas/mortas com dados | 14+ | ~126 MB | arquivar e largar? |
| F. Backups de migração | 2 | 0,2 MB | prazo de validade |
| G. **Falsos positivos — NÃO tocar** | 4 | — | — |

---

## A. Pro/AI — escrita activa, zero leituras (write-only)

O custo está a ser pago todos os dias; ninguém colhe o retorno.

| Tabela | Linhas | MB | Escritas (35d) | Última escrita | Nota |
|---|---|---|---|---|---|
| `audit_log_v6` | 40.288 | **568,2** | 111.905 | hoje | Auditoria V6 — write-only é aceitável POR DESENHO, mas 568 MB sem retenção não é. Precisa de janela. |
| `WatcherDB_Ensemble_Votes` | 1.118.208 | **270,4** | 829.204 | hoje | O detalhe voto-a-voto do ensemble. A agregada (`Ensemble_Results`) É lida; esta nunca. 829 k escritas/35d para nada — candidata a deixar de gravar ou reter dias. |
| `WatcherDB_Briefing_Items` | 13.393 | 29,8 | 38.560 | 29/07 | Morning briefing V6 — lido via outra via? verificar no V6 antes de concluir. |
| `WatcherDB_Briefings` | 36 | 8,5 | 28 | 29/07 | idem |
| `tribunal_decisions` | 1.818 | 6,2 | 19.280 | 29/07 | Tribunal voting V5/V6 — escreve a cada ciclo, nunca lida aqui. |
| `tribunal_sessions` | 2.134 | 2,0 | 675 | 29/07 | idem |
| `WatcherDB_Auth_Log` | 1.118 | 0,5 | 424 | hoje | Auditoria de autenticação — write-only aceitável; sem retenção. |

## B. Pro/AI experimental — escrita parou no início de Julho

| Tabela | Linhas | Última escrita |
|---|---|---|
| `consciousness_scheduling_log` | 582 | 2026-07-03 |
| `production_rule_firings` | 456 | 2026-07-03 |
| `ablation_reports` | 68 | 2026-07-04 |
| `app_event_log` | 573 | 2026-07-22 |

Experiências do stack AI V5 que deixaram de escrever. Se a experiência acabou, o DDL devia acompanhar.

## C. Pro/AI experimental — vazias, nunca escritas

DDL criado, nunca populado. Nomes falam por si — é a família "consciousness/AI experimental" do V5:

`incident_memory` · `kg_rag_sessions` · `meta_tuning_log` · `normative_assessments` · `pattern_execution_log` · `predictive_processing_log` · `cognitive_resonance_log` · `dream_state_discoveries` · `error_forensics_reports` · `failure_predictions` · `agent_feedback` · `ai_feedback_log` · `learned_contexts` · `contextual_anomalies` · `question_catalog_overlay` · `server_dna_snapshots` · `socratic_sessions`* · `meta_cognition_snapshots`* · `red_team_challenge_log`* · `red_team_sessions`* · `war_rooms`* · `war_room_updates`* · `war_room_participants` · `cognitive_load_entries`* · `decision_simulator_log`* · `resource_consumption`* · `resilience_measurements`* · `premortem_reports`* · `incident_dna_fingerprints`* · `agent_queries`* · `collector_toggle_audit`* · `business_impact_config` · `business_impact_events`

\* têm algumas linhas antigas mas zero escritas e zero leituras na janela.

**Pergunta única para o V5/V6:** quais destas experiências estão vivas no roadmap? As mortas deviam sair do DDL de instalação — um cliente novo recebe hoje ~33 tabelas de experiências que nunca correram.

## D. Legado V1 — vazias ou substituídas

| Tabela | Estado | Evidência |
|---|---|---|
| `KPI_MSSQL_THRESHOLDS` / `_V2` | vazias | Substituídas pelo Smart Defaults Principle (per-DB threshold = anti-pattern, decisão 2026-05-25) — o DDL sobreviveu à decisão |
| `KPI_OS_DIAGNOSIS_LOG` | vazia | nunca escrita |
| `KPI_MSSQL_AGENT_JOBS_HIST` | vazia | HIST nunca alimentada |
| `KPI_MSSQL_FG_USAGE_ALL_HIST` | vazia | idem |
| `metrics_5min` / `metrics_1hour` | vazias | geração antiga de métricas |
| `sql_agent_jobs` / `sql_error_logs` / `windows_events` / `alwayson_health` / `data_sources` | vazias | nomenclatura minúscula = geração anterior ao padrão KPI_MSSQL_* |
| `KPI_MSSQL_COLLECTION_HISTORY` + `_SERVER_DETAILS` | vazias | regressão da migração 25/03 (o serviço nunca grava) — **não apagar**: repor a escrita é sub-wave já identificada |

## E. Congeladas ou mortas com dados

| Grupo | Detalhe |
|---|---|
| `KPI_MSSQL_TLOG_USAGE_HIST` | 860 k linhas / 125 MB, congelada em **2026-03-25** (archiving morreu na migração). Decidir: reanimar ou aposentar. |
| 12 tabelas `_STG_OLD` | frias desde o arranque, ~0,5 MB total. São a **documentação das PKs originais** (12/12 lideram por Instance) — extrair as definições antes de qualquer DROP. |
| Famílias `DEPRECATED_KPIS` (BLOCKED_USERS, SERVICE_STATUS, DB_IO_STATS, LONG_LOCKS) | desactivadas de propósito 13/05 (`run_collections.py:128-139`); as tabelas e views ficaram. Decisão de produto pendente: sair de `kpis_metadata.py` e do DDL, ou reactivar. |
| `KPI_MSSQL_DB_SECURITY_MAP_STG_*` | família fora da `KPI_STG_ACTIVE_TABLE` — o swap dela falha desde antes da Wave C. Follow-up próprio. |

## F. Backups de migração — com prazo de validade

| Tabela | Origem | Quando largar |
|---|---|---|
| `KPI_MSSQL_INST_ENVS_BAK_20260724` | backup manual de 24/07 | quando o reconcile de envs estiver estável há >30d |
| `KPI_STG_ACTIVE_TABLE_BACKUP_20260731` | **âncora de rollback da Wave C** | só depois de ~1 semana de Wave C estável — **não tocar já** |

## G. Falsos positivos do filtro — NÃO são candidatas

| Tabela | Porquê aparece com zero leituras |
|---|---|
| `WDB_KPI_MUTE` | tabela de controlo do produto (mute list); vazia porque não há mutes activos — feature, não lixo |
| `WatcherDB_API_Keys` / `WatcherDB_OrgMemory` | tabelas de produto V6, vazias por não haver dados ainda |
| `KPI_MSSQL_AUTO_PAGE_REPAIR_STG_BLUE/GREEN` | par base legacy da família (as per-env estão activas); mesma classe das outras `_BLUE/_GREEN` base |

---

*Gerado na sessão de 2026-07-31 (Wave C + retenção HIST). Query reutilizável em `scratchpad/sem_uso.sql` — repetir após restart do SQL Server invalida a janela.*
