#Requires -Version 5.1
<#
.SYNOPSIS
    Validacao base de uma celula da matriz de teste de instalacao (FASE4 4.3)
    para o veiculo ZIP+install.ps1 do WatcherDB V3.3 Standard Edition.

.DESCRIPTION
    Script READ-ONLY sobre o alvo: nao instala, nao desinstala, nao toca em
    SQL Server (Regra de Ouro #2 -- so servico/HTTP/filesystem/EventLog).
    Compativel PowerShell 5.1 (VMs Srv2016 podem nao ter pwsh 7) -- sem
    operadores so-pwsh7 (&&, ?:, ??). Corre no alvo APOS um install.ps1 ter
    terminado (ou entre passos de uma celula upgrade/rollback/uninstall).

    Checks (todas as celulas, base da matriz 4.3):
      1. Servico $ServiceName RUNNING via SCM (Get-Service)
      2. Porta $Port em LISTENING (Get-NetTCPConnection)
      3. Health endpoint HTTP 200 (Invoke-WebRequest)
      4. DataDir (ProgramData) existe com subpastas esperadas + master key
      5. Zero escrita em InstallDir (Program Files) -- ver 2 modos abaixo
      6. Event Log sem 7000/7009/1053 (Source "Service Control Manager")
         e sem entradas Error dos EventSources do produto ("WatcherDB",
         $ServiceName) desde o inicio da janela de observacao

    MODO do check #5 (zero escrita em Program Files) -- 2 formas, escolhe
    conforme o cenario da celula:

      a) Modo rapido (default, um so invocation): tira snapshot do InstallDir,
         espera -ObservationSeconds (default 60) a fazer poll ao health, tira
         snapshot outra vez, compara. Serve para smoke rapido pos-install.

      b) Modo persistente (recomendado para celulas upgrade/AV-EDR/24h+):
         -SaveBaseline <path.json>  -> so grava snapshot e sai (correr logo
                                       a seguir ao install.ps1 terminar)
         -CompareBaseline <path.json> -> carrega snapshot antigo e compara
                                       com o estado actual (correr horas/dias
                                       depois, ou apos upgrade/uninstall/etc)

      NOTA: isto NAO substitui ProcMon para forense fino (escrita+revert no
      mesmo segundo pode escapar a um diff de timestamp/tamanho). Para as
      celulas 1 (fresh install) e 4 (AV/EDR) da matriz 4.3, correr TAMBEM
      uma sessao ProcMon manual filtrada a watcherdb.exe, focada em
      Program Files -- este script cobre o caso comum, nao o adversarial.

.PARAMETER ServiceName
    Nome do servico Windows. Default 'WatcherDBWebServiceV33' (SOT:
    deploy\release_vars.psd1). Confirmar antes de correr noutra celula/
    versao que o nome nao mudou.

.PARAMETER Port
    Porta HTTP do servico. Default 8433 (SOT: deploy\release_vars.psd1
    WebPort).

.PARAMETER HealthPath
    Path do health endpoint. Default '/api/v3/health' (confirmado em
    install.ps1 PASSO k -- NAO e '/health').

.PARAMETER InstallDir
    Raiz do bundle em Program Files. Default
    'C:\Program Files\WatcherDB\V3.3'.

.PARAMETER DataDir
    Raiz do estado gravavel em ProgramData. Default
    'C:\ProgramData\WatcherDB'.

.PARAMETER ObservationSeconds
    Janela do modo rapido (a). Default 60. Ignorado em -SaveBaseline/
    -CompareBaseline.

.PARAMETER SaveBaseline
    Caminho de ficheiro JSON onde gravar o snapshot do InstallDir e sair
    (nao corre os outros checks). Usar imediatamente a seguir ao
    install.ps1 terminar.

.PARAMETER CompareBaseline
    Caminho de ficheiro JSON de um snapshot anterior (-SaveBaseline). Corre
    TODOS os checks, incluindo o diff do InstallDir contra esse baseline.

.PARAMETER OutputLog
    Caminho de ficheiro de texto onde tambem escrever o transcript (alem do
    ecra). Default: none (so ecra). Recomendado apontar para
    <DataDir>\logs\validate_cell_<timestamp>.log ou para o scratchpad da
    sessao de teste.

.EXAMPLE
    # Smoke rapido pos-install (modo a, 60s de observacao)
    cd "C:\Program Files\WatcherDB\V3.3"
    .\validate_cell.ps1

.EXAMPLE
    # Baseline imediatamente apos o install.ps1 reportar exit 0
    cd "C:\Program Files\WatcherDB\V3.3"
    .\validate_cell.ps1 -SaveBaseline "C:\temp\baseline_cell01.json"

    # ... horas depois, ou apos outra operacao (upgrade/restart/etc) ...
    cd "C:\Program Files\WatcherDB\V3.3"
    .\validate_cell.ps1 -CompareBaseline "C:\temp\baseline_cell01.json" `
        -OutputLog "C:\temp\evidencia_cell01.log"

.NOTES
    Exit codes:
      0 = todos os checks PASS
      1 = 1+ checks FAILED (ver sumario)

    Author: WatcherDB DevOps (validacao matriz FASE4 4.3, Etapa 3a)
    See also: deploy\install.ps1, deploy\uninstall.ps1,
              docs\context\auditorias\AUDITORIA_EMPACOTAMENTO_2026-07-03_FASE4.md
#>

[CmdletBinding()]
param(
    [string]$ServiceName = 'WatcherDBWebServiceV33',
    [int]$Port = 8433,
    [string]$HealthPath = '/api/v3/health',
    [string]$InstallDir = 'C:\Program Files\WatcherDB\V3.3',
    [string]$DataDir = 'C:\ProgramData\WatcherDB',
    [int]$ObservationSeconds = 60,

    [string]$SaveBaseline,
    [string]$CompareBaseline,

    [string]$OutputLog
)

$ErrorActionPreference = 'Continue'

# =============================================================================
# Helpers de output (ecra + log opcional; convencao visual dos scripts deploy\)
# =============================================================================
$script:LogLines = New-Object System.Collections.Generic.List[string]

function Write-Line($msg, $color) {
    if ($color) { Write-Host $msg -ForegroundColor $color } else { Write-Host $msg }
    $script:LogLines.Add($msg)
}
function Write-Step($msg) { Write-Line "[validate_cell] $msg" 'Cyan' }
function Write-Pass($msg) { Write-Line "[validate_cell] PASS $msg" 'Green' }
function Write-Fail($msg) { Write-Line "[validate_cell] FAIL $msg" 'Red' }
function Write-Warn($msg) { Write-Line "[validate_cell] WARN $msg" 'Yellow' }

$results = New-Object System.Collections.Generic.List[PSObject]
function Add-Result($check, $ok, $detail) {
    $results.Add([PSCustomObject]@{ Check = $check; Status = if ($ok) { 'PASS' } else { 'FAIL' }; Detail = $detail })
    if ($ok) { Write-Pass "$check -- $detail" } else { Write-Fail "$check -- $detail" }
}

Write-Line ''
Write-Line '============================================================' 'Cyan'
Write-Line '  WatcherDB V3.3 - Validacao de celula (matriz FASE4 4.3)' 'Cyan'
Write-Line '============================================================' 'Cyan'
Write-Line "  Timestamp:   $(Get-Date -Format o)"
Write-Line "  ServiceName: $ServiceName"
Write-Line "  Port:        $Port"
Write-Line "  HealthPath:  $HealthPath"
Write-Line "  InstallDir:  $InstallDir"
Write-Line "  DataDir:     $DataDir"
Write-Line ''

# =============================================================================
# Modo -SaveBaseline: so tira snapshot do InstallDir e sai
# =============================================================================
function Get-DirSnapshot($root) {
    if (-not (Test-Path $root)) { return @() }
    Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        [PSCustomObject]@{
            RelPath       = $_.FullName.Substring($root.Length).TrimStart('\')
            LastWriteUtc  = $_.LastWriteTimeUtc.ToString('o')
            Length        = $_.Length
        }
    }
}

if ($SaveBaseline) {
    Write-Step "Modo -SaveBaseline: a gravar snapshot de $InstallDir"
    if (-not (Test-Path $InstallDir)) {
        Write-Fail "InstallDir $InstallDir nao existe -- nada para gravar."
        exit 1
    }
    $snap = Get-DirSnapshot $InstallDir
    $payload = [PSCustomObject]@{
        CapturedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
        InstallDir    = $InstallDir
        FileCount     = $snap.Count
        Files         = $snap
    }
    $payload | ConvertTo-Json -Depth 4 | Set-Content -Path $SaveBaseline -Encoding utf8
    Write-Pass "Baseline gravado em $SaveBaseline ($($snap.Count) ficheiros)."
    if ($OutputLog) { Set-Content -Path $OutputLog -Value $script:LogLines -Encoding utf8 }
    exit 0
}

# =============================================================================
# CHECK 1 - Servico RUNNING via SCM
# =============================================================================
Write-Step 'CHECK 1: servico Windows via SCM'
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $svc) {
    Add-Result 'Servico existe no SCM' $false "Get-Service '$ServiceName' nao encontrou o servico."
} else {
    Add-Result 'Servico existe no SCM' $true "Status actual: $($svc.Status)"
    Add-Result 'Servico RUNNING' ($svc.Status -eq 'Running') "Status: $($svc.Status)"
}
Write-Line ''

# =============================================================================
# CHECK 2 - Porta em LISTENING
# =============================================================================
Write-Step "CHECK 2: porta $Port em LISTENING"
$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
Add-Result "Porta $Port LISTENING" ([bool]$listening) $(if ($listening) { "PID $($listening[0].OwningProcess)" } else { "Nenhum socket em LISTEN na porta $Port" })
Write-Line ''

# =============================================================================
# CHECK 3 - Health endpoint HTTP 200
# =============================================================================
Write-Step "CHECK 3: health endpoint http://localhost:$Port$HealthPath"
$healthUrl = "http://localhost:$Port$HealthPath"
$healthOk = $false
$healthDetail = ''
try {
    $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 10
    $healthOk = ($resp.StatusCode -eq 200)
    $healthDetail = "HTTP $($resp.StatusCode)"
} catch {
    $healthDetail = "Excepcao: $($_.Exception.Message)"
}
Add-Result 'Health endpoint 200' $healthOk $healthDetail
Write-Line ''

# =============================================================================
# CHECK 4 - DataDir (ProgramData) com estrutura esperada
# =============================================================================
Write-Step "CHECK 4: DataDir $DataDir"
$dataDirOk = Test-Path $DataDir
Add-Result 'DataDir existe' $dataDirOk $DataDir

if ($dataDirOk) {
    foreach ($sub in @('config', 'logs', 'secrets', 'inventory', 'cache')) {
        $subPath = Join-Path $DataDir $sub
        Add-Result "DataDir\$sub existe" (Test-Path $subPath) $subPath
    }
    $masterKey = Join-Path $DataDir 'secrets\master.key.dpapi'
    Add-Result 'master.key.dpapi provisionado' (Test-Path $masterKey) $masterKey

    $logsDir = Join-Path $DataDir 'logs'
    if (Test-Path $logsDir) {
        $logFiles = Get-ChildItem -Path $logsDir -File -ErrorAction SilentlyContinue
        Add-Result 'logs\ tem ficheiros' ($logFiles.Count -gt 0) "$($logFiles.Count) ficheiro(s) em $logsDir"
    }
}
Write-Line ''

# =============================================================================
# CHECK 5 - Zero escrita em Program Files (InstallDir)
# =============================================================================
Write-Step 'CHECK 5: zero escrita em Program Files (InstallDir)'

if ($CompareBaseline) {
    if (-not (Test-Path $CompareBaseline)) {
        Add-Result 'Baseline InstallDir (comparacao)' $false "-CompareBaseline '$CompareBaseline' nao encontrado."
    } else {
        $baseline = Get-Content -Path $CompareBaseline -Raw | ConvertFrom-Json
        $before = @{}
        foreach ($f in $baseline.Files) { $before[$f.RelPath] = $f }

        $afterSnap = Get-DirSnapshot $InstallDir
        $after = @{}
        foreach ($f in $afterSnap) { $after[$f.RelPath] = $f }

        $added = @($after.Keys | Where-Object { -not $before.ContainsKey($_) })
        $removed = @($before.Keys | Where-Object { -not $after.ContainsKey($_) })
        $changed = @($after.Keys | Where-Object {
            $before.ContainsKey($_) -and
            ($before[$_].Length -ne $after[$_].Length -or $before[$_].LastWriteUtc -ne $after[$_].LastWriteUtc)
        })

        $violations = $added.Count + $removed.Count + $changed.Count
        Add-Result 'Zero escrita em InstallDir (vs baseline)' ($violations -eq 0) `
            "Baseline $($baseline.CapturedAtUtc): +$($added.Count) novos / -$($removed.Count) removidos / ~$($changed.Count) alterados"

        if ($violations -gt 0) {
            foreach ($a in $added)   { Write-Warn "  NOVO:      $a" }
            foreach ($r in $removed) { Write-Warn "  REMOVIDO:  $r" }
            foreach ($c in $changed) { Write-Warn "  ALTERADO:  $c" }
        }
    }
} else {
    Write-Step "Modo rapido: snapshot -> espera ${ObservationSeconds}s (poll ao health) -> snapshot -> diff"
    $before = Get-DirSnapshot $InstallDir
    $beforeMap = @{}
    foreach ($f in $before) { $beforeMap[$f.RelPath] = $f }

    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $ObservationSeconds) {
        try { Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5 | Out-Null } catch { }
        Start-Sleep -Seconds 5
    }

    $after = Get-DirSnapshot $InstallDir
    $afterMap = @{}
    foreach ($f in $after) { $afterMap[$f.RelPath] = $f }

    $added = @($afterMap.Keys | Where-Object { -not $beforeMap.ContainsKey($_) })
    $removed = @($beforeMap.Keys | Where-Object { -not $afterMap.ContainsKey($_) })
    $changed = @($afterMap.Keys | Where-Object {
        $beforeMap.ContainsKey($_) -and
        ($beforeMap[$_].Length -ne $afterMap[$_].Length -or $beforeMap[$_].LastWriteUtc -ne $afterMap[$_].LastWriteUtc)
    })

    $violations = $added.Count + $removed.Count + $changed.Count
    Add-Result "Zero escrita em InstallDir (janela ${ObservationSeconds}s)" ($violations -eq 0) `
        "+$($added.Count) novos / -$($removed.Count) removidos / ~$($changed.Count) alterados"

    if ($violations -gt 0) {
        foreach ($a in $added)   { Write-Warn "  NOVO:      $a" }
        foreach ($r in $removed) { Write-Warn "  REMOVIDO:  $r" }
        foreach ($c in $changed) { Write-Warn "  ALTERADO:  $c" }
    }
    Write-Warn 'Modo rapido cobre so esta janela -- para celulas fresh-install/AV-EDR, complementar com ProcMon manual filtrado a watcherdb.exe.'
}
Write-Line ''

# =============================================================================
# CHECK 6 - Event Log: sem 7000/7009/1053 (SCM) e sem Error do produto
# =============================================================================
Write-Step 'CHECK 6: Event Log (Application)'

# 7000/7009/1053 vem do Source "Service Control Manager", NAO do source do
# produto -- gotcha ja documentado (ver PROACTIVE FINDING #3 abaixo).
$scmEvents = @()
try {
    $scmEvents = Get-EventLog -LogName Application -Source 'Service Control Manager' -ErrorAction SilentlyContinue |
        Where-Object { $_.EventID -in @(7000, 7009, 1053) -and $_.Message -match [regex]::Escape($ServiceName) }
} catch { }
Add-Result 'Sem 7000/7009/1053 (Service Control Manager) para este servico' ($scmEvents.Count -eq 0) `
    "$($scmEvents.Count) evento(s) encontrado(s)"

foreach ($src in @('WatcherDB', $ServiceName) | Select-Object -Unique) {
    $errEvents = @()
    try {
        $errEvents = Get-EventLog -LogName Application -Source $src -EntryType Error -ErrorAction SilentlyContinue
    } catch {
        Write-Warn "Source '$src' nao existe ou Get-EventLog falhou (pode ser normal se a source nunca escreveu Error)."
    }
    Add-Result "Sem entradas Error na source '$src'" ($errEvents.Count -eq 0) "$($errEvents.Count) entrada(s) Error"
}
Write-Line ''

# =============================================================================
# SUMARIO
# =============================================================================
$failCount = ($results | Where-Object { $_.Status -eq 'FAIL' }).Count
$passCount = ($results | Where-Object { $_.Status -eq 'PASS' }).Count

Write-Line '============================================================' 'Cyan'
Write-Line '  SUMARIO' 'Cyan'
Write-Line '============================================================' 'Cyan'
foreach ($r in $results) {
    $color = if ($r.Status -eq 'PASS') { 'Green' } else { 'Red' }
    Write-Line ("  [{0}] {1} -- {2}" -f $r.Status, $r.Check, $r.Detail) $color
}
Write-Line ''
Write-Line "  Total: $passCount PASS / $failCount FAIL de $($results.Count) checks"
Write-Line ''

if ($OutputLog) {
    Set-Content -Path $OutputLog -Value $script:LogLines -Encoding utf8
    Write-Line "  Transcript gravado em: $OutputLog" 'Gray'
}

Write-Line '============================================================' 'Cyan'
Write-Line "  RESULTADO: $(if ($failCount -eq 0) { 'PASS' } else { 'FAIL' })" $(if ($failCount -eq 0) { 'Green' } else { 'Red' })
Write-Line '============================================================' 'Cyan'

if ($failCount -gt 0) { exit 1 }
exit 0
