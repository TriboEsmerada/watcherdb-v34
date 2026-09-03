#Requires -Version 5.1
<#
.SYNOPSIS
    Generate a CycloneDX SBOM for the WatcherDB V3.3 Standard Edition bundle.

.DESCRIPTION
    Runs Syft (https://github.com/anchore/syft) over the PyInstaller onedir
    output and produces a CycloneDX JSON SBOM next to the MSI. The SBOM
    enumerates every Python distribution, DLL and native dependency shipped
    inside dist\watcherdb\, which is what banking customers under DORA
    (and increasingly every procurement team) expect alongside a signed
    installer.

    The SBOM is also useful for automated vulnerability scanning: pipe it
    into grype, osv-scanner or trivy on every build to know if a known
    CVE has entered the dependency graph since the last release.

.PARAMETER BundleDir
    Source directory to scan. Default: dist\watcherdb.

.PARAMETER OutputPath
    Output JSON path. Default: dist\msi\WatcherDB_V3.3_Standard.sbom.cyclonedx.json.

.PARAMETER Format
    Syft output format. Default: cyclonedx-json. Acceptable values:
    cyclonedx-json, cyclonedx-xml, spdx-json, syft-json.

.EXAMPLE
    pwsh deploy\build_sbom.ps1

.EXAMPLE
    pwsh deploy\build_sbom.ps1 -Format spdx-json `
        -OutputPath dist\msi\WatcherDB_V3.3_Standard.sbom.spdx.json

.NOTES
    Install Syft via one of:
      winget install Anchore.Syft
      scoop install syft
      choco install syft
    or download the binary from https://github.com/anchore/syft/releases
    and place it on PATH.
#>

[CmdletBinding()]
param(
    [string]$BundleDir,
    [string]$OutputPath,
    [ValidateSet('cyclonedx-json','cyclonedx-xml','spdx-json','syft-json')]
    [string]$Format = 'cyclonedx-json',

    # Manifesto de RUNTIME (nao o lock de build). O Syft dir-scan sozinho
    # SUBESTIMA o bundle: so cataloga pacotes cujo dist-info/METADATA sobreviveu
    # ao PyInstaller, e muitos nao sobrevivem -- o SBOM de 2026-08-20 tinha 21
    # libs pypi e omitia 26 directas, incluindo pyodbc (o componente que fala
    # com o SQL Server do cliente). Um SBOM que omite o pyodbc e' pior que
    # nenhum: mente por omissao a um auditor DORA. A correccao (security-auditor
    # + deploy-architect, 2026-08-20) e' FUNDIR duas fontes:
    #   - Syft dir:bundle       -> .pyd/.dll/.so nativos + runtime C
    #   - requirements (runtime) -> grafo Python declarado, independente do que
    #                               sobreviveu ao empacotamento
    # Usa-se requirements.txt e NAO requirements-build.lock: o lock traz
    # pyinstaller/pytest/pyarmor, que sao ferramentas de BUILD e nao entram no
    # MSI -- inclui-los faria o SBOM afirmar componentes que nao estao no
    # artefacto (o erro inverso, mas ainda um SBOM que mente).
    [string]$LockFile,

    # Salta a camada do lockfile (so' Syft). Nao entregavel a banca -- existe
    # para debug/CI sem a toolchain Python de SBOM instalada.
    [switch]$SyftOnly
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot  = Split-Path -Parent $scriptDir
if (-not $BundleDir)  { $BundleDir  = Join-Path $repoRoot 'dist\watcherdb' }
if (-not $OutputPath) { $OutputPath = Join-Path $repoRoot 'dist\msi\WatcherDB_V3.3_Standard.sbom.cyclonedx.json' }
if (-not $LockFile)   { $LockFile   = Join-Path $repoRoot 'requirements.txt' }

function Write-Step($msg) { Write-Host "[build_sbom] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[build_sbom] OK   $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "[build_sbom] FAIL $msg" -ForegroundColor Red; throw $msg }

# -------------------------------------------------------------------------
# Prerequisites
# -------------------------------------------------------------------------
Write-Step 'Checking Syft installation...'
if (-not (Get-Command syft -ErrorAction SilentlyContinue)) {
    Write-Fail 'syft not found on PATH. Install via winget/scoop/choco or download from https://github.com/anchore/syft/releases'
}
$syftVer = (& syft version 2>&1 | Select-String 'Version:' | Select-Object -First 1).ToString()
Write-Ok $syftVer

if (-not (Test-Path $BundleDir)) {
    Write-Fail "Bundle directory not found: $BundleDir. Run deploy\build.py first."
}
Write-Ok "Scanning: $BundleDir"

# Ensure output directory exists.
$outDir = Split-Path -Parent $OutputPath
if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}

# -------------------------------------------------------------------------
# Run Syft (camada nativa: .pyd/.dll/.so + runtime C)
# -------------------------------------------------------------------------
Write-Step "Running Syft ($Format)..."
# syft scan <source> -o <format>=<file>
$source = "dir:$BundleDir"
$target = "${Format}=${OutputPath}"
& syft scan $source -o $target
if ($LASTEXITCODE -ne 0) {
    Write-Fail "syft exited with code $LASTEXITCODE"
}

if (-not (Test-Path $OutputPath)) {
    Write-Fail "Syft reported success but $OutputPath is missing"
}

# -------------------------------------------------------------------------
# Camada do lockfile (grafo Python completo) e FUSAO com o Syft
# -------------------------------------------------------------------------
# So' para cyclonedx-json (o unico formato entregavel a banca aqui). Nos outros
# formatos o Syft-only e' aceite como debug.
if ($Format -eq 'cyclonedx-json' -and -not $SyftOnly) {
    if (-not (Test-Path $LockFile)) {
        Write-Fail "Lockfile nao encontrado: $LockFile. Sem ele o SBOM subestima o bundle (ver cabecalho). Passa -LockFile <path> ou -SyftOnly para debug."
    }

    # cyclonedx-py corre no interprete do bundle. Procura-o no venv de build.
    $pyExe = Join-Path $repoRoot '.venv-build\Scripts\python.exe'
    if (-not (Test-Path $pyExe)) { $pyExe = 'python' }

    $temCyclone = & $pyExe -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('cyclonedx_py') else 1)" 2>$null; $temCyclone = ($LASTEXITCODE -eq 0)
    if (-not $temCyclone) {
        Write-Fail @"
cyclonedx-py nao instalado no venv de build -- necessario para a camada do
environment (o Syft sozinho subestima o bundle e omitiu o pyodbc no SBOM de 20/08).

Instalar (decisao do owner -- e' mutacao):
    .\.venv-build\Scripts\python.exe -m pip install cyclonedx-bom

Ou correr com -SyftOnly para um SBOM parcial NAO entregavel (debug/CI).
"@
    }

    # environment, NAO requirements: o requirements.txt tem ranges e o
    # cyclonedx-py `requirements` produz componentes SEM versao (inuteis para o
    # CVE scan). O `environment` le as versoes EXACTAS instaladas no venv -- as
    # que foram congeladas no bundle. O merge_sbom.py filtra ao fecho runtime,
    # tirando as build-tools (pyinstaller/pytest) que o venv tem mas o MSI nao.
    $venvBuild = Join-Path $repoRoot '.venv-build'
    $envSbom = [System.IO.Path]::ChangeExtension($OutputPath, $null) + 'env.cyclonedx.json'
    Write-Step 'Gerando SBOM do environment (cyclonedx-py environment, versoes reais)...'
    & $pyExe -m cyclonedx_py environment $venvBuild -o $envSbom --output-format json 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $envSbom)) {
        Write-Fail "cyclonedx-py falhou a gerar o SBOM do environment ($venvBuild)."
    }

    Write-Step 'Fundindo Syft (nativo) + environment filtrado ao runtime...'
    $fundido = & $pyExe (Join-Path $scriptDir 'merge_sbom.py') $OutputPath $envSbom $LockFile 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Fusao dos SBOMs falhou: $fundido"
    }
    Remove-Item -Force $envSbom -ErrorAction SilentlyContinue
    Write-Ok "SBOM fundido: $fundido"

    # -------------------------------------------------------------------------
    # Verificacao de cobertura: o SBOM tem de conter as deps DIRECTAS do lock.
    # E' esta assercao que impede o SBOM de voltar a mentir por omissao.
    # -------------------------------------------------------------------------
    Write-Step 'Verificando cobertura contra o lockfile...'
    $faltam = & $pyExe (Join-Path $scriptDir 'verify_sbom_coverage.py') $OutputPath $LockFile 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Cobertura do SBOM insuficiente:`n$faltam"
    }
    Write-Ok 'Cobertura verificada: todas as dependencias do lockfile presentes no SBOM.'
}

# -------------------------------------------------------------------------
# Sanity check on the CycloneDX output
# -------------------------------------------------------------------------
if ($Format -eq 'cyclonedx-json') {
    try {
        $sbom = Get-Content -Path $OutputPath -Raw | ConvertFrom-Json
    } catch {
        Write-Fail "Output is not valid JSON: $($_.Exception.Message)"
    }
    if (-not $sbom.bomFormat -or $sbom.bomFormat -ne 'CycloneDX') {
        Write-Fail 'Output does not declare bomFormat=CycloneDX.'
    }
    $componentCount = 0
    if ($sbom.components) { $componentCount = @($sbom.components).Count }
    Write-Ok "CycloneDX $($sbom.specVersion) with $componentCount components"
}

$sizeKb = [math]::Round(((Get-Item $OutputPath).Length / 1KB), 1)

# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
Write-Host ''
Write-Host ('=' * 60)
Write-Host '  SBOM BUILD COMPLETE - WatcherDB V3.3 Standard Edition'
Write-Host ('=' * 60)
Write-Host "  Output:   $OutputPath"
Write-Host "  Size:     $sizeKb KB"
Write-Host "  Format:   $Format"
Write-Host ''
Write-Host '  NEXT STEPS:'
Write-Host '  1. Archive alongside the signed MSI and manifest.'
Write-Host '  2. (Optional) Feed the SBOM into grype / osv-scanner /'
Write-Host '     trivy to surface known CVEs before shipping.'
Write-Host '  3. Provide the SBOM to customers on request (DORA article'
Write-Host '     16 - register of information; procurement teams).'
Write-Host ('=' * 60)
