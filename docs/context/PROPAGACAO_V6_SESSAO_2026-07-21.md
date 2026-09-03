# Propagação para V6 — Sessão 2026-07-20/21

Registo completo do que foi feito, decidido e descoberto, para replicar/avaliar no **WATCHERDB_V6**.

> ⚠️ **Regra crítica antes de propagar frontend:** o portal V6 é **subset simpler** do V3.3,
> **não** superset. Fazer `grep` aos anchors no V6 **antes** de assumir que a feature existe lá.
> Ver memória `feedback_v6_portal_not_superset`.
>
> ⚠️ **Infra partilhada:** a BD `WatcherDB_Intelligence` é comum a V3.3/V5/V6. As alterações
> de DDL/coletor da secção B **já beneficiam o V6 automaticamente** na BD — o que precisa de
> propagação é o **código** que o V6 tenha em cópia própria.

---

## A. FRONTEND V3.3 — aplicado, requer avaliação para V6

### A1. CORR-2026-07-20-001 — Drilldown de disco vinha vazio
**Ficheiro:** `templates/watcherdb_portal.html` (dentro de `toggleDiskDrillDown`)
**Sintoma:** tile mostrava "0 de 78 arquivos" com filtro de path (`f:\`).
**Causa:** o input `#disk-filter-input` serve a tabela externa (match em drive path) **e** o
drilldown (match só em `database_name`/`filegroup_name`/`logical_name`). Um token de path
nunca casa nos nomes lógicos → zerava tudo.
**Fix:** acrescentar `physical_path` aos campos pesquisados do drilldown.

```js
|| (f.physical_path || f.physical_name || '').toLowerCase().includes(activeText)
```

### A2. CORR-2026-07-20-002 — Sort + filtros por coluna no drilldown
**Refactor:** `renderDrillDown` era closure; passou a `buildDiskDrillHtml(drillId, state, files)` +
`renderDiskDrillById(drillId)` top-level, com estado isolado em `window.diskDrillState[drillId]`
(permite vários drilldowns abertos sem bleed).

- **Sort 8 colunas** — `sortDiskDrillColumn(drillId, col)`, ícones `fa-sort`/`-up`/`-down`.
- **Max Size / Growth**: parse client-side (OPÇÃO A, frontend-only). `parseDiskMaxSizeToGb`
  (Unlimited→∞, TB/GB/MB/KB→GB) e `parseDiskGrowthToComparable` (absoluto→MB; `%` agrupado
  via offset +1000000 — **convenção, não unidade física comparável**).
- **Filtros por coluna** — texto em Database/Arquivo/FileGroup, dropdown em Tipo.
- **Gotchas resolvidos:** restauro de foco/cursor após rebuild de innerHTML (senão perde foco
  a cada tecla); `escDiskAttr` para escapar o `value` reflectido no input.
- **i18n:** namespace `disk.drill.*` (13 chaves × pt/en/es).

### A3. CORR-2026-07-20-003 — Maximizar modais, Fase 1
- `toggleMaximizeModal(modalId)` **generalizado**: `MAXIMIZABLE_CONTENT_SELECTORS`.
- CSS `.inv-modal.maximized` (98vw/96vh — padrão de overlay centrado, não full-bleed).
- Botão na modal de Performance (`inv-header`) + `aria-label` no × de fechar.
- Reset do estado em `perfCloseModal` (senão reabre já maximizada).
- i18n `ui.maximize` / `ui.restore` (pt/en/es).

**⚠️ Colisão de nomes documentada:** já existe `toggleModalMaximize()` (sem "s", zero-arg)
dedicada ao SQL Results modal. **NUNCA usar esse nome** para a função genérica.

### A4. CORR-2026-07-21-004 — Maximizar modais, Fase 2 (sweep)
- `MAXIMIZABLE_CONTENT_SELECTORS` += `.instances-modal-content`.
- Helper novo `resetModalMaximized(modalId)`; `closeAlertsModal` refactorizado para o usar.
- CSS `.instances-modal-content.maximized` + override `#kpiHelpModalBody`.
- Botão em **10 modais**: report, memoryPressure, settings, serviceLogs, logMessage (sistema
  `.modal`) + instances, kpiHelp, cpuHelp, memoryHelp (sistema `.instances-modal`).
- Reset em 7 funções de close (+2 inline).

**Excluídos por decisão:** `changePasswordModal`, `selectableModal` (diálogos pequenos),
`backupGapsModal` (code-smell pré-existente: duas implementações para o mesmo ID).

**DIFERIDO (Zona F, não aplicado):** i18n dos tooltips hardcoded nos 4 divergentes
(`toggleConflictsModalMaximize`, `toggleReportMaximize`, `toggleDiagnoseModalExpand`,
`toggleModalMaximize`) + reset em `closeSQLResultsModal`.

> **Estado:** A1-A4 aplicados em V3.3 mas **ainda NÃO validados em browser**.
> Validar antes de propagar.

---

## B. V1 INTELLIGENCE (infra partilhada) — aplicado

### B1. Canonical — Secção 22.8b: provisionamento de tabelas por ambiente
**Ficheiro:** `WATCHERDB INTELLIGENCE V1/database/INSTALACAO_COMPLETA_UNIFICADA.sql`

**Problema:** 8 famílias da Secção 22 (`PERF_COUNTERS`, `PERF_COUNTERS_DETAIL`, `DB_SETTINGS`,
`SUSPECT_PAGES`, `AG_QUEUES`, `DBCC_HISTORY`, `SCHEDULER_HEALTH`, `JOB_DURATION`) nunca chamavam
`usp_setup_environment_tables`. Num **fresh install** criava-se só `_BLUE`/`_GREEN`, e o coletor
falharia ao escrever em `_BLUE_<ENV>` (via `fn_get_kpi_collection_target_env`) — 8 KPIs a falhar
silenciosamente a recolha. Mesma classe do incidente `WDB_KPI_MUTE` (Wave U).

**Fix:** bloco `22.8b` com 8 `EXEC dbo.usp_setup_environment_tables`, inserido **entre** o registo
Blue-Green (22.8) e as views (22.9).

**⚠️ ORDEM É CRÍTICA:** tem de ficar **depois** das tabelas base 22.1-22.7. Colocá-lo no bloco da
PARTE 4 (~linha 2537, onde estão as outras 13 famílias) seria **no-op silencioso** — as tabelas da
Secção 22 só existem ~10.000 linhas depois.

**Confirmado:** nenhuma das 8 famílias tem PK explícita nem coluna computed → clone-safe via
`SELECT * INTO`. (`ALWAYSON_STATUS` está correctamente excluído — tem `PERSISTED`.)

**Nota:** acrescentei também `'KPI_MSSQL_PERF_COUNTERS_DETAIL_STG'` à lista de registo da 22.8.
É **redundante** (já estava registado noutra secção, ~linha 11959) mas inofensivo (`IF NOT EXISTS`).

### B2. `OS_Boot_Time` — último reboot do SO
**Objetivo:** card no Overview com o reboot do **SO** (o `Uptime_Hours` existente é o arranque do
**serviço SQL**, coisa diferente).

**Porque NÃO se usa `systeminfo`:** exigiria WinRM/PowerShell remoto a cada servidor → nova
superfície de credenciais + conta de domínio a tocar nos servidores (viola Regra de Ouro #2).
`sys.dm_os_sys_info.ms_ticks` dá o mesmo em T-SQL puro com `sql_monitoring`.

**Coletor** `scripts/collectors/collect_inst_availability.py`:
```sql
(SELECT DATEADD(SECOND, -(ms_ticks/1000), GETDATE())
 FROM sys.dm_os_sys_info) AS OS_Boot_Time,
```
> `ms_ticks` = ms desde o arranque do SO. Dividir por 1000 e usar `SECOND` — `DATEADD(MS,...)`
> **estoura o int** acima de ~24.8 dias de uptime. Gotcha real.

+ `"OS_Boot_Time"` no `COLUMNS` + `pd.to_datetime(..., errors="coerce")` no `transform()`
(**sem `fillna`** — inventaria uma data de boot falsa).

**Canonical:** `OS_Boot_Time DATETIME2 NULL` na tabela base `KPI_MSSQL_INST_AVAILABILITY_STG`.
**Propaga sozinha:** loop genérico (~2167-2179) cria `_BLUE`/`_GREEN` via `SELECT TOP 0 *`, e
depois `usp_setup_environment_tables` gera as 6 variantes. Uma edição cobre as 8 tabelas.

**Passos na BD (executados pelo owner):** 8 `ALTER TABLE ... ADD OS_Boot_Time DATETIME2 NULL`
+ **`EXEC dbo.usp_create_active_view 'KPI_MSSQL_INST_AVAILABILITY_STG';`**

> 🔴 **PASSO QUE QUASE FICOU ESQUECIDO:** a view `_ACTIVE` é `DROP+CREATE` estático com `SELECT *`
> — **não se auto-actualiza**. Sem re-executar, a coluna existe na tabela mas **nunca chega ao
> portal**. Ordem obrigatória: ALTERs → re-EXEC view → deploy do coletor.

**Restart necessário:** `Restart-Service WatcherDBCollector -Force` (classe Python em cache).

**Valor:** comparar `OS_Boot_Time` com `Uptime_Hours` distingue **reboot planeado de patching**
vs **restart isolado do serviço SQL** (crash/manual). Sinal que o `systeminfo` não daria.

**Histórico:** ❌ não há. STG é snapshot com swap. `OS_Boot_Time` é timestamp absoluto (logo
"último reboot" funciona sempre), mas não há linha temporal de reboots. Se for preciso, o padrão
seria tabela append-only tipo `SERVER_OFFLINE_EVENTS`, disparada quando o valor muda.

---

## C. ACHADOS E DECISÕES (sem código) — relevantes para V6

### C1. 🔴 `never_validated` do CHECKDB está corrompido por falha de medição
`collect_dbcc_history.py` colapsa **três causas** em `Last_CheckDB_Date = NULL`:
- linha ~68: sentinela legítimo `'1900-01-01'` → NULL
- linhas ~74-77: `BEGIN CATCH` sem `ERROR_NUMBER()` → **qualquer erro** → NULL
- DB inacessível → NULL

**Evidência:** ~95% das instâncias reportam `never_validated` = 100% das DBs (93/93, 111/111,
107/107), enquanto outras têm datas reais. Padrão all-or-nothing = assinatura de falha de leitura,
não de hábito de DBA. Causa provável: **grants não uniformes na frota** (achado prévio de
2026-07-02: "3 scripts de grants divergentes", "`VIEW ANY DEFINITION` nunca aplicado").

**Consequências:**
1. O veredicto **não pode** escalar a Crítica com base em `never_validated` — ~95% da frota ficaria
   vermelha. Desenho corrigido: 3 estados, sendo `NULL` → **"Não comprovado"**, nunca Crítica.
   *Ausência de prova ≠ prova de ausência.*
2. ⚠️ **O claim comercial "94% da frota sem validação de integridade" está INSEGURO** — pode ser
   94% **não-mensurável**, não 94% **não-validado**. **Retirar de material comercial** até haver
   medição fiável.

**Fix desenhado, aprovado, NÃO aplicado (Item B):** `Collection_Status` (`VALIDATED` /
`NEVER_VALIDATED` / `COLLECTION_ERROR`) + `Error_Number` + `Error_Message` crus, **sem bucketing**
na v1 (classificar na v2 com dados reais). Coluna `Measurability` **aditiva** na
`KPI_MSSQL_INTEGRITY_VERDICT_VIEW` — **não reciclar a escala P1-P5** (é semântica de severidade).

### C2. ✅ Auto-resolução de eventos offline — NÃO há bug
Investigado a fundo e **refutado**. Confirmado por query: `ultimo_resolve = 2026-07-21 12:31`
(mesmo dia), `total_resolvidos = 9946`. O coletor de produção (`collect_server_ping.py`, serviço
`WatcherDBCollector`, PRD a cada 3 min) **regista e resolve**.

**Eventos abertos desde maio são genuínos:** `SQLADSPRD001/002/003` nem resolvem em DNS
("could not find host") → descomissionados a poluir o card. É **inventário sujo**, não bug.

> **Lição de processo (importante):** o CHANGELOG do V1 afirma *"Is_Resolved nunca é actualizada
> automaticamente"* — **está desatualizado** e induziu dois analistas ao mesmo erro. Além disso,
> havia **3 caminhos de coletor** (sync, async, serviço Windows) e só o terceiro é o vivo.
> **Confirmar qual é o caminho em execução antes de diagnosticar.** Não usar CHANGELOGs como
> fonte de verdade sobre comportamento actual.

### C3. Rota de dados morta — `INST_AVAILABILITY`
`KPI_MSSQL_INST_AVAILABILITY_STG` (tabela base) é alimentada por `usp_Collect_Instance_Availability`,
sproc legado que faz `TRUNCATE + INSERT @@SERVERNAME` (**1 linha**, só o host onde corre). As
`AGG_VIEW`/`DET_VIEW` leem **dessa tabela morta**. Dois consumidores V3.3 ainda as usam
(`helpers.py:1176`, `intelligence_kpis.py:1397`) → podem mostrar dados obsoletos.
Também `live_monitoring.py:908` lê a tabela base em vez de `_ACTIVE`.

### C4. `/server-offline/history` sem reconcile
`intelligence_kpis.py:2386-2432` e `intelligence/events.py:85-116` leem a tabela **raw**, sem o CTE
de reconciliação via `INST_AVAILABILITY` que as views AGG/DET/GROUPED já têm. O card principal
auto-cura em ~15 min; o **histórico mostra fantasmas até 7 dias**.

### C5. Tier: Maintenance Health = **Std**
O motor de cadência auto-calibrada **já é Std** (`FEATURE_MATRIX.md:70`, "Backup Status
schedule-based gap detection" — `BackupPatternAnalyzer` já em produção). **Não é tier creep.**
**Reservado a Pro:** auto-deteção de CommandLog/Ola (categoria Integrations), gap forecasting/ML,
baseline compare cross-instance.

### C6. Schema Wave X confirmado
`KPI_MSSQL_DBCC_HISTORY_STG` é **VIEW slot-aware** (union BLUE/GREEN conforme
`KPI_STG_ACTIVE_TABLE.Active_Slot`). Colunas: `Instance`, `Database_Name`, `Last_CheckDB_Date`
(datetime2), `Days_Since_CheckDB` (int), `Update_TS` (datetime2).

> ⚠️ **Não confiar em `Days_Since_CheckDB`** — é `int` calculado no momento da recolha; se um ciclo
> falhar, envelhece e **sub-reporta** a idade. **Recalcular** de `Last_CheckDB_Date`.

### C7. 🔴 Achado operacional accionável
**54 DBs de produção sem verificação de integridade há ~7,3 anos** (2674 dias):
`SQLHDSPRD212_I01` (28 DBs) e `SQLHDSPRD211_I01` (26 DBs). Estes têm **data real** — não são
vítimas do bug de medição do C1. Numa frota onde a Wave X já confirmou **3 corrupções activas**.
Também `SQLHDSGENPRD01/02_I01` (4 DBs cada, 142 dias).

### C8. Bloqueador comercial
`api/routers/queries/helpers.py:88` usa `use_windows_auth=True` — o caminho LIVE do
`performance.py` corre com conta de domínio, **contradiz a Regra de Ouro #2 e a mensagem
"banking-grade / só sql_monitoring"**. Foi a razão pela qual o Maintenance Health foi desenhado
como **agregador de leitura sobre a Intelligence**, e não como motor de queries live.

### C9. Concorrência (research com fontes)
Nenhum dos 6 concorrentes (SolarWinds DPA, Redgate SQL Monitor, Quest Spotlight, Idera SQL DM,
SentryOne, dbWatch) faz **cadência aprendida por (database × tipo de operação)**. Redgate usa
limiar **fixo de 7 dias** por instância; Quest exige que o DBA escreva a query e escolha os dias.
dbWatch é o mais próximo de adaptativo, mas para **recursos**, não cadência de manutenção — e
**executa** manutenção (o WatcherDB só reporta+prescreve).
**Nuance honesta:** "threshold adaptativo" já é comum em APM genérico — o diferenciador é aplicá-lo
à cadência de manutenção por database. Nicho defensável, **não** "primeiro do mundo".
**Evitar** claims tipo "zero falsos positivos" (não comprovável sem golden-set).

---

## D. PENDENTE — não aplicado em lado nenhum

| Item | Estado |
|---|---|
| **Item B** — `Collection_Status` no CHECKDB | Aprovado (GO-com-condições), diff pronto, não aplicado |
| **Maintenance Health** — analyzer + endpoint + tile | Desenhado; pilar CHECKDB limitado a "não comprovado" até Item B |
| **Coleta central de stats freshness** | Aprovada com 3 condições (template `collect_dbcc_history`, cadência 60 min, guards, 5 superfícies antes de shipped) |
| **Card de reboot do SO** (frontend) | Backend pronto; falta o card |
| **Zona F** — i18n dos 4 divergentes | Diferido |
| **Browser-test A1-A4** | ❌ Nunca feito |
| Corrigir CHANGELOG V1 desatualizado (C2) | Pendente |
| Limpar inventário (C2) | Pendente |

---

## B3. Hardening de boot — portal "Running mas morto" (aplicado 2026-07-21 fim de tarde)

**Sintoma (2 incidentes no mesmo dia):** Intelligence server (`SQLHDSTST505\I01`, TST) inacessível
→ o `create_app` pendura no import do `services/auth_service.py` → SCM diz Running, página estática
serve, todas as chamadas API abortam. **O V6 teve exactamente o mesmo comportamento de manhã**
(confirmado pelo owner: "o v6 ta com o mesmo problema") → **este fix é candidato directo a V6.**

**Anatomia:** `load_system_config()` corria **no import** (auth_service.py:463) → `pyodbc.connect`
com login timeout **60s** × `@retry_db_operation` (3 tentativas + backoff 1+2+4s) ≈ **~187s
bloqueado**; com DNS pendurado, pior. O `try/except: pass` só apanhava a falha no fim.

**Fix aplicado (V3.3):**
1. `services/auth_service.py` — `load_system_config()` movido para **thread daemon em background**;
   até carregar valem os defaults do módulo (mesmo comportamento que o except:pass antigo dava
   com a DB em baixo). Logs claros nos dois desfechos.
2. `watcherdb/core/settings.py` — `connection_timeout` **60 → 15** (é login timeout, não query).

**Propagação V6:** verificar se o V6 tem o mesmo padrão (`load_system_config()` at-import em
`services/auth_service.py` + `connection_timeout: 60` em `watcherdb/core/settings.py`) e aplicar
o mesmo par de alterações.

**Nota estratégica em aberto:** a Intelligence DB de "produção" vive num servidor TST instável —
para o piloto banking tem de migrar para infra de produção.

### B4. ⚠️ Armadilha do pipeline de coleta: INT nullable com None (2026-07-22)

O `base_collector.store()` usa `df.values.tolist()` + `fast_executemany=True`. **Colunas
numéricas (INT) com `None` misturado rebentam** com `22003 Numeric value out of range` —
e antes disso, `astype("Int64")` do pandas produz `pd.NA` que rebenta com
`Unknown object type NAType`. Strings NULL-able funcionam (padrão provado há meses);
INT nullable **nunca tinha passado** por este pipeline.

**Regra para novos coletores (V3.3, V6 e o futuro coletor de stats freshness):**
colunas numéricas emitem **sentinela** (`0` = sem valor/sem erro) em vez de NULL, ou a
coluna passa a string. Caso real: `Error_Number` do `collect_dbcc_history` — sucesso
grava `0`, o CATCH grava `ERROR_NUMBER()` (nunca NULL por definição). Duas rondas de
falha de storage nos 3 ambientes até isto ficar claro — não repetir a arqueologia.

---

## E. CHECKLIST DE PROPAGAÇÃO V6

- [ ] **Frontend:** grep V6 por `toggleDiskDrillDown`, `toggleMaximizeModal`, `resetModalMaximized`,
      `inv-modal-overlay`. Se não existirem → marcar N/A (V6 é subset).
- [ ] **i18n V6:** confirmar se tem `static/i18n/{pt,en,es}.json` com a mesma estrutura antes de
      propagar `disk.drill.*` e `ui.maximize`/`ui.restore`.
- [ ] **Infra partilhada:** as alterações B1/B2 são na BD comum → **V6 beneficia automaticamente**.
      Verificar apenas se o V6 tem **cópia própria** do coletor ou do canonical que precise de sync.
- [ ] **Paridade `backup_pattern_analysis.py`** V3.3 vs V6 (análise feita, resultado guardado no
      session.log do specialist) — reconciliar antes de estender para Maintenance Health.
- [ ] **C1 (never_validated)** afecta o KPI Integridade **também no V6** — a Wave X foi propagada.
      Aplicar o mesmo fix de desambiguação quando o Item B aterrar.
- [ ] **C8** (Windows auth) — verificar se o V6 tem o mesmo padrão em `performance.py`.

---

## F. SESSÃO 2026-07-23 (hardening + Item B fecho + modal 3 gráficos)

### F1. JÁ APLICADO DIRECTAMENTE NO V6 (não propagar — validar/commitar)
Commit próprio no repo V6 (bloco entregue ao owner). 4 fixes idênticos, 5 ficheiros:
- `services/web_service/service.py`: SvcStop com `should_exit`/`force_exit` + thread `daemon=True`
  (mata zombie na porta com código antigo pós-restart).
- `api/routers/intelligence_kpis.py:~4416`: connect do preload em `asyncio.to_thread`
  (connect pendurado deixa de bloquear o event loop → portal-tijolo).
- `watcherdb_main.py:~3437`: `GET /healthz` (liveness, zero DB) + `api/security.py` PUBLIC_PATHS.
- `services/auth_service.py:~320`: `load_system_config()` do import → background daemon thread (B3).
PENDENTE V6: restart do serviço (primeiro restart ainda com wrapper velho → pode precisar kill
manual UMA última vez) + browser test + commit se ainda não feito.

### F2. HERDA DE GRAÇA (BD/máquina partilhadas — nada a fazer no V6)
- `KPI_MSSQL_INTEGRITY_VERDICT_VIEW` +`Error_Number`/`Error_Message` (aplicado live pelo owner;
  canonical SECAO 16 + standalone WAVE_X sincronizados no repo V1).
- Fix DNS: entrada hosts `172.17.152.49  SQLHDSTST505` na máquina (serve os dois produtos).
  Porta real I01 = 50760 (dinâmica; porta estática = melhoria futura agendável).

### F3. PENDENTE PROPAGAÇÃO (portal V6 NÃO é superset — grep anchors primeiro)
1. **Drilldown integrity-unmeasurable** (backend V6): elif tuple ganha "integrity-unmeasurable";
   `_IG_WHERE["integrity-unmeasurable"] = "v.Measurability = 'NOT_MEASURABLE'"`; SELECT ganha
   `v.Collection_Status, v.Error_Number, v.Error_Message`. (Wave X propagou as variantes -p1/-p3/-p4;
   a -unmeasurable é nova de 22-23/07.)
2. **Card Integridade**: linha "Não mensurável (coleta falhou)" → kpi_type integrity-unmeasurable
   (+ `unmeasurable_count` no collect_integrity se o V6 tiver cópia própria do helper).
3. **Modal 3 gráficos interativos** (V3.3 anchors: verdictChartHtml/errnumChartHtml ~34868,
   composição integrityChartsRow, `data-verdict`/`data-errnum` no card ~36631, motor central
   `applyAllBackupFiltersWithMultiselect` ~40710 — ATENÇÃO: existe `_applyAllBackupFilters_LEGACY_UNUSED`,
   NÃO editar essa; funções `filterByVerdict`/`clearVerdictFilter`/`filterByErrNum`/`clearErrNumFilter`):
   - Distribuição por Veredicto (todas as modais integrity) com "?" tooltip simples.
   - Distribuição por Tipo de Falha (SÓ integrity-unmeasurable; rótulo 2571 amigável).
   - Filtros combináveis env+verdict+errnum; totais dos 3 gráficos atualizam com o filtro.
   - Strip "Porque a coleta falhou" no card (Erro N + mensagem + causa típica 2571/GRANT).
   NOTA: modal V6 é idiomático (nytLocalize, hero+chips) → ADAPTAR, não copiar.
4. **i18n 14 chaves novas** ×3 locales: chart.distribution_by_verdict, chart.distribution_by_failure,
   kpi_modal.{click_verdict_filter, verdict_p1, verdict_p3, verdict_p4, verdict_p5, why_failed,
   fix_grant, verdict_help, click_failure_filter, err_2571, err_unknown, err_generic}.
5. **Grid Overview 5 colunas** + card Reboot SO (já no item A deste doc — confirmar aplicado).
6. **Accordion nas modais** (design aprovado 23/07, docs/context/DESIGN_ACCORDION_MODAIS_2026-07-23.md):
   propagar ao V6 QUANDO shipped no V3.3, nunca antes.

### F4. LIÇÕES DA SESSÃO (aplicar em qualquer serviço/produto novo)
- Padrão hardening: ver memória `feedback-windows-service-boot-hardening` (4 defeitos + monitor 5 camadas).
- Precheck de porta em instância nomeada: memória `feedback-named-instance-port-precheck`.
- Coletor: 4 famílias paradas 13/05 + HIST archiving parcial + chaves `\` vs `_` — memória
  `project-collector-freshness-findings-2026-07` (decisões na próxima sessão; afetam V6 igualmente
  porque a BD é partilhada).
