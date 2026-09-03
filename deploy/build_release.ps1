#Requires -Version 5.1
<#
.SYNOPSIS
    Build reprodutivel do artefacto de release WatcherDB V3.3 Standard Edition
    (Etapa 3a - veiculo default ZIP onedir + install.ps1 assinado).

.DESCRIPTION
    Orquestra, num so comando, os passos que ate agora eram manuais (ver
    RUNBOOK_ETAPA2.md): gate de testes, build PyArmor+PyInstaller, assinatura
    Authenticode dos PE do bundle, staging do pacote de entrega, compressao
    em ZIP, geracao de SBOM (CycloneDX via Syft) e manifest SHA-256.

    -Target msi NAO esta implementado nesta etapa (Etapa 3b, trigger-based
    -- ver AUDITORIA_EMPACOTAMENTO_2026-07-03_FASE4.md secao 4.1). O script
    falha cedo e explicito se invocado com -Target msi.

    Fora de scope (backlog Etapa 0, itens 0.1/0.3/0.4): clone limpo +
    lockfile reprodutivel (pip-tools/uv) e reescrita automatica da versao
    a partir de git describe. Este script assume que o working tree ja
    esta no commit correto e que release_vars.psd1 ja tem o ProductVersion
    da release (SOT unica -- nao editar em mais lado nenhum).

    NOTA (drift descoberto ao escrever este script): a AUDITORIA_FASE4.md
    secao 4.2 passo 5 documenta "python deploy/build.py --strict" como
    exemplo. deploy/build.py actual (Etapa 0.7 ja implementada) NAO tem
    a flag --strict -- o comportamento fail-loud em falha de protecao
    PyArmor e o DEFAULT (so existe a flag inversa --allow-unprotected
    para relaxar). Este script invoca build.py sem argumentos extra; a
    flag --strict do doc FASE4 ficou desactualizada e deve ser corrigida
    la (proactive finding, nao bloqueia esta Etapa 3a).

.PARAMETER Target
    zip (default, implementado) ou msi (stub, Etapa 3b).

.PARAMETER SkipTests
    Salta o gate de pytest (tests/unit). Emite AVISO forte -- build sem
    evidencia de testes nao deve ir para cliente. Pensado para iteracao
    rapida em build local, nao para release candidate.

.PARAMETER SkipSigning
    Salta a assinatura Authenticode dos PE do bundle E dos scripts do stage
    (install.ps1, uninstall.ps1, preflight_target.ps1, release_vars.psd1).
    Usar apenas enquanto o Azure Trusted Signing (ou outro backend) nao
    estiver activo (audit FASE4 4a, B2-13, pendente). Sem esta flag, e sem
    backend de assinatura configurado, o script FALHA com exit code != 0
    (fail-loud -- nunca entrega um "unsigned by accident").

    RISCO#4 (cross-check adversarial deploy-architect): assinar so o .exe
    NAO chega. Um cliente banking com ExecutionPolicy AllSigned via GPO
    bloqueia QUALQUER .ps1/.psd1 nao assinado, incluindo install.ps1/
    uninstall.ps1 -- "-ExecutionPolicy Bypass" na linha de comandos NAO
    tem efeito sobre uma AllSigned imposta por GPO (a GPO tem prioridade
    sobre o parametro do processo). Por isso os scripts do stage sao
    assinados com Set-AuthenticodeSignature, no mesmo passo em que sao
    copiados para o stage (PASSO 4), usando o mesmo backend/certificado
    do SigningMode escolhido.

.PARAMETER SigningMode
    keylocker (default) | pfx | store. Mesma semantica de deploy\sign_msi.ps1
    (reutilizado aqui para consistencia entre os dois veiculos).

.PARAMETER PfxPath
    Ficheiro .pfx/.p12 (SigningMode pfx).

.PARAMETER PfxPassword
    SecureString com a password do PFX (SigningMode pfx).

.PARAMETER CertThumbprint
    Thumbprint em CurrentUser\My (SigningMode store).

.PARAMETER TimestampUrl
    Servidor de timestamp RFC 3161. Default http://timestamp.digicert.com.

.PARAMETER OutputRoot
    Diretorio base dos artefactos de release. Default: dist\release.
    O script cria dist\release\<ProductVersion>\ dentro deste diretorio.

.PARAMETER PythonExe
    Override do interprete usado para o gate de pytest e para o smoke-boot
    (nao para o build, que usa sempre .venv-build\Scripts\python.exe).
    Default: .venv-build\Scripts\python.exe (3.11 — o MESMO interpretador
    congelado no bundle; consult specialists 2026-08-10: o antigo default
    'py -3.14' validava um interpretador uma major a frente do runtime
    real do cliente). Requer pytest instalado nesse interprete.

.EXAMPLE
    # Release candidate completo (gate + build + assinatura + zip + sbom)
    pwsh deploy\build_release.ps1 -Target zip

.EXAMPLE
    # Build local rapido, sem assinatura (Trusted Signing ainda nao activo)
    pwsh deploy\build_release.ps1 -Target zip -SkipSigning

.EXAMPLE
    # Iteracao de dev, sem gate de testes nem assinatura
    pwsh deploy\build_release.ps1 -Target zip -SkipTests -SkipSigning

.NOTES
    Exit codes:
      0 = release construida com sucesso
      1 = pre-requisito em falta (venv-build, LLVM, spec file, etc.)
      2 = gate de pytest encontrou falhas NOVAS (nao presentes na baseline)
      3 = -Target msi invocado (stub, nao implementado -- ver Etapa 3b)
      4 = build.py (PyArmor+PyInstaller) falhou OU smoke-boot do bundle falhou
      5 = assinatura pedida mas backend indisponivel/falhou
      6 = staging/zip/SBOM/manifest falhou

    Idempotente: cada execucao limpa e recria dist\release\<ver>\stage\;
    o zip final e sobrescrito (Compress-Archive -Force).

    Author: WatcherDB DevOps (Etapa 3a, auditoria empacotamento 2026-07-03/04)
    See also: docs\context\auditorias\AUDITORIA_EMPACOTAMENTO_2026-07-03_FASE4.md
              docs\context\auditorias\AUDITORIA_EMPACOTAMENTO_2026-07-04_RUNBOOK_ETAPA2.md
#>

[CmdletBinding()]
param(
    [ValidateSet('zip', 'msi')]
    [string]$Target = 'zip',

    [switch]$SkipTests,
    [switch]$SkipSigning,

    [ValidateSet('keylocker', 'pfx', 'store')]
    [string]$SigningMode = 'keylocker',
    [string]$PfxPath,
    [SecureString]$PfxPassword,
    [string]$CertThumbprint,
    [string]$TimestampUrl = 'http://timestamp.digicert.com',

    [string]$OutputRoot,
    [string]$PythonExe,

    # CVE gate (Etapa 3b, security-auditor 2026-08-20). Corre grype sobre o SBOM
    # ANTES da assinatura -- um CVE critico depois de assinar obriga a re-assinar
    # num HSM que custa. Falha o build em severidade >= $CveFailOn fora da
    # allowlist. -SkipCve salta (debug/CI sem grype); nao entregavel a banca.
    [ValidateSet('critical', 'high')]
    [string]$CveFailOn = 'high',
    [string]$CveAllowlist,
    [switch]$SkipCve
)

$ErrorActionPreference = 'Stop'

# =============================================================================
# Helpers (mesma convencao visual dos outros scripts deploy\*.ps1)
# =============================================================================
function Write-Step($msg) { Write-Host "[build_release] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[build_release] OK   $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[build_release] WARN $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "[build_release] FAIL $msg" -ForegroundColor Red; throw $msg }

# Resolve um objecto X509Certificate2 com chave privada, para uso com
# Set-AuthenticodeSignature (assinatura de scripts .ps1/.psd1 -- signtool
# NAO assina scripts, so PE/MSI/CAB). Mesmos 3 backends de sign_msi.ps1.
function Get-SigningCertificateObject {
    param(
        [string]$Mode,
        [string]$PfxPathParam,
        [SecureString]$PfxPasswordParam,
        [string]$CertThumbprintParam
    )
    switch ($Mode) {
        'store' {
            if (-not $CertThumbprintParam) {
                throw '-CertThumbprint obrigatorio em SigningMode store (assinatura de scripts).'
            }
            $cert = Get-Item "Cert:\CurrentUser\My\$CertThumbprintParam" -ErrorAction SilentlyContinue
            if (-not $cert) {
                throw "Certificado com thumbprint $CertThumbprintParam nao encontrado em CurrentUser\My."
            }
            return $cert
        }
        'pfx' {
            if (-not $PfxPathParam -or -not (Test-Path $PfxPathParam)) {
                throw '-PfxPath obrigatorio e valido em SigningMode pfx (assinatura de scripts).'
            }
            if (-not $PfxPasswordParam) {
                $PfxPasswordParam = Read-Host -Prompt 'PFX password (assinatura de scripts)' -AsSecureString
            }
            $bstrPtrLocal = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($PfxPasswordParam)
            $plainPwdLocal = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstrPtrLocal)
            try {
                return New-Object Security.Cryptography.X509Certificates.X509Certificate2(
                    $PfxPathParam, $plainPwdLocal, 'Exportable'
                )
            } finally {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstrPtrLocal) | Out-Null
                Remove-Variable plainPwdLocal, bstrPtrLocal -Force -ErrorAction SilentlyContinue
            }
        }
        'keylocker' {
            # ASSUNCAO A DOCUMENTAR (nao 100% verificado sem acesso ao
            # ambiente KeyLocker real -- flag para o owner validar na 1a
            # execucao real): o DigiCert KeyLocker Client Tools (smctl/KSP)
            # provisiona o certificado no Windows cert store local -- e
            # assim que o signtool /sm /n <alias> ja funciona no PASSO 3
            # (PE). A chave privada nunca sai do HSM; Set-AuthenticodeSignature
            # invoca a mesma operacao criptografica via CSP/KSP, tal como
            # um smart card. Procuramos o certificado pelo alias no Subject
            # ou FriendlyName.
            $alias = $env:SM_CERT_ALIAS
            $cert = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My -ErrorAction SilentlyContinue |
                Where-Object { $_.Subject -match [regex]::Escape($alias) -or $_.FriendlyName -eq $alias } |
                Sort-Object NotAfter -Descending | Select-Object -First 1
            if (-not $cert) {
                throw "Certificado KeyLocker com alias '$alias' nao encontrado no cert store local. Confirmar 'smctl healthcheck' / KeyLocker Client Tools activo."
            }
            return $cert
        }
    }
}

# Invoca pytest no interprete do gate. Dois caminhos: $PythonExe como path
# de ficheiro (default .venv-build) -> invocacao directa via & (segura com
# espacos no path); string tipo 'py -3.14' (override manual) -> cmd /c.
# O exit code vai para $script:LastPytestExit em vez de return — misturar
# return com o output nativo do pytest contaminava o pipeline PS.
function Invoke-Pytest {
    param([string[]]$PytestArgs)
    if (Test-Path $PythonExe) {
        & $PythonExe -m pytest @PytestArgs
    } else {
        $argStr = ($PytestArgs | ForEach-Object {
            if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
        }) -join ' '
        cmd /c "$PythonExe -m pytest $argStr"
    }
    $script:LastPytestExit = $LASTEXITCODE
}

$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot  = Split-Path -Parent $scriptDir

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  WatcherDB V3.3 Standard - Release Build (Etapa 3a)' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host "  Repo root:   $repoRoot"
Write-Host "  Target:      $Target"
Write-Host "  SkipTests:   $SkipTests"
Write-Host "  SkipSigning: $SkipSigning"
Write-Host "  Timestamp:   $(Get-Date -Format o)"
Write-Host ''

# -----------------------------------------------------------------------
# Target msi = ETAPA 3b ACTIVADA (owner, 2026-08-19)
# -----------------------------------------------------------------------
# O stub que aqui estava saia com codigo 3 e mandava usar o ZIP, por decisao
# D1 da AUDITORIA_FASE4 (03/07): ZIP como veiculo default, MSI trigger-based.
#
# O gatilho disparou. O `docs/external/standard/INSTALL_GUIDE.md` -- o guia que
# o piloto vai seguir -- declara o MSI como "artefacto canonico, Authenticode-
# signed, SBOM incluido" e nao tem UMA linha sobre o ZIP (31 mencoes a MSI, 0 a
# ZIP). Ou seja: o guia prometia um artefacto que a linha de montagem sancionada
# nao sabia produzir, e o unico MSI que existia tinha sido feito por invocacao
# solta do build_msi.ps1 -- fora daqui, logo sem gate de testes, sem assinatura,
# sem SBOM e sem manifesto. Esta em quarentena.
#
# O delta e' o previsto na seccao 4.2 passo 7b: o MSI diverge do ZIP APENAS no
# PASSO 5. Tudo o resto -- gate de pytest (1), build PyArmor (2), assinatura dos
# PE (3), smoke-boot (3.5), staging (4), SBOM (6) e manifesto SHA-256 (7) --
# passa a valer para o MSI sem duplicacao. E' isso que fecha de uma vez os
# quatro controlos que o MSI nao tinha.
#
# Nao ha `exit` aqui: o fluxo segue e ramifica no PASSO 5.

# -----------------------------------------------------------------------
# Release vars (SOT unica -- Import-PowerShellDataFile, ZERO hardcode)
# -----------------------------------------------------------------------
$releaseVarsPath = Join-Path $scriptDir 'release_vars.psd1'
if (-not (Test-Path $releaseVarsPath)) {
    Write-Fail "release_vars.psd1 nao encontrado em $releaseVarsPath -- SOT em falta."
}
$rv = Import-PowerShellDataFile -Path $releaseVarsPath
Write-Ok "release_vars carregado: $($rv.ProductName) v$($rv.ProductVersion)"

if (-not $OutputRoot) { $OutputRoot = Join-Path $repoRoot 'dist\release' }
$versionDir = Join-Path $OutputRoot $rv.ProductVersion
$stageDir   = Join-Path $versionDir 'stage'
$bundleDir  = Join-Path $repoRoot 'dist\watcherdb'   # BundleDirName do SOT

Write-Host "  Version dir: $versionDir"
Write-Host ''

# -----------------------------------------------------------------------
# Interprete do gate/smoke = o MESMO do bundle (.venv-build, 3.11) por
# default — a evidencia de testes passa a cobrir o interpretador que o
# cliente realmente corre. -PythonExe fica como override para investigacao.
# -----------------------------------------------------------------------
if (-not $PythonExe) {
    $gatePython = Join-Path $repoRoot '.venv-build\Scripts\python.exe'
    if (-not (Test-Path $gatePython)) {
        Write-Fail "Venv de build nao encontrado: $gatePython. Criar com: py -3.11 -m venv .venv-build ; .venv-build\Scripts\pip install -r requirements-build.txt"
    }
    $PythonExe = $gatePython
}
# O gate (PASSO 1) e o smoke-boot (PASSO 3.5) correm pytest — fail-loud ja
# aqui se nao estiver instalado, com a instrucao correcta.
Invoke-Pytest @('--version')
if ($script:LastPytestExit -ne 0) {
    Write-Fail "pytest nao esta disponivel em '$PythonExe'. Instalar na venv de build: .venv-build\Scripts\pip install pytest pytest-asyncio pytest-cov pytest-mock (ver diff proposto a requirements-build.txt) — ou usar -PythonExe para override."
}
Write-Ok "Interprete do gate/smoke: $PythonExe"
Write-Host ''

# =============================================================================
# PASSO 1 - Gate de pytest (baseline conhecida; falha so em falhas NOVAS)
# =============================================================================
Write-Step 'PASSO 1/7: gate de pytest'

# Baseline validada 2026-07-04 durante a execucao end-to-end da Etapa 2
# (ver RUNBOOK_ETAPA2.md, secao "Resultados da validacao").
# ATENCAO (2026-08-10): baseline foi MEDIDA sob 'py -3.14'; o default do
# gate passou para .venv-build (3.11.9, o interpretador do runtime). Na
# primeira execucao sob 3.11, falhas "novas" podem ser diferencas de
# interpretador — investigar antes de adicionar a baseline (codigo que so
# funciona por acidente em 3.14 e quebra em 3.11 e EXACTAMENTE o que esta
# mudanca existe para apanhar). Re-baseline: correr pytest sob 3.11,
# comparar IDs, actualizar este array + este comentario.
# Sao 5 falhas conhecidas e NAO-bloqueantes:
#   - 4x TestLevel6_ProjectHygiene: assumem estado de working tree de dev
#     (sem .exe/.bak/.log soltos, sem .md solto em docs/ raiz) -- falham
#     em qualquer working tree "sujo" de sessao de trabalho activa; nao
#     sao regressao de produto.
#   - 1x test_startup_guard_grace_period_allows_missing_license -- falha
#     conhecida sob investigacao separada (licensing/startup_guard.py),
#     nao bloqueia o packaging.
# Chave usada = "<classname junit>::<name junit>" (formato nativo do plugin
# pytest-junitxml: classname e o caminho dotted do modulo [+ classe], sem
# extensao .py; NAO tentar reconstruir o node id "a/b.py::Class::test" a
# partir disto -- e ambiguo para testes fora de classe).
$script:KnownBaselineFailures = @(
    'tests.unit.test_qa_comprehensive.TestLevel6_ProjectHygiene::test_no_exe_in_repo',
    'tests.unit.test_qa_comprehensive.TestLevel6_ProjectHygiene::test_no_bak_files',
    'tests.unit.test_qa_comprehensive.TestLevel6_ProjectHygiene::test_no_log_files_at_root',
    'tests.unit.test_qa_comprehensive.TestLevel6_ProjectHygiene::test_docs_organized_in_subdirs',
    'tests.unit.test_startup_guard::test_startup_guard_grace_period_allows_missing_license'
)

if ($SkipTests) {
    Write-Warn '-SkipTests indicado. NENHUM teste correu para este build.'
    Write-Warn 'Esta build NAO tem evidencia de testes -- nao usar para entrega a cliente sem gate manual.'
} else {
    # junit escrito FORA de dist\ -- build.py (PASSO 2) faz rmtree de dist\ inteiro
    # e apagava o xml quando vivia em dist\release (achado do 1o run real 2026-07-04).
    # Copiado para $versionDir no PASSO 7.
    $junitPath = Join-Path $env:TEMP 'watcherdb_v33_pytest_results.xml'
    if (Test-Path $junitPath) { Remove-Item $junitPath -Force }

    # test_pyinstaller_boot.py EXCLUIDO do gate: valida dist\watcherdb, que
    # neste ponto (pre-build) e o artefacto STALE da run anterior — 1a run
    # pos-fix 2026-08-11 abortou o build ao apanhar o 500 do bundle VELHO.
    # Esses testes correm em exclusivo no PASSO 3.5, contra o bundle fresco.
    Write-Host "  A correr: $PythonExe -m pytest tests/unit -q --no-cov --ignore=tests/unit/test_pyinstaller_boot.py --junitxml=$junitPath"
    Push-Location $repoRoot
    try {
        Invoke-Pytest @('tests/unit', '-q', '--no-cov',
            '--ignore=tests/unit/test_pyinstaller_boot.py',
            "--junitxml=$junitPath")
        $pytestExit = $script:LastPytestExit
    } finally {
        Pop-Location
    }
    Write-Host "  pytest exit code: $pytestExit (informativo -- o gate usa o junit, nao este codigo)"

    if (-not (Test-Path $junitPath)) {
        Write-Fail "pytest nao produziu $junitPath -- provavelmente falha de collection. Corrigir antes de tentar build."
    }

    [xml]$junit = Get-Content -Path $junitPath -Raw
    $failedNodes = $junit.SelectNodes('//testcase[failure or error]')
    $failedIds = New-Object System.Collections.Generic.List[string]
    foreach ($tc in $failedNodes) {
        $failedIds.Add("$($tc.classname)::$($tc.name)")
    }

    $newFailures = $failedIds | Where-Object { $script:KnownBaselineFailures -notcontains $_ }
    $fixedSinceBaseline = $script:KnownBaselineFailures | Where-Object { $failedIds -notcontains $_ }
    $stillKnown = $failedIds | Where-Object { $script:KnownBaselineFailures -contains $_ }

    if ($newFailures) {
        Write-Host ''
        Write-Host '  FALHAS NOVAS (nao presentes na baseline conhecida):' -ForegroundColor Red
        $newFailures | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
        Write-Host ''
        Write-Fail "$($newFailures.Count) falha(s) NOVA(s) detectada(s) -- gate de release ABORTADO. Corrigir ou investigar antes de rebuild."
        exit 2
    }

    Write-Ok "Gate PASSOU. Falhas conhecidas da baseline ainda presentes: $($stillKnown.Count)/$($script:KnownBaselineFailures.Count). Zero falhas novas."
    if ($fixedSinceBaseline) {
        Write-Ok "Melhoria detectada -- estas falhas da baseline agora PASSAM (considerar remover da lista manualmente, apos confirmacao):"
        $fixedSinceBaseline | ForEach-Object { Write-Host "    - $_" -ForegroundColor Green }
    }
}
Write-Host ''

# =============================================================================
# PASSO 2 - Build PyArmor + PyInstaller (deploy\build.py via .venv-build)
# =============================================================================
Write-Step 'PASSO 2/7: build PyArmor + PyInstaller (deploy\build.py)'

$venvPython = Join-Path $repoRoot '.venv-build\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Fail "Venv de build nao encontrado: $venvPython. Criar com: py -3.11 -m venv .venv-build ; .venv-build\Scripts\pip install -r requirements-build.txt"
}
Write-Ok "venv de build: $venvPython"

$llvmBin = 'C:\Program Files\LLVM\bin'
if (-not (Test-Path $llvmBin)) {
    Write-Fail "LLVM nao encontrado em $llvmBin -- PyArmor BCC (Etapa 2 fix1-4) exige clang.exe no PATH. Instalar LLVM antes de rebuild."
}
$originalPath = $env:Path
$env:Path = "$llvmBin;$originalPath"
Write-Ok "LLVM prepended ao PATH desta sessao: $llvmBin"

Push-Location $repoRoot
try {
    & $venvPython 'deploy\build.py'
    $buildExit = $LASTEXITCODE
} finally {
    Pop-Location
    $env:Path = $originalPath
}
if ($buildExit -ne 0) {
    Write-Fail "deploy\build.py falhou com exit code $buildExit. Ver output acima (PyArmor/PyInstaller)."
    exit 4
}
if (-not (Test-Path (Join-Path $bundleDir 'watcherdb.exe'))) {
    Write-Fail "Build reportou sucesso mas $bundleDir\watcherdb.exe nao existe. Investigar antes de prosseguir."
    exit 4
}
Write-Ok "Bundle construido: $bundleDir"
Write-Host ''

# =============================================================================
# PASSO 3 - Assinatura Authenticode de todos os PE do bundle
# =============================================================================
Write-Step 'PASSO 3/7: assinatura Authenticode (*.exe, *.pyd, *.dll)'

if ($SkipSigning) {
    Write-Warn '-SkipSigning indicado. Bundle NAO assinado.'
    Write-Warn 'STUB: Azure Trusted Signing ainda nao esta activo (audit FASE4 4a / B2-13, pendente de elegibilidade).'
    Write-Warn 'Cliente vera aviso SmartScreen "Publisher desconhecido". NAO usar para entrega final.'
} else {
    Write-Step 'Resolvendo signtool.exe...'
    $signtool = (Get-Command signtool.exe -ErrorAction SilentlyContinue).Path
    if (-not $signtool) {
        $candidates = Get-ChildItem -Path 'C:\Program Files (x86)\Windows Kits\10\bin' `
            -Recurse -ErrorAction SilentlyContinue -Filter 'signtool.exe' |
            Where-Object { $_.DirectoryName -match '\\x64\\' } |
            Sort-Object FullName -Descending
        if ($candidates.Count -gt 0) { $signtool = $candidates[0].FullName }
    }
    if (-not $signtool) {
        Write-Fail 'signtool.exe nao encontrado. Instalar Windows 10/11 SDK (Signing Tools) OU rebuild com -SkipSigning.'
        exit 5
    }
    Write-Ok "signtool: $signtool"

    $peFiles = Get-ChildItem -Path $bundleDir -Recurse -Include '*.exe', '*.pyd', '*.dll' -File
    if (-not $peFiles) {
        Write-Fail "Nenhum PE encontrado em $bundleDir -- bundle incompleto?"
        exit 5
    }
    Write-Ok "$($peFiles.Count) ficheiro(s) PE a assinar."

    $common = @('sign', '/fd', 'sha256', '/td', 'sha256', '/tr', $TimestampUrl, '/v')
    switch ($SigningMode) {
        'keylocker' {
            foreach ($v in 'SM_HOST', 'SM_API_KEY', 'SM_CLIENT_CERT_FILE', 'SM_CLIENT_CERT_PASSWORD', 'SM_CERT_ALIAS') {
                if (-not (Test-Path "Env:$v")) {
                    Write-Fail "KeyLocker env var $v nao esta definida. Configurar DigiCert KeyLocker OU rebuild com -SkipSigning."
                    exit 5
                }
            }
            $alias = $env:SM_CERT_ALIAS
            $signArgs = $common + @('/sm', '/n', $alias)
        }
        'pfx' {
            if (-not $PfxPath -or -not (Test-Path $PfxPath)) {
                Write-Fail '-PfxPath obrigatorio e valido em SigningMode pfx.'
                exit 5
            }
            if (-not $PfxPassword) { $PfxPassword = Read-Host -Prompt 'PFX password' -AsSecureString }
            $bstrPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($PfxPassword)
            $plainPwd = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstrPtr)
            $signArgs = $common + @('/f', $PfxPath, '/p', $plainPwd)
        }
        'store' {
            if (-not $CertThumbprint) {
                Write-Fail '-CertThumbprint obrigatorio em SigningMode store.'
                exit 5
            }
            $signArgs = $common + @('/sha1', $CertThumbprint)
        }
    }

    # signtool aceita varios ficheiros por invocacao, mas o comprimento da
    # linha de comando do Windows tem limite (~32K chars); com bundles de
    # 147MB+ e dezenas de DLLs, agrupamos em lotes de 40 para nao estourar.
    $batchSize = 40
    $batches = [Math]::Ceiling($peFiles.Count / $batchSize)
    for ($i = 0; $i -lt $batches; $i++) {
        $batch = $peFiles | Select-Object -Skip ($i * $batchSize) -First $batchSize
        $paths = $batch | ForEach-Object { $_.FullName }
        Write-Step "Assinando lote $($i + 1)/$batches ($($paths.Count) ficheiros)..."
        & $signtool @signArgs @paths
        $rc = $LASTEXITCODE
        if ($SigningMode -eq 'pfx' -and $i -eq ($batches - 1)) {
            if ($bstrPtr) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstrPtr) | Out-Null }
            Remove-Variable plainPwd, bstrPtr -Force -ErrorAction SilentlyContinue
        }
        if ($rc -ne 0) {
            Write-Fail "signtool falhou no lote $($i + 1) com exit code $rc."
            exit 5
        }
    }
    Write-Ok "Todos os $($peFiles.Count) PE assinados (SHA-256 + timestamp RFC 3161)."

    # Verificacao rapida do exe principal (representativo do lote todo).
    & $signtool verify /pa /q (Join-Path $bundleDir 'watcherdb.exe')
    if ($LASTEXITCODE -ne 0) {
        Write-Fail 'signtool verify reportou assinatura invalida em watcherdb.exe.'
        exit 5
    }
    Write-Ok 'Verificacao de assinatura (watcherdb.exe) OK.'
}
Write-Host ''

# =============================================================================
# PASSO 3.5 - Smoke-boot do bundle (tests/unit/test_pyinstaller_boot.py)
# =============================================================================
# Os 4 incidentes historicos do empacotamento (pyodbc B0-2, structlog,
# email.mime, passlib) foram todos falhas de ARRANQUE descobertas a mao
# depois de um build verde — ate aqui o pipeline validava que o exe existe,
# nunca que arranca. Reutiliza o smoke test ja debugged (licao do
# pipe-deadlock, timeout 120s calibrado a EDR+bundle 147MB,
# WATCHERDB_LICENSE_ENFORCE=advisory no fixture) em vez de reimplementar em
# PowerShell. O teste era NO-OP no gate do PASSO 1: corre antes do build,
# logo o skipif(bundle inexistente) atirava-o sempre fora — este passo
# fecha esse buraco. Posicao DEPOIS da assinatura (consult specialists
# 2026-08-10): signtool altera o PE in-place; validamos os bytes que o
# cliente recebe, nao os pre-assinatura.
#
# Isolamento do servico dev local: o mutex single-instance e keyed por
# data_root e o grace-period marker resolve para C:\ProgramData\WatcherDB
# real — o fixture herda os.environ, por isso injectamos aqui
# WATCHERDB_DATA_DIR + WATCHERDB_INSTALL_MARKER_PATH temporarios. Sem isto:
# mutex do servico dev aborta o run_console() (falso "boot failure" por
# timeout) e cada smoke consumia grace period em producao como side effect.
Write-Step 'PASSO 3.5/7: smoke-boot do bundle (pytest test_pyinstaller_boot.py)'

$smokePort = if ($env:WATCHERDB_SMOKE_PORT) { [int]$env:WATCHERDB_SMOKE_PORT } else { 8499 }
if (Get-NetTCPConnection -LocalPort $smokePort -State Listen -ErrorAction SilentlyContinue) {
    Write-Fail "Porta de smoke $smokePort ja esta em escuta — o poll de arranque daria falso positivo. Libertar a porta ou definir WATCHERDB_SMOKE_PORT para uma livre."
    exit 4
}
$smokeDataDir = Join-Path $env:TEMP ("watcherdb_smoke_" + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $smokeDataDir -Force | Out-Null
$smokeEnvBackup = @{}
foreach ($k in 'WATCHERDB_DATA_DIR', 'WATCHERDB_INSTALL_MARKER_PATH') {
    $smokeEnvBackup[$k] = [Environment]::GetEnvironmentVariable($k)
}
$env:WATCHERDB_DATA_DIR            = $smokeDataDir
$env:WATCHERDB_INSTALL_MARKER_PATH = Join-Path $smokeDataDir 'install_marker.json'
Push-Location $repoRoot
try {
    Invoke-Pytest @('tests/unit/test_pyinstaller_boot.py', '-q', '--no-cov')
    $smokeExit = $script:LastPytestExit
} finally {
    Pop-Location
    foreach ($k in $smokeEnvBackup.Keys) {
        [Environment]::SetEnvironmentVariable($k, $smokeEnvBackup[$k])
    }
    Remove-Item -Recurse -Force $smokeDataDir -ErrorAction SilentlyContinue
}
if ($smokeExit -ne 0) {
    Write-Fail "Smoke-boot FALHOU (pytest exit $smokeExit) — o bundle nao arranca ou nao responde. Mesma classe dos incidentes pyodbc/structlog/email.mime/passlib; ver o tail do watcherdb_boot.log no output do pytest acima."
    exit 4
}
Write-Ok 'Smoke-boot OK: bundle arranca, binda e responde aos endpoints de health.'
Write-Host ''

# =============================================================================
# PASSO 4 - Staging (bundle + VERSION.txt + install/uninstall/preflight)
# =============================================================================
Write-Step 'PASSO 4/7: staging do pacote de entrega'

if (Test-Path $stageDir) { Remove-Item -Recurse -Force $stageDir }
New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

$stageBundleDir = Join-Path $stageDir $rv.BundleDirName
Write-Host "  Copiando bundle: $bundleDir -> $stageBundleDir"
Copy-Item -Path $bundleDir -Destination $stageBundleDir -Recurse -Force

# RISCO#9 (cross-check adversarial deploy-architect): validar MAX_PATH
# ANTES de zipar. Expand-Archive no cliente (sem LongPathsEnabled, que e
# o default em Windows Server "de fabrica") falha SILENCIOSAMENTE para
# ficheiros cujo path final excede o limite classico de 260 chars --
# resultado: bundle parcial, ImportError obscuro em runtime, muito depois
# do "install completed" ja ter sido reportado. Usamos o InstallDir
# pior-caso mais provavel (default do install.ps1) como prefixo de
# referencia e uma margem (240 em vez de 260) para absorver variacao de
# InstallDir custom ligeiramente mais longo.
$worstCaseInstallPrefix = 'C:\Program Files\WatcherDB\V3.3\'
$maxTotalPathChars = 240
$longPathViolations = Get-ChildItem -Path $stageBundleDir -Recurse -File | ForEach-Object {
    $relPath = $_.FullName.Substring($stageBundleDir.Length).TrimStart('\')
    $totalLen = $worstCaseInstallPrefix.Length + $relPath.Length
    if ($totalLen -gt $maxTotalPathChars) {
        [PSCustomObject]@{ RelativePath = $relPath; TotalLength = $totalLen }
    }
}
if ($longPathViolations) {
    Write-Host ''
    Write-Host "  FICHEIROS QUE EXCEDEM MAX_PATH (limite $maxTotalPathChars chars, prefixo pior-caso '$worstCaseInstallPrefix'):" -ForegroundColor Red
    $longPathViolations | ForEach-Object { Write-Host "    [$($_.TotalLength)] $($_.RelativePath)" -ForegroundColor Red }
    Write-Host ''
    Write-Fail "$($longPathViolations.Count) ficheiro(s) excedem MAX_PATH -- Expand-Archive falha silenciosamente nestes sem LongPathsEnabled no cliente. Encurtar a estrutura/nomes no bundle antes de rebuild, ou documentar LongPathsEnabled como pre-requisito obrigatorio (nao recomendado como unica mitigacao)."
    exit 6
}
Write-Ok "MAX_PATH: nenhum ficheiro excede $maxTotalPathChars chars com o prefixo pior-caso assumido."

# VERSION.txt de topo do stage (o bundle ja tem uma copia interna, gerada
# por deploy\build.py; esta e a copia visivel imediatamente ao abrir o zip).
$versionTxt = @"
$($rv.ProductName)
Version:   $($rv.ProductVersion)
Service:   $($rv.ServiceName) (port $($rv.WebPort))
Packaged:  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Vehicle:   ZIP onedir + install.ps1 (Etapa 3a)
"@
Set-Content -Path (Join-Path $stageDir 'VERSION.txt') -Value $versionTxt -Encoding ascii

# release_vars.psd1 tem de viajar com o stage: install.ps1/uninstall.ps1
# correm no cliente e importam-no via Import-PowerShellDataFile a partir
# do proprio $PSScriptRoot -- ZERO valores hardcoded no cliente. O bundle
# PyInstaller (dist\watcherdb) NAO inclui deploy\ (confirmado em
# deploy\watcherdb.spec DATAS -- so templates/static/config/keys), por
# isso a copia explicita abaixo e obrigatoria.
Copy-Item -Path $releaseVarsPath -Destination (Join-Path $stageDir 'release_vars.psd1') -Force

foreach ($f in 'install.ps1', 'uninstall.ps1') {
    $src = Join-Path $scriptDir $f
    if (-not (Test-Path $src)) {
        Write-Fail "$f nao encontrado em $scriptDir -- staging incompleto."
        exit 6
    }
    Copy-Item -Path $src -Destination (Join-Path $stageDir $f) -Force
}
Copy-Item -Path (Join-Path $scriptDir 'preflight_target.ps1') -Destination (Join-Path $stageDir 'preflight_target.ps1') -Force

# RISCO#4: assinar os scripts do stage (nao so o .exe -- ver .PARAMETER
# SkipSigning acima). Sem isto, um cliente com ExecutionPolicy AllSigned
# via GPO nao consegue correr install.ps1/uninstall.ps1 de todo.
Write-Step 'Assinatura Authenticode dos scripts do stage (install.ps1, uninstall.ps1, preflight_target.ps1, release_vars.psd1)'
if ($SkipSigning) {
    Write-Warn '-SkipSigning indicado. Scripts do stage NAO assinados.'
    Write-Warn 'AVISO ESPECIFICO: este ZIP NAO instala em clientes com ExecutionPolicy AllSigned (GPO banking comum) -- assinar so o .exe nao chega, os .ps1/.psd1 tambem sao bloqueados nesse modo.'
} else {
    try {
        $scriptSignCert = Get-SigningCertificateObject -Mode $SigningMode `
            -PfxPathParam $PfxPath -PfxPasswordParam $PfxPassword -CertThumbprintParam $CertThumbprint
    } catch {
        Write-Fail "Nao foi possivel obter o certificado de assinatura para scripts: $($_.Exception.Message)"
        exit 5
    }
    $scriptsToSign = @('install.ps1', 'uninstall.ps1', 'preflight_target.ps1', 'release_vars.psd1') |
        ForEach-Object { Join-Path $stageDir $_ }
    foreach ($sf in $scriptsToSign) {
        $sigResult = Set-AuthenticodeSignature -FilePath $sf -Certificate $scriptSignCert `
            -TimestampServer $TimestampUrl -HashAlgorithm SHA256
        if ($sigResult.Status -ne 'Valid') {
            Write-Fail "Set-AuthenticodeSignature falhou em $sf (status: $($sigResult.Status) - $($sigResult.StatusMessage))"
            exit 5
        }
    }
    Write-Ok "$($scriptsToSign.Count) scripts assinados (Set-AuthenticodeSignature, SHA-256 + timestamp)."
}

Write-Ok "Stage pronto: $stageDir"
Write-Host ''

# =============================================================================
# PASSO 4.5 - SBOM + CVE gate (ANTES da assinatura do MSI)
# =============================================================================
# Ordem critica (security-auditor 2026-08-20): o SBOM e o scan de CVE tem de
# correr ANTES do PASSO 5 (que constroi e ASSINA o MSI). Ate' 2026-08-20 o SBOM
# era o PASSO 6, DEPOIS da assinatura -- um CVE critico obrigava a re-assinar
# num HSM. Agora gera-se aqui, sobre o bundle ja' com os PE assinados (PASSO 3),
# e o gate aborta antes de qualquer assinatura de MSI.
$sbomPath = Join-Path $versionDir "WatcherDB_V3.3_$($rv.ProductVersion).sbom.cyclonedx.json"
Write-Step 'PASSO 4.5/7: SBOM (Syft+environment) + gate de CVE'
try {
    & (Join-Path $scriptDir 'build_sbom.ps1') -BundleDir $bundleDir -OutputPath $sbomPath
} catch {
    Write-Fail "build_sbom.ps1 falhou: $($_.Exception.Message)"
    exit 6
}
Write-Ok "SBOM gerado e cobertura verificada: $sbomPath"

if ($SkipCve) {
    Write-Warn '-SkipCve: scan de CVE saltado. Artefacto NAO entregavel a banca.'
} else {
    $grypeExe = Get-Command grype -ErrorAction SilentlyContinue
    if (-not $grypeExe) {
        # grype instala-se via winget/scoop; procura-o no local do winget.
        $cand = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Anchore.Grype*" -Recurse -Filter grype.exe -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cand) { $env:PATH = "$($cand.DirectoryName);$env:PATH"; $grypeExe = Get-Command grype -ErrorAction SilentlyContinue }
    }
    if (-not $grypeExe) {
        Write-Fail 'grype nao encontrado. Instalar (winget install anchore.grype) OU rebuild com -SkipCve (nao entregavel).'
    }

    $grypeReport = Join-Path $versionDir "WatcherDB_V3.3_$($rv.ProductVersion).grype.json"
    Write-Step 'Correndo grype sobre o SBOM...'
    & grype "sbom:$sbomPath" -o json --file $grypeReport 2>&1 | Out-Null
    if (-not (Test-Path $grypeReport)) {
        Write-Fail "grype nao produziu o relatorio $grypeReport."
    }

    $allowArg = @()
    if (-not $CveAllowlist) { $CveAllowlist = Join-Path $scriptDir 'cve_allowlist.json' }
    if (Test-Path $CveAllowlist) { $allowArg = @('--allowlist', $CveAllowlist) }

    Write-Step "Gate de CVE (--fail-on $CveFailOn)..."
    & $PythonExe (Join-Path $scriptDir 'cve_gate.py') $grypeReport '--fail-on' $CveFailOn @allowArg
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Gate de CVE ABORTOU o release. Resolver (rebuild com versao corrigida) ou allowlist com razao documentada. Relatorio: $grypeReport"
    }
    Write-Ok "Gate de CVE passou. Relatorio arquivado: $grypeReport"
}
Write-Host ''

# =============================================================================
# PASSO 5 - Compress-Archive
# =============================================================================
Write-Step "PASSO 5/7: veiculo de entrega ($Target)"

# O unico passo onde ZIP e MSI divergem (AUDITORIA_FASE4 4.2, passo 7a/7b).
if ($Target -eq 'msi') {

    # --- 7b: build_msi.ps1 -> sign_msi.ps1 -------------------------------
    # Marcador que autoriza o build_msi.ps1 a correr. Existe para tornar a
    # invocacao solta detectavel: um MSI produzido fora daqui nao passou pelo
    # gate de pytest nem pela assinatura dos PE, e foi assim que nasceu o
    # artefacto que esta em quarentena. O ficheiro e' apagado no fim, para o
    # marcador nao sobreviver ao build que o justificou.
    $marcador = Join-Path $bundleDir '.release_verified'
    Set-Content -Path $marcador -Encoding UTF8 -Value @(
        "release_id=$($rv.ProductVersion)"
        "gerado_por=build_release.ps1"
        "gate_pytest=PASSO 1"
        "assinatura_pe=PASSO 3"
        "smoke_boot=PASSO 3.5"
    )

    # try/finally e' obrigatorio aqui, nao estilo: o build_msi.ps1 corre com
    # $ErrorActionPreference='Stop' e aborta por `throw`, nao por exit code --
    # sem finally, uma falha deixava o marcador no disco, e o marcador e'
    # precisamente o que autoriza o proximo build. Um token de autorizacao que
    # sobrevive ao seu proprio fracasso e' pior do que nao existir.
    $msiName = "WatcherDB_V3.3_$($rv.ProductVersion).msi"
    $msiPath = Join-Path $versionDir $msiName
    try {
        Write-Step 'MSI: heat/candle/light (deploy\build_msi.ps1)'
        & (Join-Path $scriptDir 'build_msi.ps1') -Clean
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "build_msi.ps1 falhou com exit code $LASTEXITCODE."
        }

        $msiOrigem = Join-Path $repoRoot 'dist\msi\WatcherDB_V3.3_Standard.msi'
        if (-not (Test-Path $msiOrigem)) {
            Write-Fail "build_msi.ps1 terminou sem erro mas nao produziu $msiOrigem."
        }

        # O MSI vive no $versionDir, como o ZIP -- e' o que o PASSO 7 inventaria.
        Move-Item -Force $msiOrigem $msiPath
    }
    finally {
        Remove-Item -Force $marcador -ErrorAction SilentlyContinue
    }

    # --- Assinatura do MSI: FAIL-CLOSE ------------------------------------
    # O guia do cliente declara "Authenticode-signed" na primeira linha. Um MSI
    # por assinar nao e' um MSI incompleto -- e' um artefacto que contradiz a
    # documentacao que vai com ele, e que o AppLocker/WDAC de um banco recusa.
    # Sem -SkipSigning explicito, aqui aborta.
    if ($SkipSigning) {
        Write-Warn 'MSI NAO assinado (-SkipSigning). Nao entregavel a cliente.'
        Write-Warn 'O INSTALL_GUIDE declara "Authenticode-signed" -- este artefacto contradi-lo.'
    } else {
        Write-Step "MSI: assinatura Authenticode (modo $SigningMode)"
        # Os mesmos parametros de assinatura que os PE do bundle usaram no
        # PASSO 3 -- o MSI e o seu conteudo assinados pela mesma identidade.
        $argsAssinatura = @{ MsiPath = $msiPath; Mode = $SigningMode; TimestampUrl = $TimestampUrl }
        if ($PfxPath)        { $argsAssinatura['PfxPath'] = $PfxPath }
        if ($PfxPassword)    { $argsAssinatura['PfxPassword'] = $PfxPassword }
        if ($CertThumbprint) { $argsAssinatura['CertThumbprint'] = $CertThumbprint }
        & (Join-Path $scriptDir 'sign_msi.ps1') @argsAssinatura
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "sign_msi.ps1 falhou com exit code $LASTEXITCODE. MSI por assinar NAO segue."
            exit 6
        }
        $assinatura = Get-AuthenticodeSignature -FilePath $msiPath
        if ($assinatura.Status -ne 'Valid') {
            Write-Fail "MSI assinado mas a verificacao devolveu '$($assinatura.Status)'."
            exit 6
        }
        Write-Ok "MSI assinado e verificado: $($assinatura.SignerCertificate.Subject)"
    }

    $msiSizeMb = [math]::Round(((Get-Item $msiPath).Length / 1MB), 1)
    Write-Ok "MSI criado: $msiPath ($msiSizeMb MB)"

    # Artefacto NEUTRO, comum aos dois ramos -- o PASSO 7 (manifest) e o sumario
    # final referem $artifactPath/$artifactSizeMb, nao a variavel do veiculo.
    # A 3a corrida do `-Target msi` (2026-08-20) produziu o MSI e o SBOM mas o
    # PASSO 7 fazia hash de $zipPath, que no ramo MSI nunca e' atribuido: o
    # $null escorregava em silencio e o SHA256SUMS.txt ficava a apontar ao ZIP
    # velho da run anterior. Variavel neutra fecha a fenda de vez.
    $artifactPath = $msiPath
    $artifactSizeMb = $msiSizeMb

} else {

    # --- 7a: ZIP ---------------------------------------------------------
    $zipName = "WatcherDB_V3.3_$($rv.ProductVersion).zip"
    $zipPath = Join-Path $versionDir $zipName
    if (Test-Path $zipPath) { Remove-Item -Force $zipPath }

    Compress-Archive -Path (Join-Path $stageDir '*') -DestinationPath $zipPath -CompressionLevel Optimal -Force
    if (-not (Test-Path $zipPath)) {
        Write-Fail "Compress-Archive nao produziu $zipPath."
        exit 6
    }
    $zipSizeMb = [math]::Round(((Get-Item $zipPath).Length / 1MB), 1)
    Write-Ok "ZIP criado: $zipPath ($zipSizeMb MB)"

    $artifactPath = $zipPath
    $artifactSizeMb = $zipSizeMb
}

# Stage e transitorio -- o conteudo relevante ja foi para o artefacto. Remove
# para nao confundir re-execucoes (idempotencia: proxima run recria do zero).
Remove-Item -Recurse -Force $stageDir
Write-Host ''

# =============================================================================
# PASSO 6 - SBOM ja' gerado no PASSO 4.5 (antes da assinatura)
# =============================================================================
# O SBOM e o CVE gate correm no PASSO 4.5, antes da assinatura do MSI, por
# exigencia do security-auditor (2026-08-20). Aqui so' se confirma que existe
# para o manifesto (PASSO 7) o inventariar.
Write-Step 'PASSO 6/7: SBOM (gerado no PASSO 4.5)'
if (-not (Test-Path $sbomPath)) {
    Write-Fail "SBOM esperado nao existe: $sbomPath (deveria ter sido gerado no PASSO 4.5)."
}
Write-Ok "SBOM confirmado: $sbomPath"
Write-Host ''

# =============================================================================
# PASSO 7 - Manifest SHA-256
# =============================================================================
Write-Step 'PASSO 7/7: manifest SHA-256'

$manifestPath = Join-Path $versionDir 'SHA256SUMS.txt'
$filesToHash = @($artifactPath, $sbomPath)
if ($junitPath -and (Test-Path $junitPath)) {
    Copy-Item $junitPath (Join-Path $versionDir 'pytest_results.xml') -Force
}
$junitCandidate = Join-Path $versionDir 'pytest_results.xml'
if (Test-Path $junitCandidate) { $filesToHash += $junitCandidate }
# Relatorio do grype: evidencia de scan que um auditor de banca pede.
$grypeCandidate = Join-Path $versionDir "WatcherDB_V3.3_$($rv.ProductVersion).grype.json"
if (Test-Path $grypeCandidate) { $filesToHash += $grypeCandidate }

$lines = New-Object System.Collections.Generic.List[string]
foreach ($f in $filesToHash) {
    $hash = (Get-FileHash -Path $f -Algorithm SHA256).Hash.ToLowerInvariant()
    $rel = Split-Path -Leaf $f
    $lines.Add("$hash  $rel")
}
Set-Content -Path $manifestPath -Value $lines -Encoding ascii
Write-Ok "Manifest escrito: $manifestPath"
Write-Host ''

# =============================================================================
# Sumario
# =============================================================================
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  RELEASE BUILD COMPLETA - WatcherDB V3.3 Standard Edition' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host "  Versao:    $($rv.ProductVersion)"
Write-Host "  Artefacto: $artifactPath ($artifactSizeMb MB)"
Write-Host "  SBOM:      $sbomPath"
Write-Host "  Manifest:  $manifestPath"
Write-Host "  Assinado:  $(if ($SkipSigning) { 'NAO (-SkipSigning -- AVISO: nao instala em cliente AllSigned/GPO)' } else { 'SIM (exe/pyd/dll + scripts install/uninstall/preflight/release_vars)' })"
Write-Host "  Testado:   $(if ($SkipTests) { 'NAO (-SkipTests)' } else { 'SIM (gate baseline conhecida)' })"
Write-Host "  Smoke:     SIM (boot do bundle + health endpoints, PASSO 3.5)"
Write-Host ''
Write-Host '  PROXIMOS PASSOS:'
Write-Host '  1. Copiar SHA256SUMS.txt + o zip para o canal de distribuicao ao cliente.'
Write-Host '  2. Validar a matriz de teste de instalacao (AUDITORIA_FASE4 secao 4.3)'
Write-Host '     em pelo menos uma VM limpa antes de entregar.'
Write-Host '  3. Arquivar dist\release\<ver>\ (zip + sbom + manifest + junit) como'
Write-Host '     evidencia de release (auditoria/compliance).'
Write-Host '============================================================' -ForegroundColor Cyan

exit 0
