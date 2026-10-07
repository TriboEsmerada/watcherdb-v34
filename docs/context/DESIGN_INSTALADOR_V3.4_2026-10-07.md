# Desenho do instalador V3.4 Standard - base, login, inventario, provisionamento (2026-10-07)

Fontes: direccao do owner (2026-10-07, CONTEXT.md), parecer do watcherdb-security-auditor (GO-com-14-condicoes),
desenho do watcherdb-deploy-architect (lotes A-E). Runbook: RUNBOOK_INSTALACAO_PC2_V3.4_2026-10-06.md.
Estado: PROPOSTA. Aguarda 4 decisoes do owner (fim). Nada implementado.

## Decisao central
A logica nova vive em Python, como subcomandos do `watcherdb.exe`; o `install.ps1` fica orquestrador fino.
Razoes verificadas: a cifra Fernet so' existe em Python (services/secrets.py); pyodbc e o driver ODBC ja' vao no
bundle; sqlcmd e Invoke-Sqlcmd nao existem em todas as maquinas; o servidor alvo nao tem Python; tudo fica
testavel em pytest. Restricao: watcherdb_service.py:460-478 nao pode importar watcherdb.*/api.* antes do
dispatcher (erro 1053 com EDR) -> imports tardios dentro de cada subcomando.
Pacote novo `watcherdb/install/` (ja' em PROTECT_DIRS): inventory.py, provision.py, dbsetup.py, envfile.py, identity.py.

| Subcomando | Faz |
|---|---|
| `inventory` | .xlsx/.csv/.json/servers.json canonico -> servers.json; `inventory template` gera o modelo .xlsx |
| `provision-login` | `--mode auto\|manual`, `--dry-run`, `--rollback`, `--verify`; identidade DBA nunca persistida |
| `setup-database` | ensure-DB, schema com substituicao de nomes em runtime, estrito (para no 1.o erro) |
| `configure` | escreve o .env (merge idempotente; upgrade nunca reescreve; JWT so' se faltar) |
| `bootstrap-admin` | invoca tools/bootstrap_admin.py |
| `preflight-fleet` | liga com `<LOGIN>` a cada instancia, valida grants, escreve sql_auth_rollout.json |

## Lote A - BASE_E_LOGIN_CONFIGURAVEIS (M, risco medio)
- Canonico: 11 `USE [WatcherDB_Intelligence]` (nao 5) e 73 ocorrencias, 62 fora de USE (CREATE DATABASE :133-177,
  nomes de ficheiros .mdf/_KPI_Data/_KPI_Hist e CHARINDEX :219-275, @database_name nos jobs :4896-5543, SQL
  dinamico com aspas duplicadas :5057,:5144-5297, DB_ID, PRINT). Mais 52 ocorrencias em 23 ficheiros de database/.
  Opcao escolhida: gerar o SQL com o nome substituido EM RUNTIME (re.sub de palavra inteira
  WatcherDB_Intelligence -> <BASE> e sql_monitoring -> <LOGIN>); o canonico fica byte-igual. Salvaguardas:
  identificadores validados por `^[A-Za-z_][A-Za-z0-9_]{0,63}$`; teste "substituir pelo default = byte-identico";
  pos-verificacao aborta se sobrar o nome antigo.
- ORDEM (achado critico): o canonico nao tem CREATE USER/LOGIN mas faz 19 GRANT ... TO [sql_monitoring]
  (:6144-6146, :6164-6173, :6485-6488) que falham numa base nova sem o user, e hoje o erro e' engolido
  (setup_database.ps1:54,61 `| Out-Null` em try/catch). Logo: 1 ensure-DB -> 2 login + CREATE USER em <BASE> ->
  3 schema -> 4 grants nas restantes instancias.
- install.ps1: `-Database` (omissao WatcherDB) e `-SqlLogin` (omissao watcherdb). O `configure` escreve SEMPRE
  INTELLIGENCE_DATABASE e INTELLIGENCE_SQL_USER explicitos (a omissao do instalador difere da do runtime).
- Codigo: centralizar em watcherdb/core/db_identity.py (`intelligence_database()`, `intelligence_sql_login()`);
  helpers.py:142/149, intelligence_kpis.py:278/286, overview_dashboard.py:38/43, settings.py:52 passam a chamar;
  f-strings `[WatcherDB_Intelligence].dbo...` via quote_ident(); teste-gate de literais com allowlist.
  Frota actual inalterada (.env explicito).
- Preflight: preflight_target.ps1:152-155 valida sql_monitoring fixo e :185-186,198 ainda 8433/V33 -> ler do
  release_vars; a validacao do login sai do pre-install e passa ao `preflight-fleet` no fim.
- V1 (guardiao): nada muda nos ficheiros do V1; perguntar se o colector le base/login de config ou literais.

## Lote B - INVENTARIO_XLSX_E_ROLLOUT (M, risco baixo)
- openpyxl read_only/data_only (ja' em requirements.txt:30-31; confirmar hidden import + et_xmlfile no .spec).
  Casos: 1433.0 -> int, booleanos texto, cabecalhos com espacos, folha `Inventario`, linhas vazias, formulas
  sem cache -> erro claro, sanitizar description/hosts.
- JSON com `monitored_servers` = canonico, passthrough (caminho do PC2/frota actual).
- sql_auth_rollout.json no formato de connection_pool.py:578-621 (`{"sql_auth_servers": ["HOST_INST", ...]}`,
  upper-case, `*` = todos, ausente/invalido = fail-closed). REGRA: o rollout nao sai do inventario mas do
  conjunto que PASSOU o `--verify` (login existe, grants aplicados, ligacao funciona). Round-trip testado com o
  ConnectionPool real (`_sql_auth_enabled_for`, `_resolve_credentials`, id `HOST_INSTANCIA` com MSSQLSERVER).
- `auth_mode=windows` viola a Regra de Ouro #2: ERRO por omissao, `--allow-windows-auth` explicito.
- Modelo .xlsx gerado pelo build, nao commitado: folha de instrucoes, 12 colunas, validacao de dados, exemplo.

## Lote C - LOGIN_FROTA_AUTOMATICO_OU_MANUAL (L, risco alto) - GO-com-condicoes (seguranca)
Manual pode avancar ja'; automatico so' com as condicoes abaixo. Modo manual e' o recomendado por omissao em
clientes bancarios; automatico e' opt-in.
1. Identidade: sessao Windows de quem corre (Integrated Security) so' neste passo; sysadmin SQL so' como
   fallback (DMZ/fora do dominio), por prompt seguro, so' em memoria, nunca em argumento/log/relatorio.
   Excepcao a' Regra de Ouro #2 (que e' do produto, nao do instalador) escrita no runbook e no INSTALL_GUIDE.
   Double-hop: correr localmente (WinRM/RDP sem delegacao falha).
2. TLS validado no instalador: Encrypt=yes, TrustServerCertificate=no por omissao (monitoring.py:124,134 usa
   yes: inaceitavel aqui); `--trust-server-cert` explicito e registado.
3. Prova "nada em disco": teste com password sentinela e grep binario em %ProgramData%, %TEMP%, Event Log,
   transcripts e ConsoleHost_history = 0; sem Start-Transcript no instalador.
4. Password: CSPRNG 32 chars, charset seguro para ODBC/T-SQL (sem ' " ; { } = \), 4 classes (CHECK_POLICY=ON,
   CHECK_EXPIRATION=OFF, DEFAULT_DATABASE=master, nunca MUST_CHANGE). Cifrada com a master key em servers.json
   (prefixo `encrypted:`, services/secrets.py:80); nunca em relatorio/log/script. ACL de config\ e .env so'
   SYSTEM/Administrators/<SVC_ACCOUNT>, verificada por icacls, falha se Users ler. Granularidade: DECISAO 4.
5. Rotacao: comando `rotate-login-password` (ALTER LOGIN ... WITH PASSWORD + recifra + verify), pode vir depois
   do 1.o lote, com data; recomendar 90 dias.
6. SID: aleatorio 16 bytes, verificado contra colisao, fixo SO' entre replicas do mesmo `ag_name` (login criado em
   CADA replica, nao so' no listener); nunca DROP/recriar; se existe com SID diferente -> falha clara; nunca
   "adoptar" login existente sem `--adopt`.
7. Permissoes: lista fixa e versionada = docs/security/GRANTS_SQL_MONITORING_INSTANCIA.sql com substituicao de
   nome; `xp_readerrorlog` (GRANTS:40) e `SHOWPLAN` (:41) opcionais via `--minimal`; `EXECUTE AS LOGIN` (:75) sai
   (Regra #2) -> marcador `-- @@VERIFY@@`; ALTER TRACE excluida (DEFAULT_TRACE_ENABLED=False). Splitter de GO.
8. Confirmar por grep da cadeia de chamada que jobs.py:1393-1464 (sp_update_job/sp_add_jobstep/sp_start_job)
   nunca e' executado pelo login (hoje parece ser so' texto de recomendacao).
9. `--dry-run` obrigatorio antes do real (recusa real sem dry-run recente do mesmo inventario); confirmacao por
   contagem de instancias; limite de blast radius (`--confirm-count N`).
10. Rollback gerado ANTES de executar, com hash, idempotente (DROP USER master/msdb, REVOKE, DROP LOGIN), so'
    onde `created=true`; nunca remove login pre-existente; DROP LOGIN falha com sessoes abertas -> reportar.
11. Auditoria: Event Log source WatcherDB, ids 2000 PROVISION_OK / 2001 SKIPPED / 2002 FAILED / 2003 ROLLBACK
    (timestamp, instancia, identidade DBA por nome, accao, resultado, hash do script; sem segredos nem SID
    completo); relatorio JSON por instancia em %ProgramData%\WatcherDB\V3.4\logs\provision_<ts>.json com erros
    sanitizados (regex PWD=/UID=/Password=); retencao 12 meses; pedir ao cliente confirmar que o SQL Audit
    capta CREATE LOGIN/GRANT.
12. Robustez: inalcancaveis nao abortam; sequencial ou paralelismo limitado; 1 tentativa por instancia; parar
    apos N falhas de autenticacao consecutivas (lockout em massa).
13. `preflight-fleet`: ligacao REAL com o login (nao EXECUTE AS), Encrypt=yes, timeout curto;
    IS_SRVROLEMEMBER('sysadmin')=0 obrigatorio; HAS_PERMS_BY_NAME para as esperadas; fn_my_permissions para
    detectar permissoes A MAIS (CONTROL SERVER, ALTER ANY LOGIN, IMPERSONATE, roles fixas) = FAIL; nao db_owner em
    msdb nem datareader em bases de negocio; uma linha por instancia sem dados sensiveis; codigos 18456 estado
    5/8, 233 mapeados para frases; exit 0/2/1; substitui install.ps1:90-93.
14. Modo manual: script sem password, placeholder com guarda que aborta se ficar (`IF @pw LIKE '%<%' RAISERROR`),
    ou `:setvar`; cabecalho com identidade/ambito/impacto/rollback e hash; ACL restrita; a password e' do DBA.
Riscos que levariam a NAO fazer o automatico: supply chain (instalador adulterado com sysadmin em N producoes)
-> assinatura Authenticode + SHA256SUMS + SBOM + dry-run exportavel; frota errada -> contagem + dry-run + allowlist
por ambiente; CAB do cliente proibe ferramentas de terceiros a alterar producao -> o manual existe para isso.

## Lote D - PACOTE_FERRAMENTAS_INSTALACAO (S/M)
Subcomandos substituem .ps1 e Python no alvo; o stage (build_release.ps1:644-654) leva tambem o modelo .xlsx e um
README; lista de assinatura (:671) actualizada; confirmar que docs/security/GRANTS_*.sql vai no bundle (COPY_DIRS)
ou move para database/; `watcherdb.exe --help` lista os subcomandos.

## Lote E - ordem no instalador e INSTALL_GUIDE
1 preflight reduzido -> 2 directorios/ACL, bundle, master key (ja' existe; precede a cifra) -> 3 inventory ->
4 DBA cria a base ou `setup-database --ensure-db` -> 5 provision-login auto/manual/skip (inclui CREATE USER em
<BASE>) -> 6 setup-database + bootstrap-admin -> 7 configure (.env explicito) -> 8 licenca, EventLog, servico,
firewall, arranque -> 9 preflight-fleet + rollout + relatorio.
Switches novos: -Database, -SqlLogin, -InventoryPath, -ProvisionMode Auto|Manual|Skip, -DbaAuth, -DryRun;
exit 7 provision falhou, 8 preflight-fleet falhou. PC2 de teste: `-Database WatcherDB_Intelligence -SqlLogin
sql_monitoring -ProvisionMode Skip -InventoryPath <servers.json do PC1>`.
INSTALL_GUIDE: passos Inventario -> Base -> Login -> Schema -> .env -> Servico -> Prova; "o que e' o login"; modo
manual vs automatico; relatorio e rollback; corrigir V3.3/8433.

## Ordem e tamanho
| # | Lote | Tamanho | Depende |
|---|---|---|---|
| 1 | A.4 db_identity central + gate de literais | M | - |
| 2 | A.1 substituicao em runtime + teste byte-identico | S/M | 1 |
| 3 | D esqueleto de subcomandos (configure, setup-database, bootstrap-admin) | M | 2 |
| 4 | B parser xlsx + rollout + modelo | M | 3 |
| 5 | C provision-login: dry-run -> manual -> auto -> rollback -> verify | L | 3,4 |
| 6 | E install.ps1, preflight_target, INSTALL_GUIDE | M | 3-5 |
Total L (2-3 semanas de um engenheiro, com provas em QLT). 1-2 ja' desbloqueiam a instalacao de teste com outro
nome de base. Antes de tudo: lotes NONCE (pronto) e DATA_DIR_SERVICO (pronto e provado) para o build do PC2.

## Correccoes ao runbook (feitas a 2026-10-07)
- `.env`: o prefixo da password cifrada e' `encrypted:` (services/secrets.py:80, connection_pool.py:497/509), nao
  `enc:`; `enc:` seria tratado como texto claro e a ligacao falharia.
- "So' leitura": verdadeiro nas INSTANCIAS MONITORIZADAS (VIEW SERVER STATE, VIEW ANY DEFINITION, leitura de
  msdb e SQLAgentReaderRole, EXECUTE xp_readerrorlog, SHOWPLAN, EXECUTE sp_help_jobactivity -- GRANTS:33-70), com
  a nota de que VIEW SERVER STATE deixa ver o texto das queries em execucao (o portal redige-o por role). Na base
  do produto `<BASE>` o login ESCREVE: EXECUTE em procs e ALTER nas 10 STG (canonico :6144-6173), INSERT/UPDATE/
  DELETE em KPI_MSSQL_FG_USAGE_HIST (:6488). A frase para o DBA do cliente tem de listar isto.

## Achados laterais (lotes proprios)
- deploy/preflight_target.ps1:185-186,198 valida 8433 e WatcherDBWebServiceV33; fase 4 testa so' 1433.
- deploy/setup_database.ps1:54,61 engole erros (`| Out-Null` em try/catch de comando nativo) e imprime [OK].
- GRANTS_SQL_MONITORING_INSTANCIA.sql:75 usa EXECUTE AS LOGIN (Regra #2).
- modules/monitoring/monitoring.py:124,134 TrustServerCertificate=yes por omissao (pre-existente).

## 4 decisoes do owner (recomendacao primeiro)
1. Permissoes do login em `<BASE>`: um so' login com o conjunto actual do canonico (le e escreve na base do
   produto) [recomendado para o Standard, mais simples], ou dois logins (web so' leitura, colector escrita).
2. O Standard de cliente leva o colector V1? Sem colector a base fica vazia. Se sim, o colector usa o mesmo
   `<LOGIN>` e a mesma `<BASE>` (lote gemeo no V1 com o guardiao).
3. Windows Auth da sessao do DBA SO' no passo de provisionamento, nunca persistida: aceita como excepcao
   documentada a' Regra de Ouro #2? [recomendado: sim; e' a identidade do cliente, com a auditoria do cliente]
4. Password do login: uma por instancia/AG [recomendado pela seguranca: blast radius de 1 servidor; rotacao por
   instancia automatizavel] ou uma unica para a frota [mais simples; blast radius = frota inteira com VIEW
   SERVER STATE].
