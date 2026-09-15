# B2a-2b e B2b-2 — recuperar a janela perdida e agregados horários do errorlog (desenho, 15/09)

> Rascunho para o gate do guardião do recolhedor (watcherdb-v1-intel-specialist, com veto). Nada aplicado.
> Base: B2a-2a em produção (V1 7865e42, migration 014; WDB_ERRORLOG_READ_STATE com Read_Until_Server_TS por instância).

## B2a-2b — recuperar a janela perdida (só código, sem migration)

**Problema.** Janela fixa de 65 min. No incidente de DNS de 15/09 (15:11 a ~17:50) as instâncias estavam de pé mas
não foram lidas; esse errorlog nunca entrará na HIST.

**Proposta.**
1. No início de `collect_all`, uma leitura por ambiente (identidade do mestre do recolhedor, fail-open):
   `SELECT Instance, Read_Until_Server_TS FROM dbo.WDB_ERRORLOG_READ_STATE WHERE Environment = ?`.
2. Em `collect_from_server`, depois do `SELECT GETDATE()` do servidor:
   `normal = ate - 65 min`; se `marca` existir e `marca - 5 min < normal`, então `desde = max(ate - 24 h, marca - 5 min)`.
   Mesma instância, mesmo relógio (a marca foi gravada com o `ate` do próprio servidor).
3. **Volume controlado:** das linhas com `Log_Date < normal`, só entram na STG os tipos que o arquivo guarda
   (Lifecycle, AvailabilityGroup, Critical, Error). Security e Repetitive antigos não vão para a STG (a STG é a janela
   recente dos cartões); entram só nos agregados do B2b-2. Sem isto, um incidente de frota de 24 h traria ~240 mil
   linhas num ciclo (hoje 11 mil em 19 a 29 s de inserção).
4. **Arquivo:** o recolhedor passa a chamar `usp_archive_errorlog_events @days_to_archive = 2` (a procedure já aceita o
   parâmetro; a STG só tem o ciclo actual, o custo não muda). Resolve a borda dos 24 h apontada pelo guardião.
5. Log: `"{instancia}: recuperacao de janela desde {desde} ({minutos} min)"` e contagem por ciclo.
6. O log anterior (1) continua a ser lido quando o cabeçalho de arranque aparece na janela, agora alargada.

**Riscos.** Leitura de 24 h numa instância com log enorme (SQLHDSPRD214, 6,4 M linhas): o `xp_readerrorlog` já percorre
o ficheiro com filtro de data em cada ciclo; muda o número de linhas devolvidas, não a leitura. Timeout de 60 s mantém-se.
Cartão de errorlog: eventos Critical/Error recuperados aparecem no ciclo da recuperação (são reais e não tinham sido
vistos) e saem no ciclo seguinte.

## B2b-2 — agregados horários (migration 015)

**Problema.** Security e Repetitive só existem na STG (65 min). A política decidida a 15/09 prevê agregados horários
sem texto pessoal, 13 meses, para comparação ano a ano. `aggregate_hourly` existe no classificador e não é usada.

**Tabela** (nome a confirmar pelo guardião; o prefixo `KPI_MSSQL_*_HIST` já é usado por tabelas sem BLUE/GREEN):
`dbo.KPI_MSSQL_ERRORLOG_AGG_HIST` em FG_KPI_HIST.

| Coluna | Tipo | Nota |
|---|---|---|
| Instance | VARCHAR(128) | |
| Hour_TS | DATETIME2(0) | hora do servidor, truncada |
| Log_Type | VARCHAR(32) | Security, Repetitive, AvailabilityGroup, Critical (acções aggregate) |
| Category | VARCHAR(64) | do classificador |
| Error_Number | INT NOT NULL | 0 quando não há |
| State | INT NOT NULL | motivo do login em Security; -1 nos outros |
| Severity | INT NULL | |
| Occurrences | INT NOT NULL | |
| First_Log_Date / Last_Log_Date | DATETIME2 | |
| Sample_Text | NVARCHAR(400) NULL | **NULL em Security** (login e IP); nos outros, a primeira linha cortada |
| Updated_At | DATETIME2 | |

PK (Instance, Hour_TS, Log_Type, Category, Error_Number, State).

**Escrita.** `collect_from_server` calcula `aggregate_hourly` sobre tudo o que leu (janela normal ou recuperada) e o
recolhedor envia num JSON por ciclo a `dbo.usp_errorlog_agg_merge @environment, @json` (MERGE HOLDLOCK), fora do applock
do store e com try próprio, como o estado do B2a-2a. **Contagem:** as janelas sobrepõem-se (65 min lidos a cada 5 min),
por isso `Occurrences = MAX(existente, nova)`, `First = MIN`, `Last = MAX`. Com ciclos a horas cada hora fica inteira
em pelo menos uma leitura. Limite declarado: numa hora partida por uma falha (leitura A até 10:40, recuperação desde
10:35) a contagem é um mínimo garantido, não o total.

**Retenção.** Nova camada em `WDB_RETENTION_POLICY`: (`KPI_MSSQL_ERRORLOG_AGG_HIST`, `AGREGADOS`, 395 dias, mín. 365,
máx. 1095). Procedure `dbo.usp_purge_errorlog_agg @dry_run, @batch_size, @max_minutes` (corte por Hour_TS, legal hold por
instância, registo em WDB_MAINTENANCE_LOG), chamada no fim de `usp_purge_kpi_history` a seguir a `usp_purge_errorlog_hist`
(IF OBJECT_ID, sem TRY/CATCH, como no B2b-1).

**Canónico.** Secção 39 (tabela, merge, seed, purge) e a chamada nova no fim da `usp_purge_kpi_history`.

## Perguntas ao guardião

1. B2a-2b sem migration e com `@days_to_archive = 2`: de acordo? O filtro "só eventos na parte recuperada" é suficiente
   para o volume, ou limitar também o número de instâncias em recuperação por ciclo?
2. Nome e filegroup da tabela de agregados. PK com Error_Number 0 e State -1 em vez de NULL?
3. MAX por hora é aceitável como semântica, com o limite declarado?
4. Os agregados no mesmo JSON/ligação do estado de leitura ou numa chamada separada?
5. Purge dos agregados numa procedure própria chamada pela genérica, ou uma camada nova dentro de `usp_purge_errorlog_hist`?
