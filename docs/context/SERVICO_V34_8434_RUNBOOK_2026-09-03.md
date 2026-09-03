# RUNBOOK — WatcherDBWebServiceV34 (porta 8434), em paralelo ao V33 (8433)

Decisão do owner (2026-09-03): a linha V3.4 ganha serviço Windows próprio na
8434. Parecer `watcherdb-deploy-architect` + `v33-port-collision-checker`
(8434 LIVRE; netstat sem listener; fora do mapa canónico 8433/8443/8449/8450/
8452/8460/8555/8660). Executor: **owner**. A AI só preparou código + blocos.

## Já feito no repo (commit a seguir — `SERVICO_V34_PASSO2_commit.ps1`)
- `watcherdb_service.py`: `SERVICE_NAME=WatcherDBWebServiceV34`, display/desc
  V3.4, `DEFAULT_PORT=8434`, prefixo do mutex `WatcherDBV34_`, banner consola.
- `deploy/release_vars.psd1`: Product 3.4, ServiceName/Display/Desc, `WebPort=8434`,
  `InstallFolderName`/`DataFolderName='WatcherDB\V3.4'` (gap frozen/MSI),
  `MsiFileName` 3.4. `UpgradeCode` mantido de propósito (MSI 3.4 = upgrade da
  3.3 no cliente; comentário no ficheiro).
- `docs/context/COMANDOS_UTEIS_INFRA_LOCAL.md`: tabela de serviços (5) + nota 8434.

## Factos que sustentam o desenho
- Porta em runtime = `WATCHERDB_PORT` do `.env` (fallback `DEFAULT_PORT`).
  `.env` 3-tier: `WATCHERDB_DATA_DIR` > `C:\ProgramData\WatcherDB` (**só frozen**)
  > pasta do repo. Em venv (não-frozen) a V3.4 lê **o seu próprio** `.env` —
  não herda 8433. (`watcherdb/core/paths.py:33-40`)
- Mutex de instância única = hash da pasta → V33 e V34 coexistem por desenho.
- Segredos: o bootstrap copiou o working tree — `.env`, `config/servers.json`,
  `config/sql_servers.json`, `deploy/keys/ed25519_public.pem` já existem na V3.4.
  `license.dat` faz binding por `bios_uuid+cpu_id+hostname` → mesma máquina,
  copiar tal-e-qual. DPAPI master key é machine-scope.
- Web service é **read-mostly** na WatcherDB_Intelligence (routers sem
  INSERT/UPDATE persistente) → sem colisão de escrita entre V33 e V34. Risco
  real: **2× carga** nos servidores monitorizados (2 pools `sql_monitoring`,
  `max_workers=30` cada) — classe do incidente de starvation de 17/08.
- Conta do V33 hoje: `ue_e-snetto@tapnet.tap.pt` (conta pessoal). O V34 segue
  o mesmo padrão por pragmatismo de lab; dívida de least-privilege duplicada
  (finding do deploy-architect; correcção de fundo = conta AD dedicada/gMSA).

## 0. Pré-verificações (tu; leitura)
```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git log --oneline -1                                  # esperado: commit do PASSO 2 (servico V34)
Test-Path .\.env                                      # esperado: True
Select-String -Path .\.env -Pattern '^WATCHERDB_PORT='  # ver se ja' ha' linha (herdada da 3.3 = 8433!)
Test-Path .\secrets\master.key.dpapi                  # se False -> passo 2b
Test-Path .\config\license.dat                        # se False, copiar da V3.3 (mesma maquina)
netstat -ano | findstr :8434                          # esperado: vazio
```

## 1. venv de runtime (mesmo padrão do V33: `.venv-build`, Python 3.11)
```powershell
py -3.11 -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install --upgrade pip
# SEMPRE `python -m pip` — o wrapper Scripts\pip.exe da' "Access is denied" nesta
# maquina (AppLocker/AV bloqueia .exe recem-criado no perfil; visto 03/09).
.\.venv-build\Scripts\python.exe -m pip install -r requirements.txt
# (requirements-build.txt so' se fores fazer build PyArmor/PyInstaller; inclui requirements.txt)
.\.venv-build\Scripts\python.exe -c "import fastapi, uvicorn, pyodbc, win32serviceutil; print('deps OK')"
```

## 2. `.env` — porta explícita (não confiar no DEFAULT_PORT)
```powershell
# 2a. Se o Select-String do passo 0 devolveu WATCHERDB_PORT=8433: EDITAR essa linha para 8434.
#     Se nao devolveu nada:
Add-Content .\.env "WATCHERDB_PORT=8434"
Select-String -Path .\.env -Pattern '^WATCHERDB_PORT='   # esperado: exactamente 1 linha, =8434

# 2b. So' se secrets\master.key.dpapi nao existir:
.\.venv-build\Scripts\python.exe watcherdb_service.py wrap-master-key
```

## 3. Smoke em consola ANTES de instalar o serviço (apanha erros de .env/identidade)
```powershell
.\.venv-build\Scripts\python.exe watcherdb_service.py
# esperado: "[IDENTIDADE] BD = sql ..." e "[START] WatcherDB V3.4 Standard (consola) - http://0.0.0.0:8434"
# noutra janela:
Invoke-WebRequest https://localhost:8434/healthz -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest https://localhost:8434/api/version -UseBasicParsing | Select-Object -ExpandProperty Content
# Ctrl+C na consola para parar (liberta o mutex)
```

## 4. Instalar o serviço (PowerShell **como Administrador**)
```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
.\.venv-build\Scripts\python.exe watcherdb_service.py --startup auto install
# conta: mesma do V33 (password pedida interactivamente, nao fica no historico)
$cred = Get-Credential -UserName "tapnet.tap.pt\ue_e-snetto" -Message "Conta do servico V34"
sc.exe config WatcherDBWebServiceV34 obj= $cred.UserName password= $cred.GetNetworkCredential().Password
Start-Service WatcherDBWebServiceV34
Start-Sleep 20
Get-Service WatcherDBWebServiceV33, WatcherDBWebServiceV34, WatcherDBWebServiceV6 | Format-Table Name,Status,StartType
sc.exe qc WatcherDBWebServiceV34 | Select-String 'BINARY_PATH_NAME|SERVICE_START_NAME' -Context 0,1
# esperado: BINARY_PATH_NAME aponta para ...\WATCHERDB_V3.4\.venv-build\Scripts\python.exe ...\WATCHERDB_V3.4\watcherdb_service.py
```
Nota: `sc.exe config ... password=` é o mesmo padrão usado no V33. Se a conta AD
não tiver "Log on as a service" o Start falha com 1069 — o V33 já tem esse
direito, logo a mesma conta funciona.

## 5. Firewall (só se for acedido de fora desta máquina, como o 8433)
```powershell
New-NetFirewallRule -DisplayName "WatcherDB V34 Web Service" -Direction Inbound -Protocol TCP -LocalPort 8434 -Action Allow -Profile Domain
```

## 6. Validação final
```powershell
netstat -ano | findstr ":8433 :8434"     # 2 LISTENING, PIDs diferentes
Invoke-WebRequest https://localhost:8434/healthz -UseBasicParsing | Select-Object StatusCode
Get-Content .\logs\service_stderr.log -Tail 20 -ErrorAction SilentlyContinue   # sem traceback
```
Browser: `https://ti-pf5hqwk4.tapnet.tap.pt:8434/watcherdb` (TLS ON herdado do `.env`
da 3.3 — `WATCHERDB_TLS_CERT/KEY`; em Windows PowerShell 5.1 o `Invoke-WebRequest`
não tem `-SkipCertificateCheck`, validar no browser) → Backups → modal
"Em atraso (aviso)": deve mostrar **"Limite de aviso: … (excedido há Nh)"** e a
linha **"Cadeia DIFF parada (FULL a cobrir)"** (Lote A, commit 7df2ffe) — a 8433
continua a mostrar o texto antigo (é a V3.3).

## 7. Rollback (não toca no V33)
```powershell
Stop-Service WatcherDBWebServiceV34 -ErrorAction SilentlyContinue
.\.venv-build\Scripts\python.exe watcherdb_service.py remove
Remove-NetFirewallRule -DisplayName "WatcherDB V34 Web Service" -ErrorAction SilentlyContinue
sc.exe qc WatcherDBWebServiceV34    # esperado: erro 1060 (nao existe)
```
`.env`/`config`/`secrets`/`.venv-build` ficam (retomar é só re-instalar).

## Avisos
- **Carga dupla**: enquanto V33 e V34 correm juntos, cada servidor monitorizado
  recebe 2× as sessões `sql_monitoring` do web service. Se aparecer starvation
  (classe 17/08), parar um dos dois durante janelas críticas.
- Não correr o runbook de auditoria de 04/07 (serviço efémero na 8434) com o
  V34 activo — usar 8435 lá.
- `deploy/preflight_target.ps1`, `uninstall.ps1`, `validate_cell.ps1` ainda têm
  defaults 8433/V33 hardcoded (pipeline MSI, não usado nesta fase). Ajustar
  quando/se a V3.4 ganhar pipeline de release.
