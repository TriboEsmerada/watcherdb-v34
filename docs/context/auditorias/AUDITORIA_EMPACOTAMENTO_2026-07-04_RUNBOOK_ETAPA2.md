# RUNBOOK Etapa 2 — Serviço SCM + mutex + DPAPI machine-scope (B0-1, 1.4, 1.5)

Data: 2026-07-04 | Branch: `wave-packaging-etapa0` (base 4e29a4e) | Modo consultor: owner executa tudo.

## Objectivo

Fechar o B0-1 (watcherdb.exe não fala o protocolo SCM — erro 1053 garantido no
MSI de maio), dobrando as etapas 1.4 (master key DPAPI machine-scope) e 1.5
(mutex de instância única) + porta 8433 default no bundle. Bónus destravado:
hidden import `pyodbc` (B0-2 — o bundle de maio nem arrancava em consola).

## Desenho (decisões técnicas)

1. **Launcher fino `watcherdb_service.py`** passa a ser o ENTRY_POINT do
   PyInstaller. Razão crítica descoberta nesta sessão: `watcherdb/core/__init__.py`
   importa cache/excel_parser/inventory (= pandas e afins), portanto QUALQUER
   import `watcherdb.*` antes do `StartServiceCtrlDispatcher` rebenta a janela
   de 30s do SCM (ServicesPipeTimeout) num primeiro arranque com EDR a fazer
   scan — reintroduzia o 1053. O launcher é self-contained (só pywin32 +
   stdlib) e duplica inline o 3-tier de `paths.py` (data_root/logs) com
   comentário de manutenção.
2. **Sequência SCM** (verificado no pywin32 instalado, `win32serviceutil.py`
   linha ~1063): o `SvcRun` default reporta `RUNNING` ANTES de chamar
   `SvcDoRun`. O import pesado de `watcherdb_main` (app completa) acontece na
   thread `_serve`, depois do `RUNNING` — handshake SCM nunca bloqueia.
3. **Stop gracioso**: `SvcStop` põe `uvicorn.Server.should_exit = True` (corre
   o lifespan shutdown: scheduler, executors, cache) e o `SvcDoRun` espera até
   ~30s reportando `STOP_PENDING` com waitHint. `SvcShutdown` delega em
   `SvcStop` (lição do Collector Service). Thread uvicorn é daemon = backstop
   se a janela graciosa for excedida.
4. **Modos do exe**: sem args + SCM → serviço; sem args + double-click/smoke →
   dispatcher falha com 1063 → consola (o smoke test continua a funcionar);
   `wrap-master-key` → provisioning DPAPI; restantes args →
   `win32serviceutil.HandleCommandLine` (install/start/stop/remove/debug).
5. **Mutex (1.5)**: `Global\WatcherDBV33_<sha1(data_root)[:12]>`, fallback
   `Local\`. Nome derivado do data_root ⇒ smoke test (com `WATCHERDB_DATA_DIR`
   próprio) coexiste com serviço instalado; dois arranques da MESMA instalação
   não. Consola: mensagem + exit 1. Serviço: LogErrorMsg + arranque abortado.
6. **Secrets (1.4)**: novo tier de topo em `services/secrets.py` — ficheiro
   `secrets_dir()/master.key.dpapi` (base64 de blob `CRYPTPROTECT_LOCAL_MACHINE`
   = 0x4). Qualquer conta DA máquina decripta (NetworkService incluída); a ACL
   do ficheiro é a fronteira (instalador, Etapa 3a). Cadeia: ficheiro
   machine-scope → env DPAPI user-scope (legacy) → plain key. Backwards compat
   total. Novo `try_get_master_key()` público; `api/connection_pool.py`
   `_decrypt` deixa de reimplementar DPAPI inline e delega. Portável para V5:
   o import de `watcherdb.core.paths` está em try/except → no V5 usa
   `WATCHERDB_SECRETS_DIR`; `WATCHERDB_MASTER_KEY_FILE` é override exclusivo.
7. **Porta**: bundle default 8433 (SOT release_vars). Dev `watcherdb_main.py`
   fica em 8000 — deliberado: o serviço dev já ocupa 8433 na workstation;
   o flip de default acontece apenas no caminho do bundle (mesma filosofia do
   paths.py 3-tier).
8. **Nome do serviço**: `WatcherDBWebServiceV33` (SOT `deploy/release_vars.psd1`).
   `services/web_service/service.py` (wrapper dev) fica intacto.

## Ficheiros

| Ficheiro | Ação |
|---|---|
| `watcherdb_service.py` | NOVO — launcher SCM |
| `tests/unit/test_service_entry.py` | NOVO — mutex + porta |
| `tests/unit/test_secrets_machine_scope.py` | NOVO — roundtrip DPAPI real |
| `services/secrets.py` | EDIT — tier ficheiro machine-scope (+V5 propagação) |
| `api/connection_pool.py` | EDIT — `_decrypt` → `try_get_master_key()` |
| `deploy/build.py` | EDIT — PROTECT_FILES += launcher |
| `deploy/watcherdb.spec` | EDIT — ENTRY_POINT + hiddenimports `watcherdb_main`, `pyodbc` |
| `WATCHERDB_V5/services/secrets.py` | EDIT — mesmas âncoras (regra propagação) |

Aplicador (âncoras exatas, valida tudo antes de escrever, dry-run PASSOU
2026-07-04 nos dois repos):
`C:\Users\ue_e-snetto\AppData\Local\Temp\claude\c--Users-ue-e-snetto-Documents-projetosPython-WATCHERDB-V3-3\b4e7fbf2-5413-4687-988f-a7f1dcc95a59\scratchpad\apply_etapa2.py`

## Execução (owner)

### Passo 1 — aplicar

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
py -3.14 "C:\Users\ue_e-snetto\AppData\Local\Temp\claude\c--Users-ue-e-snetto-Documents-projetosPython-WATCHERDB-V3-3\b4e7fbf2-5413-4687-988f-a7f1dcc95a59\scratchpad\apply_etapa2.py"
```

### Passo 2 — validação local (sem rebuild)

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
py -3.14 -m pytest tests/unit -q --no-cov
```

Critério: **as mesmas 7 falhas** da baseline (2 boot bundle de maio, 4 hygiene,
1 startup_guard) e os testes novos (`test_service_entry`,
`test_secrets_machine_scope`) a PASSAR. Zero regressões.

### Passo 3 — rebuild do bundle

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
.venv-build\Scripts\python.exe deploy\build.py
```

### Passo 4 — pytest pós-rebuild

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
py -3.14 -m pytest tests/unit -q --no-cov
```

NOTA esperada: os 2 testes de boot podem passar a VERDE (o hidden import
`pyodbc` era a causa do B0-2) e os `.bak` órfãos somem no rebuild limpo →
baseline pode melhorar de 7 para menos falhas. Melhoria é aceitável e deve
ficar registada; qualquer falha NOVA é regressão.

### Passo 5 — smoke consola + mutex (sem admin)

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
$env:WATCHERDB_DATA_DIR = "C:\Temp\wdb_e2_test"; $env:WATCHERDB_PORT = "8434"; $env:WATCHERDB_LICENSE_ENFORCE = "advisory"
Start-Process -NoNewWindow .\dist\watcherdb\watcherdb.exe
Start-Sleep 25
Invoke-WebRequest http://127.0.0.1:8434/api/v3/health -UseBasicParsing | Select-Object StatusCode   # 200
.\dist\watcherdb\watcherdb.exe   # 2a instancia MESMO data dir -> [ERRO] mutex, exit 1
echo "exit=$LASTEXITCODE"        # 1
Get-Process watcherdb | Stop-Process   # limpar a 1a instancia
Remove-Item Env:WATCHERDB_DATA_DIR, Env:WATCHERDB_PORT, Env:WATCHERDB_LICENSE_ENFORCE
```

### Passo 6 — provisioning DPAPI machine-scope (1.4)

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
# chave Fernet de TESTE (nao usar a de producao aqui)
py -3.14 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
$env:WATCHERDB_DATA_DIR = "C:\Temp\wdb_e2_test"
$env:WATCHERDB_ENCRYPTION_KEY = "<chave de teste do comando acima>"
.\dist\watcherdb\watcherdb.exe wrap-master-key   # -> C:\Temp\wdb_e2_test\secrets\master.key.dpapi
# .env de teste com um secret cifrado por essa chave (forca o load da master key no arranque)
py -3.14 -c "from cryptography.fernet import Fernet; import os; k=os.environ['WATCHERDB_ENCRYPTION_KEY'].encode(); print('INTELLIGENCE_SQL_PASSWORD=encrypted:'+Fernet(k).encrypt(b'dummy').decode())" | Out-File -Encoding ascii C:\Temp\wdb_e2_test\.env
Remove-Item Env:WATCHERDB_ENCRYPTION_KEY, Env:WATCHERDB_DATA_DIR
```

### Passo 7 — teste SCM real (admin; é ESTE o teste que o B0-1 nunca teve)

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
icacls C:\Temp\wdb_e2_test /grant "NT AUTHORITY\NetworkService:(OI)(CI)M"
icacls .\dist\watcherdb /grant "NT AUTHORITY\NetworkService:(OI)(CI)RX"
sc.exe create WatcherDBV33_TEST binPath= "$PWD\dist\watcherdb\watcherdb.exe" start= demand obj= "NT AUTHORITY\NetworkService"
reg add "HKLM\SYSTEM\CurrentControlSet\Services\WatcherDBV33_TEST" /v Environment /t REG_MULTI_SZ /d "WATCHERDB_DATA_DIR=C:\Temp\wdb_e2_test\0WATCHERDB_PORT=8434\0WATCHERDB_LICENSE_ENFORCE=advisory" /f
sc.exe start WatcherDBV33_TEST
sc.exe query WatcherDBV33_TEST          # imediato: RUNNING (dispatcher ligou)
Start-Sleep 30
Invoke-WebRequest http://127.0.0.1:8434/api/v3/health -UseBasicParsing | Select-Object StatusCode   # 200
# validacao 1.4: a master key veio do ficheiro machine-scope, lida por NetworkService
Select-String -Path C:\Temp\wdb_e2_test\logs\*.log -Pattern "machine-scope DPAPI key file"
# stop gracioso
sc.exe stop WatcherDBV33_TEST
Start-Sleep 15
sc.exe query WatcherDBV33_TEST          # STOPPED
Get-Content C:\Temp\wdb_e2_test\logs\service_stderr.log -Tail 20   # sem tracebacks
# limpeza
sc.exe delete WatcherDBV33_TEST
Remove-Item -Recurse -Force C:\Temp\wdb_e2_test
```

Impacto: cria/apaga um serviço de TESTE local (nome próprio, porta 8434) — não
toca no serviço dev `WatcherDBWebServiceV33` nem em DB alguma. Identidade de
runtime: NetworkService; zero ligações SQL necessárias para o critério de
sucesso (health endpoint não toca na Intelligence DB).

### Passo 8 — commits (após validação)

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git add watcherdb_service.py tests/unit/test_service_entry.py tests/unit/test_secrets_machine_scope.py services/secrets.py api/connection_pool.py deploy/build.py deploy/watcherdb.spec
git commit -m 'fix(packaging): etapa 2 servico SCM + mutex + DPAPI machine-scope (B0-1)' -m 'launcher watcherdb_service.py fala protocolo SCM; mutex instancia unica por data_root; master key em ficheiro DPAPI machine-scope; porta 8433 default no bundle; hiddenimports watcherdb_main e pyodbc (B0-2)'
```

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V5"
git checkout -b wave-secrets-machine-scope
git add services/secrets.py
git commit -m 'feat(secrets): tier master key ficheiro DPAPI machine-scope (propagacao V3.3 etapa 1.4)' -m 'ficheiro master.key.dpapi via WATCHERDB_SECRETS_DIR ou WATCHERDB_MASTER_KEY_FILE; wrap_key_dpapi ganha machine_scope; novos provision_master_key_file e try_get_master_key; backwards compat env DPAPI e plain key'
```

## Rollback

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
git checkout -- services/secrets.py api/connection_pool.py deploy/build.py deploy/watcherdb.spec
Remove-Item watcherdb_service.py, tests\unit\test_service_entry.py, tests\unit\test_secrets_machine_scope.py
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V5"
git checkout -- services/secrets.py
```

## ERRATA — execução 2026-07-04 (validação encontrou 8 bloqueios reais + fixes 1-8)

A validação end-to-end desmontou uma cebola de defeitos invisíveis até alguém
tentar correr o bundle a sério. Todos corrigidos via aplicadores fix1-fix8
(scratchpad da sessão); registados aqui porque cada um é lição de packaging:

1. **clang fora do PATH persistente** — BCC do PyArmor exige LLVM; o build de
   maio corria numa shell com PATH ad-hoc. Workaround: prefixo por sessão.
   Backlog 3a: preflight `clang.exe` no build.py ao lado do check_pyarmor.
2. **ASR "Block executables unless prevalence/age/trusted" (GUID 01443614-...)**
   bloqueou o exe recém-compilado (Event 1121; cada rebuild = hash novo).
   Exclusão ASR local para `dist\watcherdb` aplicada na workstation. Para
   cliente: assinatura (3a) + exclusão/whitelist no onboarding banking.
3. **BCC quebra o `except` do fallback 1063** — pywintypes.error não era
   apanhado em código BCC-compilado (funciona em CPython puro; provado).
   Fix1: launcher SAI do PyArmor (PROTECT→COPY; boilerplate sem IP).
4. **RFT renomeia símbolos cross-module de forma inconsistente** —
   `SQLQueries`→`pyarmor__428` só no consumidor, MESMO run --recursive
   (ImportError no boot). Fix2: RFT removido do build; BCC (proteção real)
   mantém-se. Latente desde sempre — o boot de maio morria antes.
5. **Imports third-party dentro de fontes BCC são invisíveis ao PyInstaller**
   (pyodbc, structlog, jose.jwt — um por rebuild). Fix3+5: o spec faz AST
   scan das fontes PLAIN em build-time e adiciona todos os imports (dotted +
   top + candidatos `from X import Y`) a hiddenimports. Reproduzível.
6. **stdlib só referenciada em fontes BCC também fica fora** (email.mime →
   canais de alerta email mortos em TODOS os bundles anteriores). Fix6:
   o scan deixou de excluir stdlib.
7. **passlib resolve handlers por string em runtime** → fix4:
   collect_submodules("passlib").
8. **O boot test tinha deadlock de PIPE**: Popen(stdout=PIPE) sem drenar +
   arranque agora verboso (>64KB) = processo bloqueado em write() antes do
   bind (exe binda em ~12s com stdout em ficheiro). Fix7: stdout→ficheiro,
   diagnóstico passa a tail. Fix6: BOOT_TIMEOUT_S 60→120 (bundle 147MB +
   EDR scan). Fix8: /docs 401 aceite (auth middleware agora carrega no
   bundle — comportamento de produção correto).

Trade-off aceite: bundle 71→147 MB (imports completos). Dieta + decisão
sobre extras opcionais (alerting/analytics: aiosmtplib, slack_sdk, pymsteams,
matplotlib, sklearn ausentes do venv-build) = Etapa 3a.

Cosmético (polish 3a): tracebacks em consola arrastam o 1063 como
`__context__` (uvicorn corre dentro do except do fallback) — mover
run_console() para fora do bloco except.

### Resultados da validação (2026-07-04)

- Pytest: 2 boot tests VERDES (health 200 + /docs 401); restantes falhas = 5
  da baseline conhecida (4 hygiene + 1 startup_guard). Zero regressões.
- Consola: bind em ~12s, licença OK, ~30 routers, KPIs reais.
- Mutex (1.5): 2ª instância recusada (`Global\WatcherDBV33_8f38d59481d8`),
  exit=1.
- SCM (B0-1): sc start → RUNNING imediato como NetworkService; health 200
  servido pelo serviço; sc stop → STOP_PENDING → STOPPED gracioso
  ("Application shutdown complete"). Serviço de teste apagado.
- DPAPI machine-scope (1.4): `wrap-master-key` validou input (recusou
  placeholder) e escreveu o blob; serviço NetworkService leu-o —
  `service_stderr.log:130: Master key loaded from machine-scope DPAPI key
  file`. Blob criado pelo admin, lido por outra conta = prova machine-scope.
- Bónus de evidência: `Login failed for user 'TAPNET\\TI-PF5HQWK4$'` no
  serviço = confirmação viva do achado FASE 1 (Trusted_Connection +
  NetworkService sem GRANT); resolve-se no identity flip 1.2 (piloto).

## Pendências que ficam para a Etapa 3a

- ZIP + install.ps1 assinado (veículo default decidido na FASE 4), incluindo:
  registo do serviço, ACL de `ProgramData\WatcherDB\secrets\`, firewall 8433,
  chamada a `wrap-master-key` no fluxo de instalação.
- Deprecar/limpar `services/web_service/service.py` como caminho de produção
  (fica como wrapper dev) e alinhar `service_health.txt`/heartbeat se ainda
  fizer falta no bundle.
- `.bak` órfãos em config/+dist somem no rebuild limpo (test_no_bak_files).
