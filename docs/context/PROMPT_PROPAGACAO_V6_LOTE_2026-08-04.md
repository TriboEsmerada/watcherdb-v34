# PROMPT — Propagação V3.3/V1 → V6 · Lote 2026-08-04 (migração do baseline)

Para a sessão AI do V6. Origem: sessão de 04/08, **infra partilhada V1**
(`WATCHERDB INTELLIGENCE V1`). Commits V1 (branch `wave-b-indexacao-dmv`):
`8fd593f` (canonical SECÇÃO 22 + manifest) + refinamentos do gate v1-intel em
`ce69d0e`/`e8c8d38` (04:00, DELETE da linha órfã, ANSI_NULLS, nota Maintenance).
Relacionado: `a6d5dcc` (poller FIND-108, sql_monitoring, mesma infra partilhada).
Regras aplicáveis:
`v33-v6-propagation-rule` (fixes/melhorias propagam) e
`v6-portal-not-superset` (**grep anchors no V6 primeiro**; aqui NÃO há
portal — é backend/infra). Isto é uma **mudança de infra partilhada**:
afecta V3.3 + todos os tiers Pro + V6 simultaneamente.

---

## 0. A ideia em uma frase (LER antes de tudo)

O **motor de baselines estatísticas** (`usp_compute_kpi_baseline`) deixou
de correr como **Windows Scheduled Task no workstation do dev** e passou a
ser um **SQL Agent job no servidor** (`WatcherDB_Baseline_Compute`, diário
04:00). Motivo: a task no workstation parou **3×** (03/06, 12/06, 24/07 →
**11 dias** sem baseline, ninguém viu) sempre pelas mesmas causas do
workstation — **PC desligado às 03:00** + **firewall a cortar o SQL Browser**
(08001). Descoberta-chave: a proc é **auto-contida** (lê `KPI_OS_*_HIST` e
faz `MERGE` em `WDB_KPI_BASELINE`, tudo dentro da própria
`WatcherDB_Intelligence`) — **não precisa de Python**, logo cabe num SQL
Agent job, imune às 3 causas. Espelha o `WatcherDB_Anomaly_Detection`, que
já é exactamente esse padrão (EXEC de proc num job, e nunca falhou por
estas causas).

**Regra geral que fica** (aplica ao V6 e a qualquer trabalho agendado
futuro): *se o trabalho é uma proc auto-contida na BD (EXEC), pertence a um
SQL Agent job no servidor — não a uma Scheduled Task no workstation. O
workstation-como-servidor (PC desligado + firewall) é a fragilidade-raiz.*

## 1. BD partilhada — o que o V6 herda vs o que tem de espelhar

- **Se o V6 aponta para a MESMA `WatcherDB_Intelligence` física:** herda o
  job já criado — **nada a executar**. O baseline volta a correr no
  servidor automaticamente. Confirmar só (§4).
- **Se o V6 tem canonical próprio** (`INSTALACAO_COMPLETA_UNIFICADA.sql` ou
  equivalente) com receitas de jobs / seed do manifest: **espelhar as 3
  edições** abaixo, para um fresh install do V6 nascer server-native.

## 2. As edições no canonical V1 (a espelhar se o V6 tiver o seu)

Ficheiro origem:
`WATCHERDB INTELLIGENCE V1/database/INSTALACAO_COMPLETA_UNIFICADA.sql`.
As edições 4 e 5 nasceram do gate `watcherdb-v1-intel` (04/08) — ler.

1. **Receita do job `WatcherDB_Baseline_Compute`** na SECÇÃO 22, logo a
   seguir à do `WatcherDB_Anomaly_Detection`. `IF NOT EXISTS` idempotente;
   `sp_add_job` (owner `sa`, category `Database Maintenance`);
   `sp_add_jobstep` (subsystem `TSQL`, database `WatcherDB_Intelligence`,
   command `SET QUOTED_IDENTIFIER ON; SET ANSI_NULLS ON; EXEC
   dbo.usp_compute_kpi_baseline @Force_Full = 0, @Debug = 0;`,
   `on_fail_action = 2`); `sp_add_schedule` (`freq_type = 4` diário,
   `active_start_time = 40000` = **04:00:00**); `sp_attach_schedule`;
   `sp_add_jobserver @server_name = N'(local)'`.
2. **Seed do manifest** (`WDB_SCHEDULED_WORK_MANIFEST`) — nova linha
   **AGENT_JOB**: `WatcherDB_Baseline_Compute`, cadência 1440, staleness
   1560, `Enabled_Expected = 1` (a seguir à linha do Anomaly_Detection).
3. **Remover** do seed a linha **SCHEDULED_TASK**
   `WatcherDB_Intelligence_BaselineCompute_PRD` (deixei um comentário-
   breadcrumb a explicar a migração). Num fresh install não existe task no
   workstation, logo não deve ser declarada como esperada — senão o
   verificador (Wave D, `V1_DECLARADO_AUSENTE`) dispararia um falso achado.
4. **`DELETE` idempotente da linha órfã** (gate v1-intel): o MERGE do seed
   só faz `INSERT WHEN NOT MATCHED` e a remoção do ponto 3 **não retroage**
   — em hosts onde a linha SCHEDULED_TASK já foi semeada (foi, a 03/08 pela
   Wave D Fase 2), ela ficaria órfã. Um `DELETE ... WHERE Work_Name =
   N'WatcherDB_Intelligence_BaselineCompute_PRD' AND Work_Type =
   'SCHEDULED_TASK'` **fora** do `IF NOT EXISTS` da secção (senão não corre
   em re-runs) limpa-a; no-op em fresh install. **Se o V6 tiver esta linha
   semeada no seu manifest, precisa do mesmo DELETE.**
5. **Horário 04:00 e não 03:00** (gate v1-intel): o job
   `WatcherDB - Maintenance (Index + Statistics)` corre **diário 03:00**
   (a nota do manifest dizia "semanal domingo" — estava errada, corrigida
   no mesmo lote) e pode fazer `ALTER INDEX REBUILD` (offline em Standard,
   Sch-M lock) nas tabelas `KPI_OS_*_HIST` que o baseline lê com NOLOCK —
   NOLOCK não escapa a Sch-M. Baseline a 04:00 desfasa da janela do
   Maintenance (`max 45min` → acaba ~03:45). Se o V6 partilha estes jobs,
   herdar o desfasamento.

## 3. Nota de política (identidades)

Como o job corre no **contexto da conta do SQL Agent** (provado:
`Executed as user: TAPNET\ua_SQLHDSTST505_ag`), a excepção histórica
"`sql_monitoring` com `GRANT EXECUTE` na proc" **deixa de ser necessária**
para o caminho automático — fica só para o wrapper Python manual de
recurso (`scripts/collectors/compute_baseline.py`, que ganhou hoje um
override `BASELINE_MASTER_SERVER` para ligar por `ip,porta` e contornar o
Browser). Relevante para a wave de separação de identidades (FIND-104, em
design): é um consumidor de escrita ad-hoc a menos em `sql_monitoring`.

## 4. Validação V6 (após herdar / espelhar)

```sql
-- 1) o job existe e está agendado para as 04:00 (active_start_time=40000):
SELECT j.name, s.active_start_time, js.command
FROM msdb.dbo.sysjobs j
JOIN msdb.dbo.sysjobschedules jss ON jss.job_id=j.job_id
JOIN msdb.dbo.sysschedules s     ON s.schedule_id=jss.schedule_id
JOIN msdb.dbo.sysjobsteps js     ON js.job_id=j.job_id
WHERE j.name = N'WatcherDB_Baseline_Compute';

-- 2) o baseline está fresco (Last_Computed recente, não parado):
SELECT Kpi_Type, COUNT(*) AS instancias, MAX(Last_Computed) AS ultimo
FROM dbo.WDB_KPI_BASELINE GROUP BY Kpi_Type;
```

**Prova de referência da sessão V3.3/V1** (já feita na BD viva): disparo
manual correu `OK` sob a conta do Agent; com `@Force_Full=1` forçado o
`Last_Computed` saltou de 11:45 → 17:17 (lê **e escreve** sob a conta do
Agent); incremental reposto a `@Force_Full=0`. Nota sobre o incremental: o
guard de 25h na proc com corrida diária às 04:00 recalcula em **dias
alternados** (24h cai dentro do guard, 48h não) — aceitável para janela
rolling 30d; se o V6 quiser recompute diário garantido, é decisão à parte
(mexer no guard ou na cadência, não feito aqui).

## 5. Pista para o V6, à parte (não é deste lote)

A `WatcherDB V6 Audit Archive` (DORA Art.28) continua **atestada mas não
instalada** — é um item V6-side. Vale a pena aplicar-lhe o mesmo teste
desta migração: *é uma proc/script auto-contido? então é um SQL Agent job
no servidor, não uma Scheduled Task num workstation.* O `run_audit_
archive.py` é Python, por isso não colapsa num job TSQL directo — mas o
princípio de "servidor sempre ligado, não workstation" aplica-se na mesma.
