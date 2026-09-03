# WatcherDB V3.3 Standard — Security Hardening

## SQL Server least privilege (recomendado)

WatcherDB V3.3 Standard monitoriza SQL Server via Windows Auth ou SQL
Auth. Para aderir ao principio "least privilege", **criar um login
dedicado `WatcherDBReader`** em vez de usar `sysadmin`.

Script T-SQL pronto: [`LEAST_PRIVILEGE_SETUP.sql`](LEAST_PRIVILEGE_SETUP.sql)

## Passos

1. Editar o script:
   - Escolher **Opcao A (SQL Auth)** ou **Opcao B (Windows Auth)** —
     descomentar o bloco correspondente (linhas 50-80 do script).
   - Se SQL Auth: definir `<PASSWORD_AQUI>` com password seguro.
   - Se Windows Auth: definir `<DOMAIN>` com dominio AD do cliente.
   - **Descomentar** apenas `[TIER: STANDARD]` (V3.3 e Standard).
   - **Comentar** os blocos `[TIER: PRO]` e
     `[TIER: INTELLIGENCE_COLLECTOR]` — nao aplicam a V3.3 Standard.

2. Executar como `sysadmin` na instancia a monitorizar:
   ```powershell
   sqlcmd -S <host>\<instance> -E -i docs\security\LEAST_PRIVILEGE_SETUP.sql
   ```
   Repetir por cada instancia SQL Server que V3.3 monitoriza.

3. Configurar o WatcherDB V3.3 a usar o login criado.

   Em `services/web_service/config.yaml` ou via env vars:
   ```yaml
   database:
     # SQL Auth:
     user: "WatcherDBReader"
     password_env: "SQL_PASSWORD"
     trusted_connection: false

     # OR Windows Auth (service corre como <DOMAIN>\WatcherDBReader):
     trusted_connection: true
   ```

4. Verificar no startup:
   ```
   grep "SecurityCheck" services/web_service/logs/service.log
   ```
   Ausencia de WARN = configuracao OK.

## Permissoes concedidas no tier STANDARD

- `VIEW SERVER STATE` — runtime DMVs (CPU, memory, waits, sessions)
- `VIEW ANY DEFINITION` — schema metadata
- `VIEW ANY DATABASE` — database enumeration
- `msdb` SELECT em `backup*`, `sysjobs*`, `sysoperators`
- EXECUTE em `msdb.dbo.sp_help_jobactivity`

**NAO concede:** `sysadmin`, `db_owner`, `CONTROL`, `ALTER`, `INSERT`,
`UPDATE`, `DELETE` em qualquer BD.

## Notas

- V3.3 Standard **nao precisa** de `SHOWPLAN` nem `VIEW SERVER SECURITY
  STATE` (esses sao tier PRO — Performance Module e TDE Dashboard sao
  features V5.x / V5.5 Pro Enhanced).
- Se o cliente eventualmente upgrade para Pro (V5.5), correr a seccao
  `[TIER: PRO]` ADITIVAMENTE (nao remover o que ja foi feito em
  STANDARD).

## Rollback

O fim do script tem um bloco `ROLLBACK (cleanup)` comentado. Descomentar
e correr como `sysadmin` para remover login e users.

## Referencia

- Script fonte-de-verdade mantido em WATCHERDB_V5.5/docs/security/
  (mesma versao).
- Documentacao V5.5: ver `DEPLOYMENT_V55.md` seccao 4.5.
