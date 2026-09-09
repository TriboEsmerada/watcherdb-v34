# Council A: rotação da credencial sql_monitoring sem downtime

Data: 2026-09-04. Autor: orquestrador + correções do QA externo (login paralelo,
DISABLE em vez de DROP, audit de logins, GC no GitHub, pré-flight de permissões).
Estado: DESENHO PARA LEITURA. Nada aqui foi executado. Todos os blocos são para
o owner correr manualmente. Identidade nos blocos SQL: a tua sessão de DBA
(sysadmin) para CREATE LOGIN / GRANT; sql_monitoring2 (SQL auth) para o pré-flight.

## 0. O que foi exposto, e o que isso vale

O repo público continha `config/_archive/servers_27072026.json` com um campo
`enc` para a conta sql_monitoring. Esse campo é ciphertext Fernet; a chave mestra
vive em `WATCHERDB_ENCRYPTION_KEY_DPAPI` no `.env` (fora do repo) ou no
`master.key.dpapi`. Se a chave nunca esteve no histórico, o que circulou foi
ciphertext e 101 hostnames, não a password.

Verificação que só tu podes fazer (o hook bloqueou-me a leitura do histórico do .env):

```powershell
# Alguma vez um .env, .key ou .dpapi entrou no historico?
git log --all --diff-filter=A --name-only --format="" -- '.env' '*.env' '*.key' '*.dpapi' | Sort-Object -Unique
# Alguma vez a chave Fernet apareceu em texto?
git log --all -p -S 'WATCHERDB_ENCRYPTION_KEY' --format='%h %ad' | Select-String 'WATCHERDB_ENCRYPTION_KEY' | Select-Object -First 5
```

Decisão: rodar na mesma. Custo baixo com login paralelo, e um cliente bancário
vai perguntar "rodaram?" e não "estava cifrado?".

## 1. Inventário de consumidores da credencial (antes de tocar em nada)

Tudo o que liga como sql_monitoring fica cego se a password mudar sem aviso.
Lista a confirmar por ti:

| Consumidor | Onde lê a credencial | Notas |
|---|---|---|
| WatcherDB V33 (8433) | `.env` INTELLIGENCE_SQL_USER/PASSWORD + `config/servers.json` por instância (campo password cifrado) | 63 entradas com use_windows_auth=False |
| WatcherDB V34 (8434) | idem, cópia própria | restart separado |
| Collector V1 `WatcherDBCollector` | config própria do pacote watcherdb_intelligence | infra partilhada, v1-intel tem veto |
| V5 / V5.5 / V6 / AI Exp (8450, 8555, 8660, 8452) | .env de cada um | só se correm nesta máquina |
| SSIS Manager | ? | confirmar |
| Scripts teus / SCOM / outros | ? | confirmar |

Se um consumidor não estiver nesta lista quando desativares o login antigo, é ele
que vai aparecer como N/D no dashboard no dia seguinte.

## 2. Audit de logins: alguém usou a conta a partir de outro host?

Limitação honesta: por omissão o SQL Server só regista logins falhados. Logins
bem sucedidos só aparecem se `Login auditing = Both` ou houver Server Audit.
Corre nas 63 instâncias (com a tua sessão de DBA, só leitura):

```sql
-- 2a. Sessoes vivas agora com a conta, e de onde
SELECT @@SERVERNAME AS instance, s.host_name, s.program_name, s.login_time, s.client_interface_name
FROM sys.dm_exec_sessions s
WHERE s.login_name = 'sql_monitoring';

-- 2b. Nivel de auditoria desta instancia (0=none,1=success,2=failure,3=both)
EXEC xp_instance_regread N'HKEY_LOCAL_MACHINE', N'Software\Microsoft\MSSQLServer\MSSQLServer', N'AuditLevel';

-- 2c. Se AuditLevel in (1,3): logins bem sucedidos da conta nos ultimos 7 dias, por host
DECLARE @t TABLE (LogDate datetime, ProcessInfo nvarchar(50), [Text] nvarchar(max));
INSERT @t EXEC sys.xp_readerrorlog 0, 1, N'Login succeeded', N'sql_monitoring';
INSERT @t EXEC sys.xp_readerrorlog 1, 1, N'Login succeeded', N'sql_monitoring';
SELECT LogDate, [Text] FROM @t WHERE LogDate >= DATEADD(DAY,-7,GETDATE()) ORDER BY LogDate DESC;
```

Critério: qualquer `host_name` ou `[CLIENT: ip]` que não seja o host do WatcherDB
é incidente e muda a urgência de "rodar esta semana" para "rodar hoje e abrir
post-mortem". Se AuditLevel = 2 na maioria das instâncias, regista como achado
próprio: não há como responder à pergunta do banco com evidência.

## 3. Login paralelo: sql_monitoring2 nas 63 instâncias

Base: `docs/security/LEAST_PRIVILEGE_SETUP.sql` (nome de exemplo WatcherDBReader;
substituir por sql_monitoring2). Resumo do que o script concede, para conferires
que é o mesmo conjunto que sql_monitoring tem hoje:

- server: VIEW SERVER STATE, VIEW ANY DEFINITION, VIEW ANY DATABASE, SHOWPLAN,
  VIEW SERVER SECURITY STATE (2022+)
- msdb: SELECT em backupset/backupmediafamily/backupmediaset/backupfile,
  sysjobs*/sysschedules/sysoperators/syscategories, EXECUTE sp_help_jobactivity,
  role SQLAgentReaderRole
- master: EXECUTE sys.xp_readerrorlog

Antes de criar, compara com o que a conta actual tem de facto (pode ter recebido
grants ad hoc que o script canónico não conhece):

```sql
-- 3a. Permissoes server-scope e roles da conta actual
SELECT 'server_perm' AS kind, sp.permission_name, sp.state_desc
FROM sys.server_permissions sp JOIN sys.server_principals p ON p.principal_id = sp.grantee_principal_id
WHERE p.name = 'sql_monitoring'
UNION ALL
SELECT 'server_role', r.name, 'MEMBER'
FROM sys.server_role_members m JOIN sys.server_principals r ON r.principal_id = m.role_principal_id
JOIN sys.server_principals p ON p.principal_id = m.member_principal_id
WHERE p.name = 'sql_monitoring';

-- 3b. Por base (correr em master, msdb e em cada user DB onde exista o user)
EXEC sp_MSforeachdb N'USE [?];
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = ''sql_monitoring'')
SELECT DB_NAME() AS db, dp.class_desc, OBJECT_SCHEMA_NAME(dp.major_id) + ''.'' + OBJECT_NAME(dp.major_id) AS obj,
       dp.permission_name, dp.state_desc
FROM sys.database_permissions dp JOIN sys.database_principals u ON u.principal_id = dp.grantee_principal_id
WHERE u.name = ''sql_monitoring''
UNION ALL
SELECT DB_NAME(), ''role'', r.name, ''MEMBER'', NULL
FROM sys.database_role_members rm JOIN sys.database_principals r ON r.principal_id = rm.role_principal_id
JOIN sys.database_principals u ON u.principal_id = rm.member_principal_id WHERE u.name = ''sql_monitoring'';';
```

Se 3a/3b mostrarem sysadmin ou db_owner em alguma instância, isso é dívida
antiga: sql_monitoring2 NÃO herda isso. O pré-flight da secção 4 diz se algum
collector dependia dela.

Criação (uma password forte gerada por ti, nunca escrita em chat nem em ficheiro do repo):

```sql
-- 3c. Em cada instancia, sessao DBA, BD actual = master
CREATE LOGIN [sql_monitoring2] WITH PASSWORD = N'<gerada>', CHECK_POLICY = ON, CHECK_EXPIRATION = OFF, DEFAULT_DATABASE = master;
-- depois: LEAST_PRIVILEGE_SETUP.sql com WatcherDBReader -> sql_monitoring2
```

Nota do teste de 2026-08-21 (está no próprio script): os GRANT server-scope só
pegam com a BD actual = master.

Instância especial: SQLHDSTST505\I01 aloja a WatcherDB_Intelligence. Aí o novo
login precisa também do que sql_monitoring tem nessa BD (db_datareader + EXECUTE
em usp_swap_kpi_stg_tables, a confirmar com 3b). Esta parte toca infra partilhada:
pedir parecer ao v1-intel antes.

## 4. Pré-flight de permissões, como sql_monitoring2

Objectivo: provar que cada query dos collectors corre com o login novo antes de
apontar o WatcherDB para ele. Sem isto, trocamos uma violação de regra por N/D
espalhados e a semana 2 persegue fantasmas.

Ferramentas existentes que cobrem parte:
- `deploy/preflight_target.ps1` fase 5: login existe + VIEW SERVER STATE. Só isso.
- `scripts/verificar_coletas_kpi.sql`: frescura das STG depois da coleta. Serve
  como critério de saída (secção 5), não como pré-flight.

O que falta e proponho construir no dia 2 (Lote Council B), read-only:
`scripts/qa/preflight_permissions.py`

- Identidade: sql_monitoring2, SQL auth, connection string explícita. Sem
  Trusted_Connection.
- Fonte das queries: o catálogo de queries do collector V1 (pacote
  watcherdb_intelligence) e as queries live dos routers (space, alwayson,
  service logs via xp_readerrorlog, tlog-diagnosis). Cada uma corre com
  `SET NOCOUNT ON; SET LOCK_TIMEOUT 5000;` e timeout de 15 s.
- Saída: tabela instância x query com OK / erro 229 (permissão) / erro 297
  (VIEW SERVER STATE) / timeout / outro. Ficheiro CSV em docs/context/.
- Critério: 0 erros de permissão nas 63. Qualquer 229/297 é um GRANT em falta
  no script canónico, a corrigir no script e não à mão.

## 5. Troca de identidade, um serviço de cada vez

1. `config/servers.json`: username sql_monitoring2 nas 63 entradas e password
   cifrada com a chave mestra desta máquina. Há helper para isso:
   `services.secrets.encrypt_value(plaintext)`. Bloco a preparar no dia 2 como
   script que lê a password de uma variável de ambiente temporária, nunca de
   argumento de linha de comandos (fica no histórico do PowerShell).
2. `.env`: INTELLIGENCE_SQL_USER=sql_monitoring2 e INTELLIGENCE_SQL_PASSWORD cifrada.
3. Restart do V34 (8434) primeiro. Validar um ciclo completo:
   `scripts/verificar_coletas_kpi.sql` com Min_Atras abaixo do intervalo em todas
   as STG, dashboard sem N/D novos face à captura de antes.
4. Collector V1 `WatcherDBCollector`: mesma troca na config dele, restart,
   validar `usp_swap_kpi_stg_tables` a correr (v1-intel).
5. Só depois o V33 (8433).

## 6. Desativar o login antigo, com rollback de 5 segundos

```sql
-- 6a. Em cada instancia, DEPOIS de 24h sem sessoes do login antigo (repetir 2a)
ALTER LOGIN [sql_monitoring] DISABLE;
-- rollback imediato se algo ficar cego:
-- ALTER LOGIN [sql_monitoring] ENABLE;
```

DROP só passados 30 dias, e só se 2a continuar vazio. Um login desativado que
alguém tenta usar aparece no error log como "Login failed ... account is
disabled", o que é precisamente o sinal que queremos para apanhar consumidores
esquecidos.

## 7. GitHub: purga e o que ela não faz

- Repo para privado primeiro (Settings > Danger Zone). Um minuto, sem risco.
- `git filter-repo` limpa o teu clone e o remote, mas commits antigos continuam
  alcançáveis por SHA e em forks até a GitHub Support fazer garbage collection.
  Abrir ticket em https://support.github.com com a lista de SHAs
  (o histórico dos 3 ficheiros: `git log --all --oneline -- config/_archive/servers_27072026.json config/sql_servers_new.json REGISTRO_IGAC`).
- Verificar forks: página do repo > Insights > Forks. Cada fork é uma cópia
  que a purga não toca.

## 8. Critério de saída do Council A

Não é `git log -S`. É:

1. sql_monitoring2 activo nas 63 instâncias, pré-flight com 0 erros de permissão.
2. V34, V1 collector e V33 a coletar com o login novo, um ciclo completo validado.
3. `ALTER LOGIN sql_monitoring DISABLE` nas 63, com 2a vazio nas 24h anteriores.
4. Repo privado, filter-repo feito, ticket GitHub aberto com os SHAs.
5. Resultado do audit (secção 2) registado no CONTEXT, incluindo "sem evidência
   possível" onde AuditLevel = 2.

## Ordem no calendário

Dia 1 tarde: secções 0, 1, 2 e 7 (repo privado + ticket). Só leitura e uma
mudança de visibilidade.
Dia 2: secções 3 e 4 (criar login, construir e correr o pré-flight).
Dia 3 ou quando o pré-flight estiver limpo: secções 5 e 6.
O Lote Council B (remover use_windows_auth=True nos 5 sítios) só entra depois do
pré-flight, porque é ele que diz se sql_monitoring consegue substituir a conta de
serviço em xp_readerrorlog e nas DMVs de AG.
