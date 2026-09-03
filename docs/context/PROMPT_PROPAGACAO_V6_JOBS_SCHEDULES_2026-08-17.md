# PROPAGAÇÃO V6 — lote 17/08/2026: módulo Jobs ressuscitado, agendamentos, próxima execução no KPI, Jobs de Backup + origem externa

> Para a AI do V6. Regras + contratos explicados (não só o diff). Origem: sessão 2026-08-17 em V3.3,
> plano `docs/context/PLANO_JOBS_SCHEDULES_BACKUP_2026-08-17.md`. Regra: **portal V6 NÃO é superset** —
> grep das âncoras ANTES de assumir que o alvo existe.

## 0. O que mudou na BD partilhada — nada

Zero DDL. O KPI passa a **ler** `KPI_MSSQL_AGENT_JOBS_STG` (colunas já existentes; tabela única sem BLUE/GREEN, FIND-20260506-001). Herda via BD: nada a instalar.

## 1. P0 — verificar se o V6 tem o MESMO bug (módulo Jobs a zeros)

**Sintoma no V3.3:** aba Jobs com Total Jobs = 0 (HTTP 200, sem cartão de erro) desde 16/04. Causa: `JobsAnalysisResponse` (`api/models.py`) exigia `server_id` sem `extra="allow"`; o `result` de `get_jobs_analysis` não o tinha → `ResponseValidationError` → handler devolvia `200 {"success":true,"warning":...}` **sem dados**. `/trends` e `/schedule-conflicts` idem (faltava `success`).

Verificar no V6:
```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V6"
Select-String -Path api\models.py -Pattern 'class JobsAnalysisResponse' -Context 0,6
Select-String -Path . -Pattern 'ResponseValidationError' -Recurse -Include *.py | Select-Object Path,LineNumber
Select-String -Path services\web_service\logs\stderr.log* -Pattern 'ResponseValidationError on /api/jobs' | Measure-Object
```
Se o modelo exigir `server_id`/`success` sem `extra="allow"` e o handler devolver placeholder → aplicar o mesmo fix:
- modelos: `model_config = ConfigDict(extra="allow")`, `success: bool = True`, `server_id: Optional[str] = None`, `total_jobs: int = 0`, `all_jobs: Any = None`;
- `jobs.py`: `'success': True, 'server_id': server_id` nos 3 endpoints; `'all_jobs': all_jobs` (array; o portal usa `.length/.map`);
- handler: **devolver `exc.body`** (`jsonable_encoder`) e `logger.error` com os campos (`exc.errors()[:3]` → `loc`). Nunca placeholder 200 sem dados.

## 2. Backend `jobs.py` — contrato novo do payload `/api/jobs/server/{id}`

- Sem `msdb.dbo.agent_datetime` (UDF exige EXECUTE; regra sql_monitoring SELECT-only; não-sargável). Helper `_agent_dt(date_col,time_col)` = `CASE WHEN d > 0 THEN DATEADD(SECOND, hh*3600+mm*60+ss, CONVERT(DATETIME, CAST(d AS CHAR(8)), 112)) END` + pré-filtro `h.run_date >= CONVERT(INT, CONVERT(CHAR(8), DATEADD(...),112))`.
- Novo `job_schedules: [...]` (1 linha por job×schedule; **códigos crus** de `sysschedules`: `freq_type, freq_interval, freq_subday_type, freq_subday_interval, freq_relative_interval, freq_recurrence_factor, active_start_time, active_end_time, active_start_date, active_end_date, schedule_enabled, job_enabled, next_run_datetime`). Texto legível é do portal (i18n) — **nunca PT no SQL**.
- `all_jobs[]` ganha `schedule_count`, `has_active_schedule` (schedule com enabled=1) e `backup_type_classified` (FULL/DIFF/LOG/OTHER via `helpers.classify_backup_type` — o MESMO do KPI; só para nomes com backup/bkp; senão `null`).
- Novos totais: `total_scheduled_jobs`, `jobs_without_active_schedule`.

## 3. KPI global Backup Failed (`intelligence_kpis.py`, branch backup-failed/backup-log-failed)

LEFT JOIN a `KPI_MSSQL_AGENT_JOBS_STG aj ON aj.JobId = f.Job_Id AND LTRIM(RTRIM(UPPER(REPLACE(aj.Instance,'\','_')))) = LTRIM(RTRIM(UPPER(f.Instance)))` — **o REPLACE é obrigatório** (AGENT_JOBS grava `@@SERVERNAME` cru com backslash; EXEC_FAILURES é underscore). Colunas novas na row: `Next_Run_Date, Has_Schedule, Job_Enabled, Job_Last_Run_Status, Job_Last_Run_Date, Jobs_Snapshot_TS, Job_Missing_In_Snapshot`.

Portal (modal): linha **"Próxima execução do job"** (nunca "próximo backup" — a row não tem Database). Regras: `Job_Enabled=0` → "desabilitado, não corre sozinho" (sem data); `Has_Schedule=0` → "sem agendamento no Agent" + hint ferramenta externa; `Next_Run_Date` no passado → "devia ter corrido às X e não correu"; `Jobs_Snapshot_TS` > 15 min → badge stale; JOIN NULL → "sem informação". Âncora V3.3: `function _kpiJobNextRunHtml`; inserção no branch `kpiType.includes('backup')` após "Ultimo Backup". Grep no V6: `Ultimo Backup:` / `bkpStepName`.

## 4. Portal aba Jobs

Âncoras V3.3: `renderJobsAnalysis`, `id="schedules-section"`, `_formatJobSchedule` (decoder de `freq_type` etc.), cards `jobs-overdue`/`jobs-no-schedule`/`jobs-next-24h` em `CARD_HELP_TEXTS`, aviso `totalJobs === 0` (estado vazio explícito, nunca "0" liso), filtro `filterJobTable/resetJobFilters/updateJobFilterDropdowns` **tab-scoped** (`_jobsFilterRoot()` = `.tab-content.active`) e `'schedules-section'` no array `sections`. `escapeHtml` nas linhas de all/disabled/maintenance.

Grep no V6 antes: `renderJobsAnalysis`, `alljobs-section`, `filterJobTable`. Se o V6 não tiver a aba Jobs com estas secções, não propagar o portal — só o backend §2 (contrato).

## 5. Portal aba Backup

- Secção `failed-backup-jobs-section` passou a **"Jobs de Backup (N · X falhados)"**: `all_jobs` com `backup_type_classified`, agendamento (`job_schedules` via `_formatJobSchedule`), última/próxima; falhado = `last_run_status==='Falhou'` (estado actual, sem janela); sub-lista "falhas nas últimas 24h" (o `failed_jobs`, agora com `job_name` — o bug `j.name` dava sempre 0). HTML construído em `backupJobsSectionHtml` antes do `content.innerHTML`.
- **Origem do backup**: `/summary` items ganham `backup_source = {FULL|DIFF|LOG: {source: VIRTUAL_DEVICE|DISK|TAPE|URL|UNKNOWN, tool, device_type, physical_device, user_name, is_external}}` (`modules/monitoring/backup_analysis.py`: `classify_backup_source`, query de últimos backups com `user_name/media_set_id` + `OUTER APPLY backupmediafamily`). Portal: coluna "TDP" → "Origem" (`_backupSourceBadges`), painel "Backups geridos por ferramenta externa (TDP/…)" quando há bases externas.
- **Próximo esperado** por DB/tipo: `next_expected` do `/patterns` (padrão histórico R+8) na célula "Padrão" — rótulo distinto do Agent; passado = ⚠.
- Help `bkp-jobs-failed` reescrito (o que é / falhado / ferramenta externa / janelas).

Grep no V6: `failed-backup-jobs-section`, `bkp-jobs-failed`, `backupIssuesTbody`, `_pattern =`. Se o módulo Backup do V6 não tiver `_pattern`/patterns fetch, aplicar só a secção Jobs de Backup.

## 6. i18n

83 chaves novas em `jobs.*`, `kpi_modal.*`, `backup.*` nos 3 locales (ver diff de `static/i18n/*.json`). PT em grafia pós-AO90 (teste `test_pt_uses_post_ao90_spelling`: ativo, não activo).

## 7. Testes

`tests/unit/test_jobs_schedules_wave_20260817.py` (18 testes, sem BD): modelos, ausência de agent_datetime, helper inline, classificador de origem, JOIN normalizado, i18n das chaves novas, âncoras do portal. Copiar e ajustar âncoras ao V6.

## 8. Semântica a explicar ao DBA (não muda com código)

- KPI global = falhas de job dos **últimos 7 dias** recolhidas pelo collector (o "unresolved" não dispara porque `Database` vem NULL do V1 — FIND-20260817-102); aba Backup = estado actual do job + 24h ao vivo. Rótulos dizem a janela.
- "Sem agendamento no Agent" **não é alarme**: TDP/Commvault disparam via `sp_start_job` ou nem usam jobs; o "próximo esperado" vem do padrão histórico.
