#Requires -Version 5.1
<#
.SYNOPSIS
    Instalador WatcherDB V3.3 Standard Edition (Etapa 3a - veiculo ZIP).
    Corre NO servidor do cliente, elevado (Administrator).

.DESCRIPTION
    Substitui o registo directo via MSI por um script idempotente que faz
    o mesmo trabalho que o Product.wxs faria (ver deploy\msi\Product.wxs
    para a semantica que este script porta): dirs + ACLs em ProgramData,
    registo do servico Windows com failure actions, firewall, EventSource,
    provisioning da master key DPAPI machine-scope, e arranque com
    verificacao de health.

    Compativel Windows PowerShell 5.1 (servidores de cliente podem nao ter
    pwsh 7) -- sem operadores so-pwsh7 (&&, ternario ?:, null-coalescing ??).
    Guardar como ASCII/UTF8-sem-BOM para evitar mojibake em consolas cp1252.

    Layout esperado (ao lado deste ficheiro, dentro do stage do zip):
        release_vars.psd1   <- SOT (ServiceName, WebPort, InstallFolderName, ...)
        watcherdb\           <- bundle PyInstaller (watcherdb.exe + libs)
        install.ps1           <- este ficheiro
        uninstall.ps1
        preflight_target.ps1
        VERSION.txt

.PARAMETER InstallDir
    Destino do bundle. Default: %ProgramFiles%\<InstallFolderName do SOT>
    (normalmente C:\Program Files\WatcherDB\V3.3).

.PARAMETER DataDir
    Diretorio de estado gravavel (config/logs/secrets/inventory/cache).
    Default: %ProgramData%\<DataFolderName do SOT> (normalmente
    C:\ProgramData\WatcherDB). NUNCA apagado por este instalador nem pelo
    uninstall.ps1 (licao Product.wxs FIND #7/S2-7 -- upgrade/uninstall
    preservam sempre dados do cliente).

.PARAMETER ServiceAccount
    Conta Windows sob a qual o servico corre.
      Default: "NT AUTHORITY\NetworkService" (least-privilege, sem AD).
      Conta AD dedicada: "DOMAIN\svc_watcherdb_v33" (usar -ServiceAccountPassword).
      gMSA (sem password, termina em $): "DOMAIN\svc_watcherdb_v33$".

.PARAMETER ServiceAccountPassword
    SecureString com a password da conta AD. OBRIGATORIO se -ServiceAccount
    for uma conta de dominio normal (nao gMSA, nao NetworkService/LocalService/
    LocalSystem). NAO fornecer para gMSA (contas "...$") -- o SCM resolve a
    password via AD automaticamente; passar uma password neste caso e erro.

.PARAMETER FirewallProfile
    Perfis de firewall cobertos pela regra inbound. Default 'Domain,Public'.
    LICAO incidente 2026-06-12: '-Profile Domain' sozinho falha se a
    interface de rede estiver classificada como Public -- o default aqui
    ja cobre os dois perfis mais comuns em servidor. Ajustar so se souberes
    exactamente o perfil real da interface do servidor alvo.

.PARAMETER RemoteSubnet
    CIDR (ex. "10.20.0.0/16") para restringir -RemoteAddress da regra de
    firewall. Default '' = Any (aceita ligacoes de qualquer origem na rede
    permitida pelo perfil) -- AVISO impresso quando vazio. Fortemente
    recomendado definir em ambiente banking/DORA.

.PARAMETER Silent
    Modo nao-interactivo: zero prompts. Requer que -EncryptionKey (ou a
    env var WATCHERDB_ENCRYPTION_KEY previamente definida pelo chamador)
    esteja disponivel quando o master key file ainda nao existir; caso
    contrario o passo de master key falha com exit code 3.

.PARAMETER EncryptionKey
    SecureString com a Fernet master key (mesma usada para cifrar os
    segredos em .env). So e pedida/usada quando
    DataDir\secrets\master.key.dpapi ainda NAO existe (idempotente --
    reinstalacoes nao voltam a pedir). Preferir NAO passar isto na linha
    de comandos em producao (fica no historico do PowerShell); preferir
    -Silent com a env var WATCHERDB_ENCRYPTION_KEY definida por um cofre
    de segredos (Key Vault, CI secret, etc.) imediatamente antes da
    chamada e limpa logo a seguir pelo chamador.

.PARAMETER LicensePath
    Caminho para license.dat a copiar para DataDir\license.dat. Opcional
    -- pode ser feito depois manualmente.

.PARAMETER SkipPreflight
    Salta a chamada a preflight_target.ps1. Usar so se o preflight ja
    correu nesta maquina recentemente (ex.: re-tentativa de install apos
    fix pontual).

.PARAMETER SqlServer
    SQL Server alvo (ex. "SQLHDSTST505\I01") passado ao preflight_target.ps1
    para validar conectividade + login sql_monitoring. Default 'localhost'.

.PARAMETER SkipSqlCheck
    Passa -SkipSqlCheck ao preflight_target.ps1 (sql_monitoring ainda nao
    provisionado pelo DBA do cliente).

.PARAMETER HealthTimeoutSeconds
    Espera maxima para o servico chegar a RUNNING + /api/v3/health responder.
    Default 120. RISCO#8 (cross-check adversarial deploy-architect): a
    errata da Etapa 2 mediu boot ate ~120s COM EDR a fazer scan do bundle
    de 147MB no primeiro arranque (ver RUNBOOK_ETAPA2 fix6 -- BOOT_TIMEOUT_S
    60->120). O boot "limpo" sem EDR observado foi ~12s; 90s como default
    anterior disparava falso negativo (exit 4/5 + necessidade de rollback)
    exactamente no cenario mais realista em cliente banking (EDR agressivo
    ja e requisito da matriz de teste 4.3). Nao reduzir sem confirmar o
    perfil de EDR do cliente alvo.

.EXAMPLE
    # Instalacao default, interactiva, NetworkService
    powershell.exe -ExecutionPolicy Bypass -File install.ps1 -SqlServer "SQLHDSTST505\I01"

.EXAMPLE
    # Silent, conta de dominio, subnet restrita, licenca incluida
    $pwd = ConvertTo-SecureString "P@ssw0rd!" -AsPlainText -Force
    powershell.exe -ExecutionPolicy Bypass -File install.ps1 -Silent `
        -ServiceAccount "BANCO\svc_watcherdb_v33" -ServiceAccountPassword $pwd `
        -RemoteSubnet "10.20.0.0/16" -LicensePath "C:\temp\license.dat" `
        -SqlServer "SQLHDSPRD214\I01"

.EXAMPLE
    # gMSA, sem password
    powershell.exe -ExecutionPolicy Bypass -File install.ps1 `
        -ServiceAccount "BANCO\svc_watcherdb_v33$" -SqlServer "SQLHDSPRD214\I01"

.NOTES
    Exit codes:
      0 = instalacao concluida, servico RUNNING, health OK
      1 = nao elevado (Administrator) -- falha limpa, ZERO alteracoes feitas
      2 = preflight_target.ps1 reportou falhas (target nao pronto)
      3 = master key: sem chave disponivel em -Silent, ou chave invalida
      4 = servico nao chegou a RUNNING dentro do timeout
      5 = health endpoint nao respondeu OK dentro do timeout
      6 = erro de staging/copia/ACL (upgrade ou fresh install)

    Idempotente: correr duas vezes nao duplica registo de servico, regra
    de firewall, EventSource, nem sobrescreve master key ja provisionada.

    DPAPI machine-scope (services\secrets.py, Etapa 1.4): o blob em
    secrets\master.key.dpapi e cifrado com CRYPTPROTECT_LOCAL_MACHINE --
    QUALQUER conta local desta maquina consegue decifra-lo (nao esta
    ligado a conta de servico especifica). Mudar -ServiceAccount num
    upgrade NAO invalida a master key existente; este script reaplica a
    ACL do ficheiro para a NOVA conta em cada execucao E, se a conta
    anterior (lida de HKLM\SOFTWARE\<Manufacturer>\<ProductVersionShort>,
    paridade Product.wxs:152-157) for diferente da actual, remove a ACE
    da conta ANTIGA de DataDir e secrets\ automaticamente (RISCO#10
    fechado -- ja nao depende de accao manual do operador; ver PASSO (d)).

    ACL de secrets\ para a conta de servico e SO-LEITURA ((OI)(CI)R), nao
    Modify: o runtime so LE master.key.dpapi via try_get_master_key()
    (services\secrets.py); a UNICA escrita (provision_master_key_file, via
    wrap-master-key) corre elevada durante o proprio install, coberta pela
    ACE de Administrators:F -- least privilege confirmado por leitura de
    codigo, nao suposicao.

    Author: WatcherDB DevOps (Etapa 3a, auditoria empacotamento 2026-07-03/04)
    See also: deploy\msi\Product.wxs (semantica portada), services\secrets.py,
              watcherdb_service.py, docs\context\auditorias\AUDITORIA_EMPACOTAMENTO_2026-07-04_RUNBOOK_ETAPA2.md
#>

[CmdletBinding()]
param(
    [string]$InstallDir,
    [string]$DataDir,

    [string]$ServiceAccount = 'NT AUTHORITY\NetworkService',
    [SecureString]$ServiceAccountPassword,

    [string]$FirewallProfile = 'Domain,Public',
    [string]$RemoteSubnet = '',

    [switch]$Silent,
    [SecureString]$EncryptionKey,

    [string]$LicensePath = '',

    [switch]$SkipPreflight,
    [string]$SqlServer = 'localhost',
    [switch]$SkipSqlCheck,

    [int]$HealthTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'

function Write-Step($msg) { Write-Host "[install] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[install] OK   $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[install] WARN $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "[install] FAIL $msg" -ForegroundColor Red }

$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  WatcherDB V3.3 Standard - Instalacao (Etapa 3a: ZIP)' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host "  Timestamp: $(Get-Date -Format o)"
Write-Host ''

# =============================================================================
# PASSO (a) - Guard de elevacao. Falha LIMPA, sem tocar em nada, se nao-admin.
# =============================================================================
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Fail 'Este script tem de correr como Administrator (necessario para registar o servico Windows).'
    Write-Fail 'Fecha esta consola e reabre com "Run as administrator". Nenhuma alteracao foi feita.'
    exit 1
}
Write-Ok 'A correr como Administrator.'

# -----------------------------------------------------------------------
# Release vars (SOT) -- import obrigatorio, ZERO valores hardcoded.
# -----------------------------------------------------------------------
$releaseVarsPath = Join-Path $scriptDir 'release_vars.psd1'
if (-not (Test-Path $releaseVarsPath)) {
    Write-Fail "release_vars.psd1 nao encontrado em $scriptDir. Stage incompleto -- reextrair o zip."
    exit 6
}
$rv = Import-PowerShellDataFile -Path $releaseVarsPath
$ServiceName = $rv.ServiceName
$WebPort = $rv.WebPort
$BundleDirName = $rv.BundleDirName

if (-not $InstallDir) { $InstallDir = Join-Path $env:ProgramFiles $rv.InstallFolderName }
if (-not $DataDir)    { $DataDir = Join-Path $env:ProgramData $rv.DataFolderName }

Write-Host "  Produto:         $($rv.ProductName) v$($rv.ProductVersion)"
Write-Host "  InstallDir:      $InstallDir"
Write-Host "  DataDir:         $DataDir"
Write-Host "  ServiceName:     $ServiceName"
Write-Host "  WebPort:         $WebPort"
Write-Host "  ServiceAccount:  $ServiceAccount"
Write-Host "  FirewallProfile: $FirewallProfile"
Write-Host "  RemoteSubnet:    $(if ($RemoteSubnet) { $RemoteSubnet } else { '(vazio -> Any, ver aviso abaixo)' })"
Write-Host "  Silent:          $Silent"
Write-Host ''

$sourceBundleDir = Join-Path $scriptDir $BundleDirName
if (-not (Test-Path (Join-Path $sourceBundleDir 'watcherdb.exe'))) {
    Write-Fail "Bundle nao encontrado em $sourceBundleDir\watcherdb.exe. Stage incompleto -- reextrair o zip."
    exit 6
}

# -----------------------------------------------------------------------
# CONTEXTO: estado de uma instalacao anterior (registry HKLM), lido ANTES
# de qualquer ACL ser aplicada. Paridade com Product.wxs:152-157
# (RegistryValue InstalledVersion em HKLM\SOFTWARE\$(var.Manufacturer)\
# $(var.ProductVersionShort)) -- aqui acrescentamos tambem ServiceAccount,
# para o RISCO#10 (ACEs orfas de conta antiga): se a conta mudou desde a
# ultima instalacao, este script sabe qual era a antiga (SEM adivinhar) e
# limpa a ACE dela em PASSO (d).
# -----------------------------------------------------------------------
$regKeyPath = "HKLM:\SOFTWARE\$($rv.Manufacturer)\$($rv.ProductVersionShort)"
$previousServiceAccount = $null
if (Test-Path $regKeyPath) {
    $existingReg = Get-ItemProperty -Path $regKeyPath -ErrorAction SilentlyContinue
    if ($existingReg -and $existingReg.PSObject.Properties['ServiceAccount']) {
        $previousServiceAccount = $existingReg.ServiceAccount
    }
}
if ($previousServiceAccount) {
    Write-Host "  ServiceAccount anterior (registry): $previousServiceAccount" -ForegroundColor Gray
}

$builtinAccountPatterns = @(
    'nt authority\networkservice', 'nt authority\network service',
    'nt authority\localservice', 'nt authority\local service',
    'localsystem', 'nt authority\system'
)
$isBuiltinAccount = $builtinAccountPatterns -contains $ServiceAccount.Trim().ToLowerInvariant()

# =============================================================================
# PASSO (b) - Preflight
# =============================================================================
Write-Step 'PASSO (b): preflight_target.ps1'
if ($SkipPreflight) {
    Write-Warn '-SkipPreflight indicado. Preflight NAO correu nesta execucao.'
} else {
    $preflightPath = Join-Path $scriptDir 'preflight_target.ps1'
    if (-not (Test-Path $preflightPath)) {
        Write-Fail "preflight_target.ps1 nao encontrado em $scriptDir. Stage incompleto."
        exit 6
    }
    $preflightArgs = @{ SqlServer = $SqlServer }
    if ($ServiceAccount -and $ServiceAccount -ne 'NT AUTHORITY\NetworkService') {
        $preflightArgs['ServiceAccount'] = $ServiceAccount
    }
    if ($SkipSqlCheck) { $preflightArgs['SkipSqlCheck'] = $true }

    & $preflightPath @preflightArgs
    $preflightExit = $LASTEXITCODE
    if ($preflightExit -eq 1) {
        Write-Fail 'Preflight reportou FALHAS. Corrigir antes de instalar (ver output acima). Instalacao ABORTADA.'
        exit 2
    }
    if ($preflightExit -eq 2) {
        Write-Warn 'Preflight passou com AVISOS. A prosseguir (revisar avisos acima).'
    } else {
        Write-Ok 'Preflight PASSOU sem avisos.'
    }
}
Write-Host ''

# =============================================================================
# PASSO (c) - Criar estrutura de diretorios em DataDir
# =============================================================================
Write-Step 'PASSO (c): estrutura de diretorios em DataDir'
# Espelha watcherdb\core\paths.py (config_dir/logs_dir/secrets_dir/
# inventory_dir/cache_dir) -- a app resolve estes mesmos caminhos em runtime.
$subDirs = @('config', 'logs', 'secrets', 'inventory', 'cache')
foreach ($d in $subDirs) {
    $full = Join-Path $DataDir $d
    if (-not (Test-Path $full)) {
        New-Item -ItemType Directory -Path $full -Force | Out-Null
        Write-Ok "Criado: $full"
    } else {
        Write-Host "  Ja existe: $full" -ForegroundColor Gray
    }
}
Write-Host ''

# =============================================================================
# PASSO (d) - ACLs
# =============================================================================
Write-Step 'PASSO (d): ACLs de DataDir'

# Raiz de DataDir + a maioria dos subdirs: SYSTEM + Administrators FullControl,
# conta de servico Modify. Inheritance quebrada aqui para nao herdar Users
# de ProgramData pai (mesma politica de Product.wxs CreateFolder Permission).
$icaclsArgsRoot = @(
    $DataDir,
    '/inheritance:r',
    '/grant:r', 'SYSTEM:(OI)(CI)F',
    '/grant:r', 'BUILTIN\Administrators:(OI)(CI)F',
    '/grant:r', "${ServiceAccount}:(OI)(CI)M",
    '/T', '/C'
)
& icacls @icaclsArgsRoot | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Fail "icacls falhou em $DataDir (exit $LASTEXITCODE). Verificar se ServiceAccount '$ServiceAccount' e um nome resolvivel (DOMAIN\user ou NT AUTHORITY\NetworkService)."
    exit 6
}
Write-Ok "ACL aplicada em $DataDir (SYSTEM+Administrators FullControl, $ServiceAccount Modify, sem heranca de Users)."

# secrets\ mais restrito: mesmos 3 principais, NADA mais (nem Users read).
# ServiceAccount so com LEITURA (R): o runtime so LE master.key.dpapi via
# try_get_master_key() (services\secrets.py); a UNICA escrita e
# provision_master_key_file(), chamada por wrap-master-key durante o
# proprio install (corre elevado, coberto pela ACE Administrators:F).
# Least privilege confirmado por leitura de codigo -- nao suposicao.
$secretsDir = Join-Path $DataDir 'secrets'
$icaclsArgsSecrets = @(
    $secretsDir,
    '/inheritance:r',
    '/grant:r', 'SYSTEM:(OI)(CI)F',
    '/grant:r', 'BUILTIN\Administrators:(OI)(CI)F',
    '/grant:r', "${ServiceAccount}:(OI)(CI)R",
    '/T', '/C'
)
& icacls @icaclsArgsSecrets | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Fail "icacls falhou em $secretsDir (exit $LASTEXITCODE)."
    exit 6
}
Write-Ok "ACL restrita aplicada em $secretsDir (SYSTEM+Administrators FullControl, $ServiceAccount so-leitura; nem Users tem acesso)."

# RISCO#10 (cross-check adversarial deploy-architect): se a conta de
# servico mudou desde a ultima instalacao (lido do registry acima, NAO
# adivinhado), remove a ACE da conta ANTIGA de DataDir e secrets\. So
# corre depois de a NOVA conta ja ter acesso garantido (ordem importa:
# nunca ficar sem nenhuma conta valida a meio do processo).
if ($previousServiceAccount -and ($previousServiceAccount.Trim().ToLowerInvariant() -ne $ServiceAccount.Trim().ToLowerInvariant())) {
    Write-Step "Conta de servico mudou ($previousServiceAccount -> $ServiceAccount) -- a remover ACE antiga."
    foreach ($targetDir in @($DataDir, $secretsDir)) {
        & icacls $targetDir '/remove:g' $previousServiceAccount '/T' '/C' | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "icacls /remove:g '$previousServiceAccount' em $targetDir reportou exit $LASTEXITCODE (pode ja nao ter ACE, ou o nome da conta antiga ja nao resolve -- nao bloqueante)."
        } else {
            Write-Ok "ACE de '$previousServiceAccount' removida de $targetDir."
        }
    }
}
Write-Host ''

# =============================================================================
# PASSO (e) - Copiar bundle (com backup para rollback se upgrade)
# =============================================================================
Write-Step 'PASSO (e): copia do bundle'

$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
$isUpgrade = $false
$backupDir = $null

if (Test-Path $InstallDir) {
    $isUpgrade = $true
    if ($existingService -and $existingService.Status -eq 'Running') {
        Write-Step "Servico existente ($ServiceName) RUNNING -- a parar para upgrade..."
        Stop-Service -Name $ServiceName -Force
        $sw = [Diagnostics.Stopwatch]::StartNew()
        while ((Get-Service -Name $ServiceName).Status -ne 'Stopped' -and $sw.Elapsed.TotalSeconds -lt 60) {
            Start-Sleep -Seconds 2
        }
        if ((Get-Service -Name $ServiceName).Status -ne 'Stopped') {
            Write-Fail "Servico $ServiceName nao parou dentro de 60s. Aborta para nao corromper ficheiros em uso."
            exit 6
        }
        Write-Ok 'Servico parado.'
    }

    $backupDir = "$InstallDir.bak.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Write-Step "Backup do InstallDir existente -> $backupDir (rollback manual: renomear de volta se o upgrade falhar)"
    Rename-Item -Path $InstallDir -NewName (Split-Path -Leaf $backupDir) -Force
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Write-Step "Copiando bundle: $sourceBundleDir -> $InstallDir"
Copy-Item -Path (Join-Path $sourceBundleDir '*') -Destination $InstallDir -Recurse -Force

# uninstall.ps1 + release_vars.psd1 viajam para dentro do InstallDir, para
# que o cliente consiga desinstalar mais tarde sem precisar do zip original.
Copy-Item -Path (Join-Path $scriptDir 'uninstall.ps1') -Destination (Join-Path $InstallDir 'uninstall.ps1') -Force
Copy-Item -Path $releaseVarsPath -Destination (Join-Path $InstallDir 'release_vars.psd1') -Force

if (-not (Test-Path (Join-Path $InstallDir 'watcherdb.exe'))) {
    Write-Fail "Copia terminou mas $InstallDir\watcherdb.exe nao existe. Algo correu mal."
    if ($backupDir -and (Test-Path $backupDir)) {
        Write-Warn "Restaurando backup de $backupDir para $InstallDir (rollback automatico)."
        Remove-Item -Recurse -Force $InstallDir -ErrorAction SilentlyContinue
        Rename-Item -Path $backupDir -NewName (Split-Path -Leaf $InstallDir) -Force
    }
    exit 6
}
Write-Ok "Bundle copiado para $InstallDir."
if ($isUpgrade) {
    Write-Ok "Upgrade: config/logs/secrets/inventory em DataDir PRESERVADOS (vivem fora de InstallDir)."
}
Write-Host ''

# ACL de leitura/execucao no InstallDir para a conta de servico (o binPath
# do servico e watcherdb.exe dentro desta pasta).
$icaclsArgsInstall = @(
    $InstallDir,
    '/grant:r', "${ServiceAccount}:(OI)(CI)RX",
    '/T', '/C'
)
& icacls @icaclsArgsInstall | Out-Null
Write-Ok "ACL de leitura/execucao concedida a $ServiceAccount em $InstallDir."
Write-Host ''

# =============================================================================
# PASSO (f) - Master key DPAPI machine-scope (wrap-master-key)
# =============================================================================
Write-Step 'PASSO (f): master key DPAPI machine-scope'

$masterKeyFile = Join-Path $secretsDir 'master.key.dpapi'
if (Test-Path $masterKeyFile) {
    Write-Ok "master.key.dpapi ja existe em $secretsDir -- nao reprovisionado (idempotente)."
} else {
    $watcherdbExe = Join-Path $InstallDir 'watcherdb.exe'
    $envKeyWasSet = [bool]$env:WATCHERDB_ENCRYPTION_KEY

    if ($EncryptionKey) {
        # Janela de exposicao minima: converter so o tempo necessario, limpar logo a seguir.
        $bstrPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($EncryptionKey)
        $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstrPtr)
        $env:WATCHERDB_DATA_DIR = $DataDir
        $env:WATCHERDB_ENCRYPTION_KEY = $plainKey
        try {
            & $watcherdbExe wrap-master-key
            $wrapExit = $LASTEXITCODE
        } finally {
            Remove-Item Env:WATCHERDB_ENCRYPTION_KEY -ErrorAction SilentlyContinue
            Remove-Item Env:WATCHERDB_DATA_DIR -ErrorAction SilentlyContinue
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstrPtr) | Out-Null
            Remove-Variable plainKey, bstrPtr -Force -ErrorAction SilentlyContinue
        }
    } elseif ($envKeyWasSet) {
        # Silent com env var pre-definida pelo chamador (cofre de segredos).
        # NAO fazemos log do valor em lado nenhum.
        $env:WATCHERDB_DATA_DIR = $DataDir
        try {
            & $watcherdbExe wrap-master-key
            $wrapExit = $LASTEXITCODE
        } finally {
            Remove-Item Env:WATCHERDB_ENCRYPTION_KEY -ErrorAction SilentlyContinue
            Remove-Item Env:WATCHERDB_DATA_DIR -ErrorAction SilentlyContinue
        }
    } elseif (-not $Silent) {
        # Interactivo: o proprio exe pede a chave via getpass (input oculto,
        # nunca impresso). Deixamos correr em foreground sem lhe passar nada.
        $env:WATCHERDB_DATA_DIR = $DataDir
        try {
            & $watcherdbExe wrap-master-key
            $wrapExit = $LASTEXITCODE
        } finally {
            Remove-Item Env:WATCHERDB_DATA_DIR -ErrorAction SilentlyContinue
        }
    } else {
        Write-Fail 'Modo -Silent sem chave disponivel: fornece -EncryptionKey OU define WATCHERDB_ENCRYPTION_KEY no ambiente antes de chamar install.ps1.'
        exit 3
    }

    if ($wrapExit -ne 0) {
        Write-Fail "wrap-master-key falhou (exit $wrapExit). Ver output acima (chave invalida?)."
        exit 3
    }
    if (-not (Test-Path $masterKeyFile)) {
        Write-Fail "wrap-master-key reportou sucesso mas $masterKeyFile nao existe."
        exit 3
    }
    Write-Ok "master.key.dpapi provisionado em $secretsDir."
}
Write-Host ''

# =============================================================================
# PASSO (g) - Licenca
# =============================================================================
Write-Step 'PASSO (g): license.dat'
if ($LicensePath) {
    if (-not (Test-Path $LicensePath)) {
        Write-Fail "LicensePath '$LicensePath' nao existe. Continuar sem licenca (podes copiar manualmente depois)."
    } else {
        Copy-Item -Path $LicensePath -Destination (Join-Path $DataDir 'license.dat') -Force
        Write-Ok "license.dat copiado para $DataDir."
    }
} else {
    Write-Host '  -LicensePath nao fornecido -- sem licenca deployada nesta execucao.' -ForegroundColor Gray
}
Write-Host ''

# =============================================================================
# PASSO (h) - EventSource
# =============================================================================
Write-Step 'PASSO (h): EventLog source'
# DUAS sources distintas em jogo (RISCO#1, cross-check adversarial
# deploy-architect):
#   - "WatcherDB" -- fixa, partilhada entre versoes/produtos. Usada por
#     watcherdb\licensing\startup_guard.py:29 (WINDOWS_EVENT_LOG_SOURCE)
#     via win32evtlogutil.ReportEvent para os eventos de auditoria de
#     licenca (1000-1004). Sem esta source, esses eventos desaparecem
#     SILENCIOSAMENTE do Event Log -- gap de auditoria SIEM/compliance
#     banking (nao um erro visivel, so ausencia de evidencia).
#   - "$ServiceName" -- por instalacao/versao. Usada por
#     servicemanager.LogMsg/LogInfoMsg/LogErrorMsg em watcherdb_service.py
#     (arranque/paragem do servico, mutex, master key).
# Cada uma registada de forma idempotente (SourceExists antes de New-EventLog).
$eventSources = @('WatcherDB', $ServiceName) | Select-Object -Unique
foreach ($src in $eventSources) {
    if ([Diagnostics.EventLog]::SourceExists($src)) {
        Write-Ok "EventLog source '$src' ja existe (idempotente, nada a fazer)."
    } else {
        try {
            New-EventLog -LogName Application -Source $src
            Write-Ok "EventLog source '$src' registado em Application."
        } catch {
            Write-Warn "New-EventLog falhou para '$src': $($_.Exception.Message). O servico ainda funciona (fica so sem eventos amigaveis no Event Viewer -- entradas aparecem como source generico)."
        }
    }
}
Write-Host ''

# =============================================================================
# PASSO (i) - Registo do servico (sc.exe create/config + failure actions)
# =============================================================================
Write-Step 'PASSO (i): registo do servico Windows'

$binPath = "`"$InstallDir\watcherdb.exe`""
$isGmsa = $ServiceAccount.TrimEnd() -match '\$$'

if (-not $existingService) {
    Write-Step "Servico nao existe -- sc.exe create $ServiceName"
    $createArgs = @('create', $ServiceName, 'binPath=', $binPath, 'start=', 'delayed-auto', 'obj=', $ServiceAccount)
    if ($ServiceAccountPassword -and -not $isGmsa) {
        $bstrPtr2 = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($ServiceAccountPassword)
        $plainPwd2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstrPtr2)
        $createArgs += @('password=', $plainPwd2)
    }
    & sc.exe @createArgs
    $scExit = $LASTEXITCODE
    if ($ServiceAccountPassword -and -not $isGmsa) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstrPtr2) | Out-Null
        Remove-Variable plainPwd2, bstrPtr2 -Force -ErrorAction SilentlyContinue
    }
    if ($scExit -ne 0) {
        Write-Fail "sc.exe create falhou (exit $scExit)."
        exit 6
    }
    & sc.exe description $ServiceName $rv.ServiceDescription | Out-Null
    Write-Ok "Servico $ServiceName criado."
} else {
    Write-Step "Servico ja existe -- sc.exe config $ServiceName (idempotente, sem duplicar registo)"
    $configArgs = @('config', $ServiceName, 'binPath=', $binPath, 'start=', 'delayed-auto', 'obj=', $ServiceAccount)
    if ($ServiceAccountPassword -and -not $isGmsa) {
        $bstrPtr3 = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($ServiceAccountPassword)
        $plainPwd3 = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstrPtr3)
        $configArgs += @('password=', $plainPwd3)
    }
    & sc.exe @configArgs
    $scExit = $LASTEXITCODE
    if ($ServiceAccountPassword -and -not $isGmsa) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstrPtr3) | Out-Null
        Remove-Variable plainPwd3, bstrPtr3 -Force -ErrorAction SilentlyContinue
    }
    if ($scExit -ne 0) {
        Write-Fail "sc.exe config falhou (exit $scExit)."
        exit 6
    }
    & sc.exe description $ServiceName $rv.ServiceDescription | Out-Null
    Write-Ok "Servico $ServiceName reconfigurado (upgrade)."
}

# RISCO#5 (cross-check adversarial deploy-architect): SeServiceLogonRight.
# So relevante para contas nao-builtin (AD dedicada ou gMSA) -- NetworkService/
# LocalService/LocalSystem ja tem o direito por natureza, sem GPO a gerir.
if (-not $isBuiltinAccount) {
    Write-Step 'PASSO (i-bis): SeServiceLogonRight (Log on as a service)'
    Write-Host "  sc.exe create/config acima ja concedeu 'Log on as a service' a" -ForegroundColor Gray
    Write-Host "  $ServiceAccount automaticamente via ChangeServiceConfig (SCM) -- nada a" -ForegroundColor Gray
    Write-Host '  fazer manualmente para o arranque IMEDIATO funcionar.' -ForegroundColor Gray
    Write-Warn "GOTCHA GPO: se o cliente gere 'Log on as a service' centralmente por Group Policy (User Rights Assignment), o PROXIMO gpupdate (refresh de background, tipicamente 90-120 min, ou gpupdate /force) APAGA esta concessao local -- o servico fica RUNNING agora mas falha dias depois com 'Logon failure: the user has not been granted the requested logon type'. Pede ao AD team para adicionar $ServiceAccount ao GRUPO AD referenciado nessa GPO (nao conceder na conta directamente) -- so assim sobrevive a proximos gpupdate."

    # Deteccao best-effort (NUNCA falha o install por isto -- so informa).
    try {
        $sidObj = (New-Object Security.Principal.NTAccount($ServiceAccount)).Translate([Security.Principal.SecurityIdentifier])
        $sidValue = $sidObj.Value
        $seceditOut = Join-Path $env:TEMP "watcherdb_secedit_$([Guid]::NewGuid().ToString('N')).cfg"
        & secedit /export /areas USER_RIGHTS /cfg $seceditOut | Out-Null
        if (Test-Path $seceditOut) {
            $seceditContent = Get-Content -Path $seceditOut -Raw
            if ($seceditContent -match 'SeServiceLogonRight\s*=\s*(.+)') {
                $grantedList = $matches[1]
                if ($grantedList -match [regex]::Escape($sidValue)) {
                    Write-Ok "SID $sidValue ($ServiceAccount) presente em SeServiceLogonRight (secedit local, informativo)."
                } else {
                    Write-Warn "SID $sidValue ($ServiceAccount) NAO aparece no export secedit local de SeServiceLogonRight -- pode ser lag do proprio secedit (o sc.exe acabou de conceder) ou pode confirmar o gotcha GPO acima. Revalidar depois de um reboot/gpupdate se o servico falhar mais tarde."
                }
            }
            Remove-Item -Path $seceditOut -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Write-Warn "Deteccao best-effort de SeServiceLogonRight falhou (nao bloqueante, so informativo): $($_.Exception.Message)"
    }
    Write-Host ''
}

# Failure actions: 1a falha=restart 30s, 2a falha=restart 60s, reset contador 24h
# (86400s). Mesma semantica do util:ServiceConfig em Product.wxs.
& sc.exe failure $ServiceName reset= 86400 actions= restart/30000/restart/60000//0 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "sc.exe failure falhou (exit $LASTEXITCODE) -- servico funciona mas sem auto-restart em crash."
} else {
    Write-Ok 'Failure actions configuradas (restart 30s / restart 60s / reset 24h).'
}
Write-Host ''

# =============================================================================
# PASSO (j) - Firewall
# =============================================================================
Write-Step 'PASSO (j): regra de firewall'

if (-not $RemoteSubnet) {
    Write-Warn "RemoteSubnet vazio -- regra aceita ligacoes de QUALQUER origem (RemoteAddress=Any) nos perfis '$FirewallProfile'. Definir -RemoteSubnet e recomendado em ambiente banking/DORA."
}
$remoteAddr = if ($RemoteSubnet) { $RemoteSubnet } else { 'Any' }
$fwDisplayName = "$ServiceName - Inbound $WebPort"

$existingRule = Get-NetFirewallRule -DisplayName $fwDisplayName -ErrorAction SilentlyContinue
if ($existingRule) {
    Write-Step 'Regra de firewall ja existe -- a actualizar (idempotente, sem duplicar).'
    $existingRule | Set-NetFirewallRule -Profile $FirewallProfile -RemoteAddress $remoteAddr -Enabled True
    Write-Ok "Regra '$fwDisplayName' actualizada (perfil: $FirewallProfile, origem: $remoteAddr)."
} else {
    New-NetFirewallRule -DisplayName $fwDisplayName -Direction Inbound -Protocol TCP `
        -LocalPort $WebPort -Action Allow -Profile $FirewallProfile -RemoteAddress $remoteAddr | Out-Null
    Write-Ok "Regra '$fwDisplayName' criada (perfil: $FirewallProfile, origem: $remoteAddr)."
}
Write-Host ''

# =============================================================================
# PASSO (k) - Arranque + verificacao de health
# =============================================================================
Write-Step 'PASSO (k): arranque do servico'

Start-Service -Name $ServiceName
$sw = [Diagnostics.Stopwatch]::StartNew()
$running = $false
while ($sw.Elapsed.TotalSeconds -lt $HealthTimeoutSeconds) {
    $svc = Get-Service -Name $ServiceName
    if ($svc.Status -eq 'Running') { $running = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $running) {
    Write-Fail "Servico $ServiceName nao chegou a RUNNING dentro de $HealthTimeoutSeconds s. Ver Event Viewer (Application, source '$ServiceName') e $DataDir\logs\service_stderr.log."
    exit 4
}
Write-Ok "Servico $ServiceName RUNNING (levou $([math]::Round($sw.Elapsed.TotalSeconds, 1))s)."

Write-Step "A aguardar /api/v3/health em localhost:$WebPort..."
$healthOk = $false
$healthUrl = "http://localhost:$WebPort/api/v3/health"
$swHealth = [Diagnostics.Stopwatch]::StartNew()
while ($swHealth.Elapsed.TotalSeconds -lt $HealthTimeoutSeconds) {
    try {
        $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
        if ($resp.StatusCode -eq 200) { $healthOk = $true; break }
    } catch {
        # Normal durante o arranque (bind ainda nao aconteceu) -- retry.
    }
    Start-Sleep -Seconds 2
}
if (-not $healthOk) {
    Write-Fail "Health endpoint ($healthUrl) nao respondeu 200 dentro de $HealthTimeoutSeconds s. Servico esta RUNNING mas a app pode nao ter arrancado (licenca invalida? ver logs)."
    exit 5
}
Write-Ok "Health OK ($healthUrl -> 200) em $([math]::Round($swHealth.Elapsed.TotalSeconds, 1))s."
Write-Host ''

# =============================================================================
# PASSO (l) - Registo HKLM (paridade Product.wxs InstalledVersion + tracking
# de ServiceAccount para o RISCO#10, ver CONTEXTO acima e PASSO (d))
# =============================================================================
Write-Step 'PASSO (l): registo HKLM'
if (-not (Test-Path $regKeyPath)) {
    New-Item -Path $regKeyPath -Force | Out-Null
}
New-ItemProperty -Path $regKeyPath -Name 'InstalledVersion' -Value $rv.ProductVersion -PropertyType String -Force | Out-Null
New-ItemProperty -Path $regKeyPath -Name 'ServiceAccount' -Value $ServiceAccount -PropertyType String -Force | Out-Null
Write-Ok "$regKeyPath atualizado (InstalledVersion=$($rv.ProductVersion), ServiceAccount=$ServiceAccount)."
Write-Host ''

# =============================================================================
# Sumario
# =============================================================================
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  INSTALACAO CONCLUIDA - WatcherDB V3.3 Standard Edition' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host "  Versao:          $($rv.ProductVersion)"
Write-Host "  Tipo:            $(if ($isUpgrade) { 'UPGRADE' } else { 'FRESH INSTALL' })"
Write-Host "  InstallDir:      $InstallDir"
Write-Host "  DataDir:         $DataDir (preservado em upgrades/uninstall)"
Write-Host "  Servico:         $ServiceName ($ServiceAccount) - RUNNING"
Write-Host "  Porta:           $WebPort - http://localhost:$WebPort"
Write-Host "  Firewall:        $fwDisplayName (perfil $FirewallProfile, origem $remoteAddr)"
if ($backupDir -and (Test-Path $backupDir)) {
    Write-Host "  Backup anterior: $backupDir (podes apagar apos confirmares que o upgrade esta OK)"
}
if ($previousServiceAccount -and ($previousServiceAccount.Trim().ToLowerInvariant() -ne $ServiceAccount.Trim().ToLowerInvariant())) {
    Write-Host "  ServiceAccount:  mudou de '$previousServiceAccount' para '$ServiceAccount' -- ACE antiga removida automaticamente de DataDir/secrets (PASSO d)."
}
Write-Host ''
Write-Host '  Desinstalacao:   ' -NoNewline
Write-Host "$InstallDir\uninstall.ps1" -ForegroundColor Yellow
Write-Host ('=' * 60) -ForegroundColor Cyan

exit 0
