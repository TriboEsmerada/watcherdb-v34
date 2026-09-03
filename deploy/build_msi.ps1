#Requires -Version 5.1
<#
.SYNOPSIS
    Build the WatcherDB V3.3 Standard Edition MSI installer.

.DESCRIPTION
    Runs the WiX Toolset v3 pipeline (heat -> candle -> light) against the
    PyInstaller onedir bundle produced by deploy/build.py.

    Prerequisites:
      * WiX Toolset v3 installed on the build workstation. Download from
        https://github.com/wixtoolset/wix3/releases (the .exe installer is
        enough; the .msi flavour also works). candle.exe, light.exe and
        heat.exe must resolve on PATH.
      * A fresh PyInstaller bundle at dist\watcherdb\ (run
        `python deploy\build.py` first).

    Output:
      dist\msi\WatcherDB_V3.3_Standard.msi

.PARAMETER Clean
    Wipe dist\msi\ and the generated BundleFiles.wxs before rebuilding.

.EXAMPLE
    pwsh deploy\build_msi.ps1

.EXAMPLE
    pwsh deploy\build_msi.ps1 -Clean
#>

[CmdletBinding()]
param(
    [switch]$Clean,

    # Permite correr sem o marcador de proveniencia que o build_release.ps1
    # escreve. Produz um MSI de TESTE LOCAL, sem gate de testes nem assinatura
    # garantidos -- nao entregavel. Mesmo padrao do --allow-unprotected em
    # deploy\build.py, criado depois do incidente de 2026-05-13.
    [switch]$AllowUnverified
)

$ErrorActionPreference = 'Stop'

# -------------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------------
$scriptDir   = Split-Path -Parent $PSCommandPath
$repoRoot    = Split-Path -Parent $scriptDir
$msiSrcDir   = Join-Path $scriptDir 'msi'

# -------------------------------------------------------------------------
# Release metadata SOT (audit FIND #B / S2-5 — elimina drift permanente)
# -------------------------------------------------------------------------
$releaseVarsFile = Join-Path $scriptDir 'release_vars.psd1'
if (-not (Test-Path $releaseVarsFile)) {
    throw "release_vars.psd1 nao encontrado em $releaseVarsFile. Este ficheiro e SOT para VERSION/PORT/SERVICE_NAME."
}
$rv = Import-PowerShellDataFile -Path $releaseVarsFile

$bundleDir   = Join-Path $repoRoot ("dist\" + $rv.BundleDirName)
$outputDir   = Join-Path $repoRoot 'dist\msi'
$bundleWxs   = Join-Path $msiSrcDir 'BundleFiles.wxs'
$msiFile     = Join-Path $outputDir $rv.MsiFileName

function Write-Step($msg) { Write-Host "[build_msi] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[build_msi] OK   $msg" -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "[build_msi] WARN $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "[build_msi] FAIL $msg" -ForegroundColor Red; throw $msg }

# -------------------------------------------------------------------------
# Prerequisite checks
# -------------------------------------------------------------------------
# Auto-resolve do WiX (2026-08-20): o instalador do WiX v3 NAO poe o bin/ no
# PATH, e exigir que cada consola o faca a mao repete o mesmo tropeco em cada
# sessao nova -- o 2o `-Target msi` da historia morreu exactamente aqui, com
# os PASSOS 1-4 ja pagos (gate + PyArmor + PyInstaller + staging). Mesmo
# padrao do LLVM no build_release.ps1: procurar no sitio canonico e prepender
# ao PATH DESTA sessao. O PATH do utilizador continua a ganhar, se ja o tiver.
if (-not (Get-Command 'candle.exe' -ErrorAction SilentlyContinue)) {
    $wixBin = Get-ChildItem "${env:ProgramFiles(x86)}\WiX Toolset*\bin", "$env:ProgramFiles\WiX Toolset*\bin" `
        -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
    if ($wixBin) {
        $env:PATH = "$($wixBin.FullName);$env:PATH"
        Write-Ok "WiX prepended ao PATH desta sessao: $($wixBin.FullName)"
    }
}

Write-Step 'Checking WiX Toolset v3 on PATH...'
foreach ($tool in @('candle.exe', 'light.exe', 'heat.exe')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Fail "WiX tool '$tool' not found on PATH (nem em '\WiX Toolset*\bin'). Install WiX Toolset v3 from https://github.com/wixtoolset/wix3/releases and re-open the shell."
    }
}
# WiX 3.14 banner format: "Windows Installer XML Toolset Compiler version 3.14.1.8722"
# Older versions used "candle.exe [Version X.Y.Z]". Defensive: match generic "version <semver>" with null-guard.
$candleMatch = & candle.exe -? 2>&1 | Select-String -Pattern 'version ([\d\.]+)' | Select-Object -First 1
$candleVer = if ($candleMatch) { $candleMatch.Matches.Groups[1].Value } else { $null }
if ($candleVer) { Write-Ok "WiX candle.exe version $candleVer" } else { Write-Ok 'WiX tools resolved.' }

if (-not (Test-Path (Join-Path $bundleDir 'watcherdb.exe'))) {
    Write-Fail "PyInstaller bundle missing: $bundleDir\watcherdb.exe. Run 'python deploy\build.py' first."
}
Write-Ok "PyInstaller bundle found: $bundleDir"

# -------------------------------------------------------------------------
# Gate de proveniencia (2026-08-19)
# -------------------------------------------------------------------------
# Este script produz um MSI a partir do que estiver em dist\watcherdb, e nao
# tem forma de saber se esse bundle passou pelo gate de testes, se os PE foram
# assinados, ou se houve smoke-boot -- tudo isso vive no build_release.ps1.
#
# Foi assim que nasceu o artefacto que esta em quarentena: invocado a mao, fora
# da linha de montagem, produziu um MSI por assinar e sem SBOM que ficou em
# dist\msi\ com cara de entregavel -- e o INSTALL_GUIDE aponta as pessoas para
# la. Ninguem fez nada de errado; o script simplesmente deixava.
#
# O marcador e' escrito pelo build_release.ps1 depois dos PASSOS 1 a 4 e
# apagado a seguir, inclusive em caso de falha. A escotilha `-AllowUnverified`
# segue o precedente do `--allow-unprotected` no deploy\build.py: o caminho
# manual continua aberto, mas passa a ser uma decisao escrita em vez do default.
$marcadorProveniencia = Join-Path $bundleDir '.release_verified'
if (Test-Path $marcadorProveniencia) {
    Write-Ok "Proveniencia verificada: bundle vem do build_release.ps1"
    Get-Content $marcadorProveniencia | ForEach-Object { Write-Host "         $_" -ForegroundColor DarkGray }
} elseif ($AllowUnverified) {
    Write-Warn 'PROVENIENCIA NAO VERIFICADA (-AllowUnverified).'
    Write-Warn 'O bundle pode nao ter passado pelo gate de testes nem pela assinatura dos PE.'
    Write-Warn 'O MSI resultante NAO e entregavel a cliente -- so para teste local.'
} else {
    Write-Fail @"
Bundle sem prova de proveniencia -- este script nao deve ser invocado a mao.

O caminho sancionado produz o MSI com gate de pytest, assinatura Authenticode
dos PE, smoke-boot, SBOM e manifesto SHA-256:

    pwsh deploy\build_release.ps1 -Target msi

Para um MSI de teste local, sem valor de entrega:

    pwsh deploy\build_msi.ps1 -Clean -AllowUnverified
"@
}

# -------------------------------------------------------------------------
# Clean (optional)
# -------------------------------------------------------------------------
if ($Clean) {
    Write-Step 'Clean requested - removing previous MSI artefacts...'
    if (Test-Path $outputDir) { Remove-Item -Recurse -Force $outputDir }
    if (Test-Path $bundleWxs) { Remove-Item -Force $bundleWxs }
}

New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

# -------------------------------------------------------------------------
# Phase 1: heat.exe harvest
# -------------------------------------------------------------------------
Write-Step 'Phase 1: harvesting bundle with heat.exe...'
# O transform exclui watcherdb.exe do harvest: esse ficheiro e declarado a mao
# em Product.wxs dentro do ServiceRegistrationComp, para servir de KeyPath ao
# ServiceInstall (sem isto o ImagePath do servico fica malformado -- ver o
# cabecalho do .xsl e o incidente 2026-08-12).
$exeExcludeXsl = Join-Path $msiSrcDir 'exclude-service-exe.xsl'
if (-not (Test-Path $exeExcludeXsl)) { Write-Fail "Transform do heat em falta: $exeExcludeXsl" }

$heatArgs = @(
    'dir', $bundleDir,
    '-out', $bundleWxs,
    '-cg', 'BundleFiles',               # ComponentGroup id referenced in Product.wxs
    '-gg',                                # generate GUIDs for components
    '-ag',                                # auto-generate component IDs
    '-sfrag',                             # suppress fragments
    '-sreg',                              # no auto-registry harvesting
    '-srd',                               # suppress root directory
    '-dr', 'INSTALLFOLDER',               # target directory ref in Product.wxs
    '-var', 'var.BundleSourceDir',        # reference preprocessor variable
    '-suid',                              # stable UIDs across heat runs
    '-t', $exeExcludeXsl,                 # exclui watcherdb.exe (declarado a mao)
    '-nologo'
)
& heat.exe @heatArgs
if ($LASTEXITCODE -ne 0) { Write-Fail "heat.exe failed with exit code $LASTEXITCODE" }
Write-Ok "Harvested -> $bundleWxs"

# -------------------------------------------------------------------------
# Phase 2: candle.exe compile
# -------------------------------------------------------------------------
Write-Step 'Phase 2: compiling with candle.exe...'
$productWxs   = Join-Path $msiSrcDir 'Product.wxs'
$objDir       = Join-Path $outputDir 'obj'
New-Item -ItemType Directory -Path $objDir -Force | Out-Null

$candleArgs = @(
    $productWxs,
    $bundleWxs,
    "-dBundleSourceDir=$bundleDir",
    # S2-5: Override Variables.wxi defines com SOT de release_vars.psd1.
    # Se o .psd1 nao definir um valor, candle cai para o .wxi (seguro).
    "-dProductName=$($rv.ProductName)",
    "-dProductVersion=$($rv.ProductVersion)",
    "-dProductVersionShort=$($rv.ProductVersionShort)",
    "-dManufacturer=$($rv.Manufacturer)",
    "-dUpgradeCode=$($rv.UpgradeCode)",
    "-dServiceName=$($rv.ServiceName)",
    "-dServiceDisplayName=$($rv.ServiceDisplayName)",
    "-dServiceDescription=$($rv.ServiceDescription)",
    "-dInstallFolderName=$($rv.InstallFolderName)",
    "-dDataFolderName=$($rv.DataFolderName)",
    "-dWebPort=$($rv.WebPort)",
    '-arch', 'x64',
    '-ext', 'WixUtilExtension',
    '-ext', 'WixUIExtension',
    '-ext', 'WixFirewallExtension',    # Etapa 3b: fire:FirewallException no Product.wxs
    '-out', "$objDir\",
    '-nologo'
)

Write-Ok "SOT carregado de release_vars.psd1: v$($rv.ProductVersion), service=$($rv.ServiceName), port=$($rv.WebPort)"
& candle.exe @candleArgs
if ($LASTEXITCODE -ne 0) { Write-Fail "candle.exe failed with exit code $LASTEXITCODE" }
Write-Ok "Compiled .wixobj files in $objDir"

# -------------------------------------------------------------------------
# Phase 3: light.exe link
# -------------------------------------------------------------------------
Write-Step 'Phase 3: linking with light.exe...'
$wixObjs = Get-ChildItem -Path $objDir -Filter '*.wixobj'
if ($wixObjs.Count -eq 0) { Write-Fail "No .wixobj files produced by candle." }

$lightArgs = @(
    $wixObjs.FullName,
    '-out', $msiFile,
    '-ext', 'WixUtilExtension',
    '-ext', 'WixUIExtension',
    '-ext', 'WixFirewallExtension',    # Etapa 3b: linka a regra de firewall
    '-cultures:en-US',
    '-b', $msiSrcDir,                     # base path for WixUI binder assets (license.rtf etc.)
    '-spdb',                              # don't emit .wixpdb alongside the msi
    '-nologo'
)
& light.exe @lightArgs
if ($LASTEXITCODE -ne 0) { Write-Fail "light.exe failed with exit code $LASTEXITCODE" }

if (-not (Test-Path $msiFile)) { Write-Fail "light.exe returned success but $msiFile is missing" }

$sizeMb = [math]::Round(((Get-Item $msiFile).Length / 1MB), 1)
Write-Ok "Built MSI: $msiFile ($sizeMb MB)"

# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
Write-Host ''
Write-Host ('=' * 60)
Write-Host '  MSI BUILD COMPLETE - WatcherDB V3.3 Standard Edition'
Write-Host ('=' * 60)
Write-Host "  Output: $msiFile"
Write-Host "  Size:   $sizeMb MB"
Write-Host ''
Write-Host '  NEXT STEPS:'
Write-Host '  1. Test install:   msiexec /i ' + $msiFile + ' /qn'
Write-Host '  2. Verify service: Get-Service WatcherDBWebServiceV33'
Write-Host '  3. Test uninstall: msiexec /x ' + $msiFile + ' /qn'
Write-Host '  4. (Sem 4) Sign the MSI with signtool + EV certificate.'
Write-Host ('=' * 60)
