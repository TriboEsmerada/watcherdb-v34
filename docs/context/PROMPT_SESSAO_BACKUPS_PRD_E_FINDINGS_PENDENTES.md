# PROMPT — sessão seguinte: backups de PRD + findings por registar

> Nome por **conteúdo**, não por data. Origem: sessão de 2026-07-29, que começou
> num incidente de DNS e acabou a descobrir 26 bases de PRD sem backup há mais de
> um mês. O assunto sério é a **secção 3**; o resto é rasto por fechar.

Cola isto numa sessão nova:

---

Lê `docs/context/CONTEXT.md` (entradas 2026-07-29) e este ficheiro. Executa em OODA,
modo consultor + GO por lote, memórias owner activas. **Prioridade 1 é a secção 3.**

## 1. Estado — o que já está feito e commitado

Branch `wave-b-indexacao-dmv` (working tree partilhado com a sessão da Wave B).

| Commit | O quê |
|---|---|
| `56f3671` / `4829478` | incidente DNS + passo 0 da Wave Cobertura (runbook, CONTEXT, 4 findings) |
| `67618b6` | secção 8 do runbook: git com sessões concorrentes |
| `68ebd4c` | FIND-107 e FIND-108 |
| `50b89e9` | `is_damaged` render condicional + doc PT/EN corrigida |
| `7e9c0fd` | **fix V1**: `HasSchedule` e `collect_backup_jobs_disabled` passam a ver agendamentos desligados |
| `ed1f737` | documentação dos KPIs de backup nos três locales |

**Validado:** `DBA_FULL_BACKUP` em `SQLMDMQLT03\I01` dá `HasSchedule` ANTES=1, DEPOIS=0.
12/12 blocos `<script>` OK. AST OK nos dois collectors.

**Por confirmar:** o `Restart-Service WatcherDBCollector` foi feito? Sem ele o fix
está commitado e sem efeito. Verificar no ciclo seguinte se o KPI
"Jobs de Backup Desativados" subiu.

## 2. Correcções de facto desta sessão (não repetir os erros)

- O 5.º argumento do `_advRow` é chave de **drill** (`showProblematicInstances`),
  **não** de documentação. Cruzá-lo com ids de doc produz ~10 falsos positivos.
- As entradas `backup-jobs-disabled`, `jobs-failed`, `db-availability-*` etc. **não**
  são órfãs: renderizam como *tiles* de KPI, superfície diferente das linhas de card.
- São **cinco** registos mantidos à mão, não quatro: `KPI_METADATA` (`portal:32156`),
  registo de documentação (`portal:38657+`), texto de ajuda (`~34811`), destino de
  tab (`~34789`), chave de drill (`_advRow`).
- SIMPLE recovery **não** afecta backups diferenciais. Só bloqueia `BACKUP LOG`.
- Os comentários dentro das strings SQL dos collectors são `--`, não `#`.

## 3. PRIORIDADE 1 — 26 bases de PRD sem backup há mais de um mês

Varredura feita a 2026-07-29 no Intelligence. Instâncias com o FULL mais recente
(de qualquer base) com mais de 7 dias:

| Instância | Env | Bases | Sem FULL | Sem DIFF |
|---|---|---|---|---|
| `SQLHDSQLT301_I02` | QLT | 5 | **83 dias** | nunca teve |
| `SQLMDMQLT03_I01` | QLT | 12 | 37 | 1 |
| **`SQLHDSPRD405_I01`** | **PRD** | 1 | **36** | 34 |
| **`SQLHDSPRD201_I01`** | **PRD** | 7 | 20 | **37** |
| **`SQLHDSPRD408_I01`** | **PRD** | 18 | 19 | 34 |
| **`SQLHDSPRD214_I01`** | **PRD** | 15 | 14 | 0 |
| **`SQLHDSPRD403_I01`** | **PRD** | 9 | 13 | 13 |

**405, 201 e 408 — 26 bases — não têm nem full nem diferencial há mais de um mês.**

### Causa confirmada no `SQLMDMQLT03_I01`

```
DBA_FULL_BACKUP   enabled=1   DBA_FULL_BACKUP_SCHEDULE enabled=0   semanal, Domingo 20:00
```

Job activo, **agendamento desligado**. Último full: Domingo 21/06. Cinco semanas.
Invisível aos três KPIs (`Full falhou` não tinha execuções para contar,
`Jobs Desativados` via `enabled=1`, `HasSchedule` via a linha do agendamento a existir).

O backup é **TSM/TDP** (`cmd.exe /c "C:\Program Files\Tivoli\TSM\TDPCMD\sqlDiff_I01.cmd"`),
com `output_file_name = NULL` — o step não captura output, por isso não há mensagem
de erro nenhuma há 23 dias.

### Passo 1 — confirmar se o padrão se repete nas cinco de PRD

Correr **em cada instância**, com `sql_monitoring` (se faltar permissão em `msdb`,
usar a sessão do owner):

```sql
USE msdb;
SELECT j.name, j.enabled,
       s.name AS Agendamento, s.enabled AS Sched_Enabled,
       s.freq_type, s.freq_interval, s.active_start_time
FROM msdb.dbo.sysjobs AS j
LEFT JOIN msdb.dbo.sysjobschedules AS js ON js.job_id = j.job_id
LEFT JOIN msdb.dbo.sysschedules    AS s  ON s.schedule_id = js.schedule_id
WHERE j.name LIKE 'DBA_%BACKUP%'
ORDER BY j.name;
```

`freq_interval` é bitmask semanal: 1=Dom, 2=Seg, 4=Ter, 8=Qua, 16=Qui, 32=Sex, 64=Sáb.
126 = Seg-Sáb.

**Se as cinco tiverem o agendamento de FULL desligado, foi acção em massa — e o
motivo importa mais do que o fix.** Perceber antes de religar.

### Passo 2 — remediação (MUTAÇÃO, decisão do owner)

```sql
USE msdb;
EXEC msdb.dbo.sp_update_schedule
     @name = N'DBA_FULL_BACKUP_SCHEDULE',
     @enabled = 1;
```

Não correr às cegas: um FULL de 18 bases a arrancar sem aviso tem impacto, e
alguém desligou aquilo deliberadamente a 21/22 de Junho.

### Passo 3 — capturar output (evita o próximo silêncio de 23 dias)

```sql
USE msdb;
EXEC msdb.dbo.sp_update_jobstep
     @job_name = N'DBA_DIFF_BACKUP', @step_id = 1,
     @output_file_name = N'C:\Temp\DBA_DIFF_BACKUP_I01.log',
     @flags = 2;
```

Confirmar que a conta de serviço tem escrita na pasta.

### Ponto aberto

Cerca de 20 bases em `SQLMDMQLT03_I01` (família `INFA_*`, `TAP_IDQ`) sem backup
desde Março de 2026 — oito delas desde **Março de 2024**. Não é problema de job:
é decisão sobre se ainda estão em uso.

## 4. Findings por registar em `findings-inbox.md`

Próximo número livre: **109**. Sistema compacto (1XX). Ficheiro fora da zona de
escrita da AI — exige WAIVER com GO explícito do owner.

### FIND-20260729-109 — KPIs irmãos do card Backups contam unidades diferentes

- **Severity:** P1 · **Category:** ux · **Owner:** watcherdb-v33-specialist
- **Evidence:** `Diff falhou: 7` no card correspondia a **1 job, 2 instâncias,
  10 noites** — não a 7 bases. O KPI `falhou` conta **eventos**; o `sem checksum`
  conta **entidades deduplicadas** por (Instância, Base) e diz isso na documentação.
  Dois números lado a lado, unidades diferentes, nada que o indique. Agravado por
  `collect_server_ping.py:1450` (*"Conservativo: Database NULL ou type OTHER não
  filtram"*): as 7 linhas tinham `Database` vazio, logo nunca podem ser marcadas
  como recuperadas e acumulam até à retenção de 14 dias. **O número cresce com a
  duração da avaria, não com a sua amplitude** — indistinguível de 7 bases partidas.
- **Recommendation:** deduplicar por (Instância, Job) ou declarar a unidade no card.
  Para linhas sem `Database`, contar a ocorrência uma vez e mostrar a duração
  (*"falha desde 17/07"*) em vez de repetir a contagem por noite.

### FIND-20260729-110 — KPIs de LOG ignoram o modelo de recuperação

- **Severity:** P1 · **Category:** coverage · **Owner:** watcherdb-v1-intel-specialist
- **Evidence:** os limiares de atraso de LOG são warning 1h / critical 2h
  (`helpers.py:1308`). Uma base em SIMPLE **não pode** ter backup de log
  (Msg 4208) e vai a CRÍTICO em duas horas. Zero referências a modelo de
  recuperação em toda a árvore `api/routers/intelligence/`. O collector **já
  recolhe** o dado: `recovery_model_desc AS RecoveryModel` em `collect_kpi.py:315`.
  **Caso de produção imediato:** a `WatcherDB_Intelligence` passou a SIMPLE a
  2026-07-29 (decisão do owner); tinha 477 backups de log em 20 dias.
- **Recommendation:** excluir bases em SIMPLE dos KPIs de LOG, ou classificá-las
  como `NOT_MEASURABLE`. Para SIMPLE, "sem backup de log" não é atraso: é
  **não aplicável**. O dado já existe, só não é consultado.

### FIND-20260729-111 — `Full falhou` é cego a backups externos

- **Severity:** P0 · **Category:** coverage · **Owner:** watcherdb-customer-success-persona
- **Evidence:** o KPI conta falhas de jobs do SQL Agent. A frota faz backup por
  **TSM/TDP**, e parte da cadeia é agendada do lado do TSM — não passa pelo Agent.
  Onde passa (`CmdExec`), o Agent só vê o exit code do `cmd.exe`, não o resultado
  do TSM. Resultado medido: `SQLHDSPRD405/201/408` sem full nem diff há mais de um
  mês, e o card a mostrar **`Full falhou: 0`**. Tecnicamente correcto — não há job
  a falhar — e operacionalmente a tranquilizar. O sinal existe no
  `Backups em Atraso: 623`, diluído e com o mesmo peso visual que o zero verde.
  **Assimetria a explorar:** `msdb.dbo.backupset` regista qualquer backup,
  independentemente do motor; `sysjobhistory` só regista o que passa pelo Agent.
- **Recommendation:** hierarquizar. Primário e universal: tempo desde o último
  backup bem-sucedido (`backupset`). Secundário e dependente de regime: falhas de
  jobs, com o regime declarado. Detecção **por instância** — a frota é mista
  (há servidores com os jobs `_LOCAL` nativos activos e o TSM desligado). O
  `_source_label` do `DatabaseBackupPatternAnalysis` já classifica em
  sysjobs / histórico R+8 / **inferido** e despeja-o num `logger.info`: é o
  detector de regime, já construído, que nunca chega à API. Decisão do owner
  2026-07-29: o WatcherDB **adapta a monitorização** ao regime; **não** passa a
  fazer backups.

### FIND-20260729-112 — `HasSchedule` verificava existência, não actividade

- **Severity:** P1 · **Category:** reliability · **Owner:** watcherdb-v1-intel-specialist
- **Status:** **fixed** em `7e9c0fd`, pendente de validação pós-restart
- **Evidence:** `collect_agent_jobs.py:91` fazia `EXISTS(sysjobschedules)` sem
  verificar `sysschedules.enabled`. `collect_backup_jobs_disabled.py:87` filtrava
  só por `sj.enabled = 0`. Um job activo com todos os agendamentos desligados
  passava entre os três KPIs de backup. Caso real: `DBA_FULL_BACKUP`, 5 semanas.
- **Nota de processo:** mudança em infra partilhada V1 **sem gate** do
  `watcherdb-v1-intel-specialist`, que tem direito de veto. Pedir parecer
  a posteriori — nem que seja para confirmar que nenhum consumidor do
  `HasSchedule` depende da semântica antiga.

### FIND-20260729-113 — O KPI de jobs desactivados conta o par intencional

- **Severity:** P1 · **Category:** ux · **Owner:** watcherdb-v1-intel-specialist
- **Evidence:** cada instância tem **dois conjuntos** de jobs de backup — TSM e
  `_LOCAL` (mais variantes tipo `_TAP_ORS`) — e um deles está sempre desligado, de
  propósito. Em `SQLMDMQLT03_I01` o KPI passa a marcar **6 jobs: 1 problema real e
  5 de ruído estrutural** (83%). O ruído é **anterior** ao fix `7e9c0fd`; o fix
  acrescenta o sinal certo a um sítio onde ele fica enterrado.
- **Recommendation:** critério sem configuração — **um job desactivado cujo irmão
  de mesmo nome-base está activo é alternativa intencional, não esquecimento**
  (`DBA_FULL_BACKUP` vs `DBA_FULL_BACKUP_LOCAL`). Filtrar o par antes de contar.
  Mesma família do `sem checksum` com 1153 a dominar o card, já removido a 28/07.

### Entrada para o `CONTEXT.md`

```
- 2026-07-29 | Claude+owner (OODA, cont.) | BACKUPS DE PRD PARADOS -- achado maior do dia, a partir de uma pergunta sobre o card. Varredura do Intelligence: 7 instancias com FULL mais recente >7 dias, das quais 5 em PRD; SQLHDSPRD405/201/408 (26 bases) sem full NEM diferencial ha mais de um mes; SQLHDSQLT301_I02 com 83 dias e sem diferencial nenhum. CAUSA confirmada em SQLMDMQLT03_I01: DBA_FULL_BACKUP com enabled=1 e DBA_FULL_BACKUP_SCHEDULE com enabled=0 (semanal, Domingo 20:00) -- job activo, agendamento morto desde 21/06. INVISIVEL aos 3 KPIs: Full falhou nao tinha execucoes para contar, Jobs Desativados via enabled=1, HasSchedule via a linha do agendamento existir. Backup e TSM/TDP via CmdExec com output_file_name=NULL, logo 23 dias de falhas sem uma unica mensagem de erro. FIX aplicado (7e9c0fd, V1 infra partilhada, SEM gate v1-intel -- pedir parecer a posteriori): HasSchedule passa a exigir sysschedules.enabled=1 e collect_backup_jobs_disabled passa a apanhar jobs activos sem agendamento; validado ANTES=1/DEPOIS=0 no caso real, AST OK. Doc dos KPIs alinhada nos 3 locales (ed1f737) -- inclui ES do backup-no-checksum, que ficou 2h a mentir depois de eu ter corrigido PT/EN e declarado coerente (3a ocorrencia do mesmo padrao no mesmo dia, a 3a minha: argumento a favor do acoplamento da FIND-108). PENDE: Restart-Service WatcherDBCollector; agendamentos das 5 instancias PRD; findings 109-113 por registar.
```

## 5. Outros pendentes, por ordem

1. **SSIS** — decisão sobre `WatcherDBSSIS` (`Auto` mas `Stopped`, a apontar para
   `C:\BKP PC TAP - 21012026\...\WATCHERPKG`). Fecha a `FIND-20260506-102`, que a
   limpeza de 29/07 deixou 2/3 resolvida.
2. **Bloco 2 da Wave Cobertura, peças 3 e 4** — `_advRow` ganha chave de
   documentação e falha visível (`FIND-108`); par checksum + danificado no tab
   Backups (item 4 da Prioridade 2 do prompt pós-Wave-A).
3. **Bloco 3** — `FIND-104` (contraste em 4 componentes, causa-raiz confirmada:
   hex pastel inline em `portal:19049-19070`) e `FIND-106` (`Avg Livre` não
   ponderado). Ambas no portal, a 106 no mesmo modal da 104.
4. **Bloco 4** — collector a consumir a porta aprendida da Wave A. Resolve a
   `FIND-102` na raiz em vez de a mitigar. Gate `v1-intel` obrigatório.
5. **Propagação V6** — a `FIND-106` já nasce com o ponteiro identificado
   (`WATCHERDB_V6/api/routers/intelligence_kpis.py:2883`, mesmo `AVG(Percent_Free)`).
6. **Entrada de documentação para "Backup Danificado"** — não existe em nenhum dos
   cinco registos. Precisa de estrutura completa e dos três locales.
7. **Renomear o KPI `backup-jobs-disabled`** — o título diz "Desativados" e ele
   passou a contar também jobs sem agendamento. Decisão de produto, em aberto.

## 6. Avisos operacionais

- **Working tree partilhado.** `git switch` muda a branch para a sessão paralela
  também. `CONTEXT.md` e `findings-inbox.md` exigem `git add -p` — ver secção 8 do
  `COMANDOS_UTEIS_INFRA_LOCAL.md`.
- **Restarts:** edit em collector V1 ⇒ `Restart-Service WatcherDBCollector`
  (classe em cache na RAM). Edit em backend V3.3 ⇒ `Restart-Service` V33.
  Frontend ⇒ só `Ctrl+Shift+R`.
- **Validação obrigatória:** blocos `<script>` do portal por `node --check`
  (baseline 12/12) e `ast.parse` nos ficheiros Python.
- **DNS do workstation** — se voltarem falsos offline em massa, é a 4.ª ocorrência.
  Runbook em `COMANDOS_UTEIS_INFRA_LOCAL.md`, secção 2.3: **toggle de placa de
  rede**, não reboot.
