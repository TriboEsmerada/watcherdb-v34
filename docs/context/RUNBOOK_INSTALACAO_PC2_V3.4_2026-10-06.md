# Runbook - Instalacao do WatcherDB V3.4 Standard num servidor alvo (teste no PC2)

Data: 2026-10-06, revisto 2026-10-07. Direccao do owner: o utilizador preenche servidor e base; a base
(SQL Server) tem de existir antes; nome por omissao WatcherDB, configuravel; caminhos no servidor alvo sao
os padrao do produto, nunca os da maquina do vendor.

Duas partes, dois sitios, duas identidades:

| Parte | Onde corre | Quem | Caminhos |
|---|---|---|---|
| A. Vendor: build + licenca | maquina do vendor (hoje PC1, repo WATCHERDB_V3.4) | owner | os do repo do vendor; o cliente nunca ve esta parte |
| B. Cliente: instalar e provar | servidor alvo (PC2 ou servidor do cliente) | DBA/admin do cliente | so' caminhos padrao: `%ProgramFiles%\WatcherDB\V3.4`, `%ProgramData%\WatcherDB\V3.4`, pasta do pacote |

Preencher antes de comecar (Parte B):

| Campo | Valor | Nota |
|---|---|---|
| `<SQLSERVER>` | ______________ | servidor\instancia SQL Server que aloja a base do WatcherDB (ex.: `SRV01\I01`) |
| `<BASE>` | `WatcherDB` | nome da base; por omissao `WatcherDB`, pode ser outro (ver "Limites actuais") |
| `<LOGIN>` | `watcherdb` | login SQL do produto, SO' DE LEITURA nas instancias do cliente; por omissao `watcherdb`, pode ser outro (ver "Limites actuais") |
| `<DBA>` | ______________ | identidade DBA que cria a base, o login e corre o schema (DDL); nunca a do servico |
| `<SVC_ACCOUNT>` | `DOMINIO\usuario` | conta do servico Windows (nao UPN); so' le ficheiros locais |
| `<PACOTE>` | `C:\Temp\WatcherDB_Install` | pasta onde o pacote ZIP e' copiado e extraido no servidor alvo |
| `<HOST>` | ______________ | hostname do servidor alvo (entra na licenca) |

Base: gate de release docs/context/releases/2026-10-06_3.4.0.0.md e parecer do watcherdb-deploy-architect.
Acesso do produto a' base: so' pelo login `sql_monitoring` (Regra de Ouro #2). Os guias existentes
(deploy/INSTALL_TEST.md, deploy/INSTALL_FLOW_V0.2.md, docs/external/standard/INSTALL_GUIDE.md) sao do V3.3.

---

## Limites actuais (lotes a fechar antes de uma instalacao em cliente)

| Lote | Facto medido | Efeito ate' ser fechado |
|---|---|---|
| NONCE_TEST_FALSO_POSITIVO (pronto) | teste vermelho fora da baseline do build | PASSO 1 do build aborta |
| WATCHERDB_DATA_DIR | o servico empacotado le `C:\ProgramData\WatcherDB` fixo (watcherdb/core/paths.py:20) e o install.ps1 provisiona em `...\WatcherDB\V3.4` (release_vars.psd1:51; install.ps1:226); a variavel nunca chega ao servico | contorno: variavel de maquina (B.3.3) |
| BASE_E_LOGIN_CONFIGURAVEIS | BASE: install.ps1 nao pede a base (:162-180); runtime le INTELLIGENCE_DATABASE do .env com omissao `WatcherDB_Intelligence` (helpers.py:142, overview_dashboard.py:38, intelligence_kpis.py:278) + 30 literais em 16 ficheiros; setup_database.ps1 aceita -Database (:11) mas o canonico tem `USE [WatcherDB_Intelligence]` fixo (:186,:214,:3680,:5600,:5659; 73 ocorrencias). LOGIN: runtime ja' configuravel por INTELLIGENCE_SQL_USER com omissao `sql_monitoring` (helpers.py:149, overview_dashboard.py:43, intelligence_kpis.py:286, settings.py:52, db_identity.py:111); frota por servidor no servers.json (farm_inventory_parser --master-username, omissao sql_monitoring :385); install.ps1 nao pede o login e o preflight valida "sql_monitoring" por nome (:90-93); docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql tem `[sql_monitoring]` fixo 29x e LEAST_PRIVILEGE_SETUP.sql usa um 3.o nome, `WatcherDBReader` (:79-257) | `<BASE>` tem de ser `WatcherDB_Intelligence`; `<LOGIN>` diferente de `sql_monitoring` exige editar os scripts de grants a' mao e o preflight falha o check do login |
| PACOTE_FERRAMENTAS_INSTALACAO | o stage do build leva so' install.ps1, uninstall.ps1, preflight_target.ps1, release_vars.psd1 (build_release.ps1:644-654); os .sql vao dentro do bundle (build.py COPY_DIRS) mas `setup_database.ps1`, `tools/bootstrap_admin.py` e `deploy/farm_inventory_parser.py` NAO viajam (deploy nao esta' em PROTECT_DIRS nem no stage); bootstrap_admin fica obfuscado dentro do bundle, sem CLI; o servidor alvo nao tem Python | o cliente nao consegue criar o schema, o primeiro admin nem converter o inventario a partir do pacote; no teste do PC2 corre-se a partir do repo |
| INVENTARIO_XLSX_E_ROLLOUT | farm_inventory_parser aceita so' .csv/.json (:401-413) e escreve so' servers.json (:363); nao gera sql_auth_rollout.json nem o script de grants; --master-username com omissao sql_monitoring (:385) | o cliente nao pode entregar .xlsx; o rollout e os grants fazem-se a' mao |

---

# PARTE A - Vendor (maquina de build, owner)

## A.0 Pre-requisitos
```powershell
cd <raiz do repo WATCHERDB_V3.4>        # na maquina do vendor
git status            # so' .nestor/session.log pode estar modificado
git log -1 --oneline  # o sha vai para GET /api/version
```
Lotes antes do build: NONCE_TEST_FALSO_POSITIVO_2026-10-06_apply.py; WATCHERDB_DATA_DIR; se `<BASE>` for
diferente de `WatcherDB_Intelligence`, NOME_DA_BASE_CONFIGURAVEL; para cliente, PACOTE_SETUP_DATABASE.
Ferramentas na .venv-build (hoje so' tem o runtime):
```powershell
.venv-build\Scripts\python.exe -m pip install -r requirements-build.txt
.venv-build\Scripts\python.exe -m pip check
.venv-build\Scripts\python.exe -m pyarmor.cli --version    # esperar pyarmor-pro e 011618
.venv-build\Scripts\python.exe -m PyInstaller --version
where syft; where grype
Test-Path deploy\keys\ed25519_public.pem                    # True (gitignored: so' existe na arvore do vendor)
```

## A.1 Build ZIP
```powershell
pwsh -File deploy\build_release.ps1 -Target zip -SkipSigning
```
- -SkipSigning so' para teste interno (signtool fora do PATH); entrega a cliente exige assinatura.
- Nao usar -SkipTests nem -SkipCve. 10-20 min. Exit 2 gate, 4 build/smoke, 6 staging/SBOM.
- Saida: `dist\release\3.4.0.0\` (zip com nome ainda `WatcherDB_V3.3_3.4.0.0.zip`, SHA256SUMS.txt, sbom, grype).
Validar: `dist\watcherdb\VERSION.txt` = 3.4.0.0 / WatcherDBWebServiceV34 / 8434 / Git <sha>; SBOM sem `anthropic`.
Smoke em pasta limpa, porta 8499, com WATCHERDB_DATA_DIR temporario (ver versao anterior deste runbook ou
docs/context/auditorias/AUDITORIA_EMPACOTAMENTO_2026-07-04_RUNBOOK_ETAPA2.md:115-122).

## A.2 Licenca TRIAL de 30 dias
Entrada: fingerprint do servidor alvo (recolhido em B.0). Chave privada em
`%USERPROFILE%\.watcherdb-council-secrets` do vendor, NUNCA sai da maquina do vendor nem vai no pacote.
```powershell
$cid = [guid]::NewGuid().ToString(); $lid = [guid]::NewGuid().ToString()
py deploy\license_cli.py issue --customer-id $cid --customer-name "TRIAL <HOST>" --edition standard `
  --bios-uuid <UUID> --cpu-id <ProcessorId> --hostname <HOST> `
  --expires <hoje+30, AAAA-MM-DD> --license-id $lid --out <pasta de saida>\license_trial_<HOST>.dat
"license_id (guardar para revogar): $lid"
```
Expira a' meia-noite UTC da data; a partir dai o servico deixa de ARRANCAR (fail-close no restart); uma
instancia a correr nao morre sozinha; aviso Event Log 1002 a <= 30 d. Sem serial legivel (identificador =
license_id). Revogar: `py deploy\license_cli.py revoke --license-id $lid`.

Entregar ao cliente: o ZIP, o SHA256SUMS.txt, o license_trial_<HOST>.dat e, ate' ao lote PACOTE_SETUP_DATABASE,
tambem `deploy\setup_database.ps1` e `database\INSTALACAO_COMPLETA_UNIFICADA.sql` (ja' dentro do bundle).

---

# PARTE B - Servidor alvo (cliente / PC2)

## B.0 Antes de instalar (DBA do cliente)
1. SQL Server instalado e acessivel do servidor alvo (2016+ recomendado; 2014 sem Query Store). Porta TCP
   aberta ate' `<SQLSERVER>`; nome resolvivel (nome curto se o FQDN nao resolver).
2. Base `<BASE>` criada e vazia pelo `<DBA>` (RECOVERY SIMPLE recomendado):
   ```sql
   -- identidade: <DBA>; onde: <SQLSERVER>; impacto: cria uma base vazia; rollback: DROP DATABASE [<BASE>]
   IF DB_ID(N'<BASE>') IS NULL CREATE DATABASE [<BASE>];
   ALTER DATABASE [<BASE>] SET RECOVERY SIMPLE;
   ```
3. **O que e' o login `<LOGIN>`.** Serve exclusivamente para a RECOLHA de dados de monitorizacao nas
   instancias do cliente (estado do servidor, esperas, sessoes, backups, jobs, espaco) e NUNCA altera dados
   do cliente. Nas instancias monitorizadas as permissoes sao todas de leitura, e sao exactamente estas
   (docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql:33-70): VIEW SERVER STATE, VIEW ANY DEFINITION, leitura
   de msdb (backupset, sysjobs e tabelas irmas) e SQLAgentReaderRole, EXECUTE em xp_readerrorlog (ler o log de
   erros do SQL Server; opcional) e sp_help_jobactivity, SHOWPLAN (ver planos; opcional). Sem INSERT/UPDATE/
   DELETE, sem DDL, sem acesso as tabelas de negocio. Nota honesta: VIEW SERVER STATE deixa ver o texto das
   queries em execucao, que pode conter valores de negocio; o portal redige esse texto por perfil de
   utilizador. O unico sitio onde o produto ESCREVE e' a sua propria base `<BASE>`, onde guarda o que
   recolheu (ai o login tem EXECUTE em procedimentos, INSERT/UPDATE/DELETE e ALTER nas tabelas de staging do
   produto). O DBA pode auditar isto a qualquer momento: `sys.fn_my_permissions`, `sys.server_permissions` e
   `sys.database_permissions` para o principal `<LOGIN>`.
   Login (SQL auth, por omissao `watcherdb`) criado e permissionado pelo `<DBA>` em DOIS sitios:
   (a) em `<SQLSERVER>`, com leitura em `<BASE>`; (b) em TODAS as instancias que vao ser monitorizadas
   (a lista do inventario, B.3.4), com VIEW SERVER STATE + VIEW ANY DEFINITION + leitura de msdb
   (docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql por instancia; ate' ao lote, substituir o nome no script).
   Uma instancia sem o login aparece no portal como inalcancavel. O produto nunca usa Trusted_Connection.
   ```sql
   -- identidade: <DBA>; onde: <SQLSERVER> E cada instancia monitorizada; rollback: DROP LOGIN [<LOGIN>]
   IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'<LOGIN>')
       CREATE LOGIN [<LOGIN>] WITH PASSWORD = N'<senha forte>', CHECK_POLICY = ON;
   ```
   Com o lote LOGIN_FROTA_AUTOMATICO_OU_MANUAL (direccao do owner, 2026-10-07) este passo passa a ser feito
   DEPOIS do inventario (B.3.4), em B.3.5, a' escolha do cliente: o instalador cria e permissiona o login em
   todas as instancias registadas, ou gera o script para o DBA correr a' mao. Ate' ao lote: manual.
4. Conta do servico `<SVC_ACCOUNT>` com "Log on as a service". NetworkService nao serve se a instancia
   exigir Windows Auth (seria `<HOST>$`); com `<LOGIN>` a conta do servico nao toca a base.
5. Servidor alvo: Windows Server 2019+/Windows 10-11 x64, ODBC Driver 17 ou 18 for SQL Server, VC++ runtime,
   porta 8434 livre, PowerShell 5.1+.
6. Fingerprint para a licenca (PowerShell admin; enviar ao vendor):
   ```powershell
   (Get-CimInstance Win32_ComputerSystemProduct).UUID
   (Get-CimInstance Win32_Processor | Select-Object -First 1).ProcessorId
   $env:COMPUTERNAME
   ```

## B.1 Receber e conferir o pacote
```powershell
New-Item -ItemType Directory -Force <PACOTE> | Out-Null
# copiar para <PACOTE>: o ZIP, SHA256SUMS.txt, license_trial_<HOST>.dat
Get-FileHash -Algorithm SHA256 <PACOTE>\*.zip        # comparar com SHA256SUMS.txt
Expand-Archive <PACOTE>\*.zip <PACOTE>\x -Force
```

## B.2 Schema na base (so' se `<BASE>` esta' vazia)
Identidade `<DBA>` (Windows Auth, DDL). Impacto: cria tabelas/views/procs em `<BASE>`. Rollback: DROP DATABASE
[<BASE>] (base de teste). NUNCA apontar a uma base viva de outro ambiente.
```powershell
# ate' ao lote PACOTE_SETUP_DATABASE o script vem a' parte (entregue pelo vendor em <PACOTE>\setup\)
powershell -ExecutionPolicy Bypass -File <PACOTE>\setup\setup_database.ps1 -SqlServer <SQLSERVER> -Database <BASE> -ConfirmedDBAIdentity <DBA>
```
O Passo 3 do script cria o primeiro admin (interactivo; recusa se ja' houver admin). Depois: GRANTS de
`sql_monitoring` em `<BASE>` e nas instancias monitorizadas. A base fica sem dados ate' o colector correr.
Se `<BASE>` ja' tem schema e utilizadores (base existente), saltar B.2 por completo.

## B.3 Instalar
3.1 Preflight e instalacao, a partir de `<PACOTE>\x`:
```powershell
cd <PACOTE>\x
powershell -ExecutionPolicy Bypass -File preflight_target.ps1 -SqlServer <SQLSERVER>     # exit 0 ok, 2 avisos
$pwd = Read-Host -AsSecureString "password <SVC_ACCOUNT>"
$mk  = Read-Host -AsSecureString "Fernet master key desta instalacao (nova; guardar no cofre do cliente)"
powershell -ExecutionPolicy Bypass -File install.ps1 -SqlServer <SQLSERVER> -ServiceAccount "<SVC_ACCOUNT>" `
  -ServiceAccountPassword $pwd -MasterKey $mk -LicensePath <PACOTE>\license_trial_<HOST>.dat -RemoteSubnet <subnet dos DBAs>
```
Sem -InstallDir/-DataDir o instalador usa os padrao (install.ps1:225-226):
- programa: `%ProgramFiles%\WatcherDB\V3.4`
- dados, segredos, config e licenca: `%ProgramData%\WatcherDB\V3.4`
3.2 [ate' ao lote WATCHERDB_DATA_DIR] apontar o servico para a pasta de dados:
```powershell
[Environment]::SetEnvironmentVariable("WATCHERDB_DATA_DIR", (Join-Path $env:ProgramData "WatcherDB\V3.4"), "Machine")
```
3.3 `.env` em `%ProgramData%\WatcherDB\V3.4\.env` (o install.ps1 nao o cria):
```
WATCHERDB_PORT=8434
INTELLIGENCE_SERVER=<SQLSERVER>
INTELLIGENCE_DATABASE=<BASE>
INTELLIGENCE_SQL_USER=<LOGIN>
INTELLIGENCE_SQL_PASSWORD=<cifrada com a master key desta instalacao, prefixo encrypted: (services/secrets.py:80); enc: seria lido como texto claro>
INTELLIGENCE_USE_WINDOWS_AUTH=false
JWT_SECRET_KEY=<novo, 64 hex>
WATCHERDB_EDITION=standard
```
3.4 Inventario da frota (lista das instancias a monitorizar). O cliente preenche UM ficheiro, num de tres
formatos, e o instalador converte para o que o produto usa:
   - `.xlsx` (modelo entregue com o pacote: uma linha por instancia, colunas host, instance, port, auth_mode,
     username, description, environment, priority, enabled, has_alwayson, ag_name, ag_listener)  [lote]
   - `.csv` com as mesmas colunas  [existe hoje: deploy/farm_inventory_parser.py]
   - `.json` (array de objectos com as mesmas chaves; o instalador normaliza para o formato canonico)  [existe hoje]
   Saida em `%ProgramData%\WatcherDB\V3.4\config\`: `servers.json` (canonico, consumido pelo portal e pelo
   colector) e, com o lote, `sql_auth_rollout.json` (ids que entram por `<LOGIN>`) e o script de grants por
   instancia. Passwords NUNCA no ficheiro de inventario: o parser escreve `@ENCRYPT_AT_INSTALL@` e o
   instalador pede-as e cifra-as com a master key. Hoje:
   ```powershell
   # ate' ao lote PACOTE_FERRAMENTAS_INSTALACAO o parser vem a' parte e exige Python no servidor alvo
   python <PACOTE>\setup\farm_inventory_parser.py --input <PACOTE>\inventario.csv --output "%ProgramData%\WatcherDB\V3.4\config\servers.json" `
     --master-host <SQLSERVER host> --master-instance <instancia> --master-db <BASE> --master-username <LOGIN> --validate-tcp
   ```
   Sem o `sql_auth_rollout.json` a frota entra por Trusted_Connection com a conta do servico, o que viola a
   Regra de Ouro #2.
3.5 Provisionar `<LOGIN>` na frota (com as instancias ja' registadas em 3.4). Em qualquer dos modos o login
   recebe SO' permissoes de leitura para recolha de dados de monitorizacao; nao altera dados do cliente
   (ver B.0.3). O cliente escolhe o modo:
   - **Automatico** (lote LOGIN_FROTA_AUTOMATICO_OU_MANUAL): o instalador liga a cada instancia do inventario
     com a identidade DBA de quem o corre (sessao Windows, ou sysadmin SQL pedido na hora, nunca gravado),
     cria o login com password forte gerada, aplica os grants minimos (VIEW SERVER STATE, VIEW ANY DEFINITION,
     leitura de msdb; em `<SQLSERVER>` tambem leitura em `<BASE>`), grava a password cifrada com a master key
     no `.env`/`servers.json`, escreve o `sql_auth_rollout.json` e um relatorio por instancia (criado /
     ja' existia / falhou: motivo). Condicoes: `--dry-run` que so' mostra o que faria; mesmo SID em todas as
     instancias (`CREATE LOGIN ... WITH SID = 0x...`) para replicas de AG e failover; instancias
     inalcancaveis nao abortam o resto; script de rollback gerado (DROP LOGIN por instancia); registo no
     Event Log; a identidade DBA nunca fica em disco.
   - **Manual**: o instalador gera o MESMO script (um bloco por instancia, `<LOGIN>` ja' substituido, SID fixo,
     password a preencher pelo DBA) e o DBA corre-o; o cliente introduz depois a password no instalador, que a
     cifra. Em qualquer dos modos o preflight valida no fim: liga com `<LOGIN>` a cada instancia e confirma
     os grants (hoje o preflight so' valida um login fixo, install.ps1:90-93).
   Ate' ao lote: modo manual com docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql, nome substituido.
3.6 Arrancar:
```powershell
Start-Service WatcherDBWebServiceV34; Start-Sleep 20; Get-Service WatcherDBWebServiceV34
Get-WinEvent -LogName Application -MaxEvents 20 | Where-Object ProviderName -eq 'WatcherDB' | Select-Object TimeCreated,Id,Message
```

## B.4 Prova
| # | Verificacao | Esperado |
|---|---|---|
| 1 | Event Log WatcherDB | 1000 LICENSE_VALIDATION_OK days_left=30 (nao 1001 nem 1003) |
| 2 | `https://localhost:8434/api/v3/health` | 200 |
| 3 | `GET /api/version` | 3.4.0.0 + sha do build |
| 4 | Login no portal (admin do bootstrap) | entra; troca obrigatoria no 1.o login |
| 5 | Overview e LIVE | dados da frota, ou "sem dados" ate' o colector correr |
| 6 | Performance > CPU como viewer | SQL como [oculto - requer nivel dba] #hash |
| 7 | Negativo: licenca de outro servidor e reiniciar | 1001 LicenseFingerprintError; repor |
| 8 | Expiracao: 2.a licenca com data de ontem | LicenseExpiredError / SystemExit; repor |
| 9 | `sc qfailure WatcherDBWebServiceV34` | restart 30 s / 60 s |

## B.5 Rollback
`%ProgramFiles%\WatcherDB\V3.4\uninstall.ps1` (preserva a pasta de dados; `-PurgeSecrets` apaga segredos,
config e licenca) ou `sc.exe delete WatcherDBWebServiceV34` + apagar as duas pastas padrao. Base de teste:
`DROP DATABASE [<BASE>]` pelo `<DBA>`. Licenca: `license_cli.py revoke --license-id <lid>` (vendor).

---

## Excepcao para o teste no PC2 do owner (nao e' cliente)
O PC2 pode apontar a' base partilhada `WatcherDB_Intelligence` em `SQLHDSTST505\I01` (saltar B.2 e o bootstrap;
copiar `servers.json` e `sql_auth_rollout.json` do PC1; usar a MESMA master key do PC1 via -MasterKey para os
segredos cifrados continuarem validos; nunca o blob DPAPI do PC1; o PC2 nao corre o colector). Nome curto
`SQLHDSTST505`; VPN ligada (incidente 21/09).

## Fora deste runbook (entrega a cliente)
Limpeza de IP (nomes reais no canonico, template e guias), CHANGELOG 3.4.0.0, nomes V3.3/8433 nos scripts e
guias, INSTALL_GUIDE dentro do pacote, assinatura Authenticode, drift canonico vs base viva
(Resolved_By_Success_TS, WDB_KPI_MUTE), lotes NOME_DA_BASE_CONFIGURAVEL e PACOTE_SETUP_DATABASE.
