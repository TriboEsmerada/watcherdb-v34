# B2a-2 — marca de água por instância no recolhedor do errorlog (desenho, 15/09)

> Rascunho para o gate do guardião do recolhedor (watcherdb-v1-intel-specialist, com veto). Nada aplicado.
> Plano: PLANO_EXECUCAO_ALERTAS_ERRORLOG_2026-09-14.md, B2.

## Problema medido (sql_monitoring, só leitura, 15/09)

1. **Não se distingue calma de cegueira.** 63 instâncias no inventário; 40 com linhas na HIST em 7 dias, 29 na STG
   agora. `collect_from_server` devolve `[]` tanto para "li e não havia linhas" como para "não consegui ligar"
   (`scripts/collectors/collect_errorlog.py`, except final). O heartbeat em `WDB_COLLECTION_SCHEDULE_META` é global:
   um ambiente saudável esconde outro cego. O B3 só consegue dizer "última linha recebida", que numa instância calma
   é antiga mesmo com leituras boas.
2. **Perdem-se linhas quando a falha é do recolhedor.** Janela fixa de 65 min. Hoje, 15:11 a 16:50+, a resolução
   de nomes na máquina do recolhedor levou 700 a 750 s por nome PRD: todos os recolhedores falharam em muitas
   instâncias durante mais de 1,5 h. Essas instâncias estavam de pé; o errorlog desse período nunca será lido.
   Quedas de SQL não são o caso: 122 eventos offline em 7 dias, o mais longo com 9 min.
3. **Achado lateral:** `run()` não chama `store_data` com df vazio, portanto um ciclo sem linhas não escreve o
   heartbeat (o comentário de `_heartbeat` diz o contrário).

## Proposta

### B2a-2a — estado por instância (observabilidade, sem mudar a leitura)

Tabela `dbo.KPI_MSSQL_ERRORLOG_READ_STATE` (estado, uma linha por instância, sem BLUE/GREEN, FG_KPI_DATA):

| Coluna | Tipo | Nota |
|---|---|---|
| Instance | VARCHAR(128) PK | canónico com underscore |
| Environment | VARCHAR(8) NOT NULL | PRD, QA, TST |
| Last_Attempt_TS | DATETIME2 NOT NULL | relógio do recolhedor |
| Last_Success_TS | DATETIME2 NULL | idem |
| Read_Until_Server_TS | DATETIME2 NULL | `ate` da última leitura boa, relógio do servidor (a marca de água) |
| Rows_Read | INT NULL | linhas não descartadas da última leitura boa |
| Logs_Read | TINYINT NULL | 1 ou 2 (log anterior lido por rotação) |
| Consecutive_Failures | INT NOT NULL DEFAULT 0 | zera numa leitura boa |
| First_Failure_TS / Last_Failure_TS | DATETIME2 NULL | início e fim da série de falhas |
| Last_Failure_Class | VARCHAR(32) NULL | connect_timeout, login_failed, permission, query_timeout, other |
| Last_Failure_Text | NVARCHAR(400) NULL | mensagem do driver, sem connection string |
| Updated_At | DATETIME2 NOT NULL | |

Procedure `dbo.usp_errorlog_read_state_upsert @environment VARCHAR(8), @json NVARCHAR(MAX)`: um MERGE por ciclo a
partir de OPENJSON (compat 160 medido), transacção curta. Chamada em **todo** o ciclo, com ou sem linhas, antes do
TRUNCATE/swap e fora do applock do store (ou dentro? pergunta ao guardião). Falhar o upsert não falha o KPI.

Recolhedor: `collect_from_server` passa a devolver `(linhas, estado)`; `collect_all` junta os estados; `run()`
chama o upsert e o heartbeat mesmo com df vazio (corrige o achado 3).

Consumidores: o endpoint do B3 mostra "última leitura bem-sucedida desta instância" e, em falha, "o recolhedor não
consegue ler esta instância desde HH:MM (connect_timeout, N ciclos)". Cartão de frescura por instância: fase própria.

### B2a-2b — recuperar a janela perdida (muda a leitura)

`desde = max(ate - 24 h, min(ate - 65 min, Read_Until_Server_TS - 5 min))`, lido do estado no início do ciclo (um
SELECT por ambiente). Só a primeira leitura depois de uma falha alarga a janela; tecto de 24 h para caber no
`@days_to_archive = 1` do arquivo B2a-1. O cabeçalho de rotação continua a decidir a leitura do log 1.

Riscos: volume do primeiro ciclo depois de um incidente de frota (todas as instâncias com janela larga em
simultâneo; SQLHDSPRD214 tem 6,4 M linhas no log); duração do ciclo de PRD (hoje 20 a 30 s de inserção); STG com
linhas mais velhas que 65 min só nesse ciclo (os cartões contam por Update_TS 24 h, sem efeito).

## Base partilhada e processo

Migration 014, secção nova no canónico, baseline actualizada, testes com o harness do B2a-1, prompt V6. O owner
corre a migration com a conta de deploy. Identidade de escrita do recolhedor: sql_monitoring (hoje db_owner, achado
já registado); a procedure permite no futuro só GRANT EXECUTE.

## Perguntas ao guardião

1. Estado numa tabela nova sem BLUE/GREEN, ou há padrão existente (Wave C/D) que deva ser reutilizado?
2. Upsert dentro ou fora do applock `COLLECTOR_KPI_MSSQL_ERRORLOG_STG_{env}`? Antes ou depois do swap?
3. Separar B2a-2a e B2a-2b em lotes? Tecto de 24 h e sobreposição de 5 min adequados?
4. Classificação de falhas: a partir do SQLSTATE e do texto do pyodbc (08001 connect, 28000 login, 42000 permissão,
   HYT00 timeout)?
5. Corrigir já o heartbeat de ciclo vazio neste lote?
