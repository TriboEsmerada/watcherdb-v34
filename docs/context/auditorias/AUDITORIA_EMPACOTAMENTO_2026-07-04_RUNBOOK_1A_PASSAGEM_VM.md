# RUNBOOK — 1ª passagem da matriz de teste em VM (veículo ZIP)

Data: 2026-07-04 | Etapa 3a item 3a.4 | Executa: owner | Base: MATRIZ_TESTE_ZIP.md
Ordem: célula 2 → 1 → 11 → 9 → 5 → 8 → 6(proxy) → 7. Gate mínimo = todas estas
com PASS. Células 3/12 = 2ª passagem; 4 (AV/EDR) e 10 (AD) = fora desta passagem.

## Descobertas de código que moldam este runbook (verificadas hoje)

1. **`/api/v3/health` NÃO é liveness puro**: faz `SELECT 1` à BD Intelligence
   (intelligence_kpis.py:999-1022) e devolve **503 sem SQL alcançável**. O
   install.ps1 PASSO (k) exige **200** senão sai com exit 5. Consequência:
   **a VM TEM de alcançar um SQL Server TST com a BD WatcherDB_Intelligence
   e o login sql_monitoring** — VM isolada não fecha a célula 1.
2. **First-run frozen semeia skeletons VAZIOS** (`bootstrap_config()` em
   watcherdb/core/paths.py:84 — servers.json/sql_servers.json/custom_queries.json
   vazios). A app não sabe a que SQL ligar sem config. Consequência: **pré-
   -seed do DataDir com config de teste ANTES do install** (DataDir nunca é
   sobrescrito pelo instalador — seguro).
3. `.env` frozen é lido de **`C:\ProgramData\WatcherDB\.env`** (paths.py:108-114,
   cadeia 3-tier, data_root primeiro).
4. O ZIP atual (3.3.0.0) é `-SkipSigning` → numa máquina com ASR rule
   01443614 ativa o exe é bloqueado (lição Etapa 2). VM de teste com Defender
   default (sem ASR configurado) não bloqueia; se bloquear, é a célula 4 a
   manifestar-se — registar e aplicar exclusão temporária documentada.

## FASE 0 — Kit de teste (montar na dev machine)

Pasta `C:\temp\watcherdb_test_kit\` com:

| Item | Origem | Nota |
|---|---|---|
| `WatcherDB_V3.3_3.3.0.0.zip` + `SHA256SUMS.txt` | `dist\release\3.3.0.0\` | verificar hash na VM |
| `validate_cell.ps1` | `deploy\` (commit 446b7f8) | não vem dentro do ZIP atual |
| `config_test\servers.json` | **criar MÍNIMO à mão** | master_server = Intelligence TST + 1-2 monitored TST. **NUNCA copiar o servers.json da dev machine** — contém o inventário do vendor (99 servers, B0-3); levar isso para uma VM é regressão da sanitização |
| `config_test\.env` | derivar do da dev machine, só chaves TST | segredos cifrados com a MESMA Fernet key que vais dar ao install |
| `license.dat` (se disponível) | dev machine | sem ela: grace period do startup_guard deve permitir boot — se a célula 1 falhar no health por licença, os logs em `DataDir\logs` dizem-no (mensagem do install.ps1:713 aponta lá) |
| Fernet master key | cofre pessoal | pedida no prompt do install (célula 1) e via env var (célula 5) |

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
New-Item -ItemType Directory -Force C:\temp\watcherdb_test_kit | Out-Null
Copy-Item dist\release\3.3.0.0\WatcherDB_V3.3_3.3.0.0.zip, dist\release\3.3.0.0\SHA256SUMS.txt, deploy\validate_cell.ps1 C:\temp\watcherdb_test_kit\
# config_test\servers.json e .env: montar à mão (ver tabela acima)
```

## FASE 1-pre — Provisionar a VM (se ainda não existir)

Versão mínima de Windows: **Server 2016 / Win10 64-bit** (piso do PowerShell
5.1 nativo, exigido pelos scripts; bundle Python 3.11 corre em qualquer
Windows 64-bit moderno). **Recomendado: Server 2022 ou 2019** — SO alvo real
do produto e SO definido pela matriz para a 1ª passagem formal.

Via Hyper-V na dev machine (Win11 Enterprise já traz):

1. Ativar Hyper-V (elevado, exige reboot):
   `Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All`
2. ISO: Windows Server 2022 **Evaluation** (180 dias, grátis) do Microsoft
   Evaluation Center (microsoft.com/evalcenter). Escolher "Desktop Experience"
   na instalação.
3. VM Gen 2 no Hyper-V Manager: 2 vCPU, 4 GB RAM (dinâmica), 60 GB disco,
   **switch EXTERNO** (a VM precisa de alcançar o SQL TST na rede — NAT/
   internal não serve se o TST está na rede corporativa). Se a rede
   corporativa bloquear MACs de VMs, ativar MAC address spoofing na NIC da
   VM ou falar com rede — sem alcance ao TST a célula 1 não fecha.
4. Instalar o SO, definir password de Administrator, renomear a máquina
   (ex. WDBTEST01), configurar IP/DNS se não houver DHCP.
5. Confirmar dentro da VM: `$PSVersionTable.PSVersion` (≥5.1),
   `[Environment]::Is64BitOperatingSystem` (True),
   `Get-ExecutionPolicy -List` (sem AllSigned imposto por GPO).
6. Transferir o kit (FASE 0): com Enhanced Session Mode o copy-paste de
   ficheiros funciona; alternativa é partilha de rede ou montar um ISO/VHD
   com o kit.
7. **SÓ DEPOIS de kit copiado + conectividade TST validada: criar o
   checkpoint "clean"** (Hyper-V Manager → Checkpoint). É a este ponto que
   as células 5/8 fazem reset (`Restore checkpoint`), com o kit já lá dentro.

## FASE 1 — Preparar a VM (uma vez)

- Windows Server 2019/2022, PowerShell 5.1+, **snapshot "clean" tirado ANTES
  de qualquer célula** (as células 5/8 pedem reset a este snapshot).
- Rede: alcance ao SQL TST — validar ANTES de tudo:
  `Test-NetConnection <SQL_TST_HOST> -Port 1433` (ou porta da instância).
- Sem GPO ExecutionPolicy AllSigned (ZIP não assinado; se AllSigned, os .ps1
  nem correm — isso é teste da era pós-signing).
- Copiar o kit para `C:\temp\kit\`; verificar hash:
  ```powershell
  cd C:\temp\kit
  (Get-FileHash .\WatcherDB_V3.3_3.3.0.0.zip -Algorithm SHA256).Hash.ToLower()
  # comparar com a 1a linha de SHA256SUMS.txt
  Expand-Archive .\WatcherDB_V3.3_3.3.0.0.zip -DestinationPath C:\temp\kit\extracted
  ```
- Evidências: `New-Item -ItemType Directory -Force C:\temp\evidencias`
- Transcript global por célula: `Start-Transcript C:\temp\evidencias\cellNN_console.txt`
  no início, `Stop-Transcript` no fim.

## FASE 2 — Células, por ordem

### Célula 2 — Não-admin (primeira: barata, zero instalação)
Consola PowerShell **sem elevação**:
```powershell
cd C:\temp\kit\extracted
powershell.exe -ExecutionPolicy Bypass -File .\install.ps1 -SqlServer "<SQL_TST>"
$LASTEXITCODE   # esperado: 1
Get-Service WatcherDBWebServiceV33 -ErrorAction SilentlyContinue   # esperado: nada
Test-Path 'C:\Program Files\WatcherDB'; Test-Path 'C:\ProgramData\WatcherDB'  # esperado: False False
```
PASS = exit 1 + mensagem limpa + zero artefactos criados.

### Célula 1 — Fresh install default (NetworkService)
Consola **elevada**:
```powershell
cd C:\temp\kit\extracted
# Pré-seed do DataDir (descoberta #2 — install nunca sobrescreve DataDir)
New-Item -ItemType Directory -Force C:\ProgramData\WatcherDB\config | Out-Null
Copy-Item C:\temp\kit\config_test\servers.json C:\ProgramData\WatcherDB\config\
Copy-Item C:\temp\kit\config_test\.env C:\ProgramData\WatcherDB\.env

powershell.exe -ExecutionPolicy Bypass -File .\install.ps1 -SqlServer "<SQL_TST>" `
    -RemoteSubnet "<subnet_lab_CIDR>" -LicensePath "C:\temp\kit\license.dat"
$LASTEXITCODE   # esperado: 0 (prompt da Fernet key a meio)

# Validação + baseline para as células seguintes
Copy-Item C:\temp\kit\validate_cell.ps1 C:\temp\
C:\temp\validate_cell.ps1 -SaveBaseline C:\temp\evidencias\baseline_cell01.json
C:\temp\validate_cell.ps1 -CompareBaseline C:\temp\evidencias\baseline_cell01.json `
    -OutputLog C:\temp\evidencias\cell01_validate.log

# Extras da célula 1 (matriz): JWT sobrevive a restart + HKLM
Restart-Service WatcherDBWebServiceV33; Start-Sleep 30
Invoke-WebRequest http://localhost:8433/api/v3/health -UseBasicParsing | Select-Object StatusCode
Get-ItemProperty 'HKLM:\SOFTWARE\WatcherDB\3.3' | Select-Object InstalledVersion, ServiceAccount
# Login no portal: browser http://<VM>:8433 -> login -> F5 apos restart mantem sessao
```
PASS = exit 0 + validate_cell 100% PASS + health 200 pós-restart + HKLM correto.
(Se health falhar 503: confirmar SELECT 1 manual ao TST a partir da VM e o
servers.json/.env — descoberta #1.)

### Célula 11 — 2ª instância manual (serviço UP)
```powershell
cd 'C:\Program Files\WatcherDB\V3.3\watcherdb'
.\watcherdb.exe   # esperado: mensagem clara de mutex e sai (exit != 0), sem crash
$LASTEXITCODE
Get-Service WatcherDBWebServiceV33   # esperado: Running (intacto)
C:\temp\validate_cell.ps1 -CompareBaseline C:\temp\evidencias\baseline_cell01.json -OutputLog C:\temp\evidencias\cell11_validate.log
```

### Célula 9 — Firewall com interface Public
```powershell
Get-NetConnectionProfile
Set-NetConnectionProfile -InterfaceIndex <idx> -NetworkCategory Public
Get-NetFirewallRule -DisplayName '*WatcherDB*' | Get-NetFirewallProfile   # deve incluir Public
```
Da **dev machine** (ou outra máquina da subnet permitida):
`Test-NetConnection <VM> -Port 8433` → TcpTestSucceeded True + portal abre no browser.
PASS = acesso remoto funciona com o perfil real em Public (re-validação do
incidente 2026-06-12). Repor perfil no fim se quiseres.

### Célula 5 — Silent (reset ao snapshot clean primeiro)
```powershell
# Apos reset: repetir FASE 1 (kit ja la esta se o snapshot foi tirado depois; senao recopiar)
cd C:\temp\kit\extracted
New-Item -ItemType Directory -Force C:\ProgramData\WatcherDB\config | Out-Null
Copy-Item C:\temp\kit\config_test\servers.json C:\ProgramData\WatcherDB\config\
Copy-Item C:\temp\kit\config_test\.env C:\ProgramData\WatcherDB\.env

# NEGATIVO primeiro: silent sem chave -> exit 3 determinístico, sem hang
powershell.exe -ExecutionPolicy Bypass -File .\install.ps1 -Silent -SqlServer "<SQL_TST>"
$LASTEXITCODE   # esperado: 3

# POSITIVO: chave via env var (definir e limpar na mesma consola)
$env:WATCHERDB_ENCRYPTION_KEY = '<fernet_key>'
powershell.exe -ExecutionPolicy Bypass -File .\install.ps1 -Silent -SqlServer "<SQL_TST>" -LicensePath "C:\temp\kit\license.dat"
$LASTEXITCODE; $env:WATCHERDB_ENCRYPTION_KEY = $null
C:\temp\validate_cell.ps1 -OutputLog C:\temp\evidencias\cell05_validate.log
```
PASS = exit 3 no negativo; exit 0 no positivo com estado final idêntico à célula 1.

### Célula 8 — Uninstall → reinstall (a partir do estado da célula 5)
```powershell
& 'C:\Program Files\WatcherDB\V3.3\uninstall.ps1'
Get-Service WatcherDBWebServiceV33 -ErrorAction SilentlyContinue    # nada
Get-NetFirewallRule -DisplayName '*WatcherDB*' -ErrorAction SilentlyContinue  # nada
Test-Path C:\ProgramData\WatcherDB\secrets\master.key.dpapi          # True (preservado!)
Test-Path C:\ProgramData\WatcherDB\config\servers.json               # True

cd C:\temp\kit\extracted
powershell.exe -ExecutionPolicy Bypass -File .\install.ps1 -SqlServer "<SQL_TST>"
# esperado: NAO pede a Fernet key (master.key.dpapi existe, install.ps1:456-458), exit 0
C:\temp\validate_cell.ps1 -OutputLog C:\temp\evidencias\cell08_validate.log
```

### Célula 6 (proxy idempotência) — 2ª execução da mesma versão
```powershell
cd C:\temp\kit\extracted
powershell.exe -ExecutionPolicy Bypass -File .\install.ps1 -SqlServer "<SQL_TST>"
$LASTEXITCODE   # esperado: 0, tipo UPGRADE no sumario
Get-Service WatcherDBWebServiceV33 | Measure-Object                  # 1 servico
(Get-NetFirewallRule -DisplayName '*WatcherDB*').Count               # 1 regra
Get-ChildItem 'C:\Program Files\WatcherDB\V3.3' -Filter '*.bak.*' -Directory  # backup criado
C:\temp\validate_cell.ps1 -OutputLog C:\temp\evidencias\cell06_validate.log
```
Nota: upgrade N-1→N REAL fica pendente até existir 3.3.1.0 (FINDING #2 da matriz).

### Célula 7 — Rollback / kill a meio (ÚLTIMA — deixa estado sujo de propósito)
Duas consolas elevadas. Consola A:
```powershell
cd C:\temp\kit\extracted
powershell.exe -ExecutionPolicy Bypass -File .\install.ps1 -SqlServer "<SQL_TST>"
```
Consola B — matar o processo da consola A durante o PASSO (e) (a cópia do
bundle, ~147MB, dá janela de segundos; identifica o PID pela linha de comandos):
```powershell
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
  Where-Object { $_.CommandLine -match 'install.ps1' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false }
```
Verificar o comportamento **ESPERADO** (FINDING #1 — não é bug):
```powershell
Get-ChildItem 'C:\Program Files\WatcherDB\V3.3' -Filter '*.bak.*'   # .bak orfao presente
Test-Path 'C:\Program Files\WatcherDB\V3.3\watcherdb\watcherdb.exe' # possivelmente False/parcial
# Recovery MANUAL documentado (runbook cliente):
#   Remove-Item InstallDir parcial; Rename-Item <.bak.ts> de volta; Start-Service
```
PASS = estado pós-kill corresponde ao documentado + recovery manual repõe o
serviço RUNNING (correr validate_cell.ps1 no fim do recovery:
`C:\temp\validate_cell.ps1 -OutputLog C:\temp\evidencias\cell07_pos_recovery.log`).

## FASE 3 — Fecho

- 7 células com PASS + logs em `C:\temp\evidencias\` → copiar a pasta para a
  dev machine e anexar como evidência do fecho da 3a.
- Registar no Diário (CONTEXT.md): resultado por célula + achados novos.
- Qualquer FAIL: parar, capturar `DataDir\logs\service_stderr.log` + Event
  Viewer (Application: sources "Service Control Manager", "WatcherDB",
  "WatcherDBWebServiceV33") e trazer para análise antes de continuar.

## Segurança / identidades

- SQL: **só sql_monitoring**, só SELECT (o produto). O runbook em si não
  executa SQL manual; o teste de conectividade é TCP (Test-NetConnection).
- Fernet key: nunca em ficheiro no kit; prompt (célula 1) ou env var
  transitória (célula 5).
- **Inventário do vendor NUNCA entra na VM** — servers.json mínimo criado à mão.
