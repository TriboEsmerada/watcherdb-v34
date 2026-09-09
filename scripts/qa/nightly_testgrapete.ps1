# TESTGRAPETE TG-1 - corrida noturna: council (afirma) e depois qa-externo (confere).
# PS7. Corre no host da 8434. Credenciais em .env.qa (fora do git) ou no ambiente.
#
# Uso manual:   pwsh scripts/qa/nightly_testgrapete.ps1
# Agendado:     ver docs/context/PLANO_TESTGRAPETE_2026-09-09.md (TG-2)
#
# .env.qa (raiz do repo, ignorado pelo git), uma variavel por linha:
#   WATCHERDB_BASE_URL=https://localhost:8434
#   WATCHERDB_QA_VIEWER_USER=qa_viewer
#   WATCHERDB_QA_VIEWER_PASS=...
#   WATCHERDB_QA_DBA_USER=qa_dba
#   WATCHERDB_QA_DBA_PASS=...
#   WATCHERDB_QA_ADMIN_USER=qa_admin
#   WATCHERDB_QA_ADMIN_PASS=...
#   WATCHERDB_QA_SERVER=<nome ou server_id de um TST>

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repo

$envFile = Join-Path $repo '.env.qa'
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"'), 'Process')
        }
    }
}
if (-not $env:WATCHERDB_BASE_URL) { $env:WATCHERDB_BASE_URL = 'https://localhost:8434' }

$dia = Get-Date -Format 'yyyy-MM-dd'
$bundle = Join-Path $repo "docs\qa\externo\$dia"
$council = Join-Path $bundle 'council'
$externo = Join-Path $bundle 'externo'
New-Item -ItemType Directory -Force -Path $council, $externo, (Join-Path $council 'cases') | Out-Null
$env:WATCHERDB_QA_BUNDLE = $council

$inicio = Get-Date
$head = (git rev-parse --short HEAD).Trim()

# ---- 1) Council: runner Playwright ----
$junit = Join-Path $council 'junit.xml'
& py -m pytest tests/e2e/test_smoke_modules_e2e.py -m e2e --no-cov -p no:cacheprovider -q `
    --screenshot only-on-failure --tracing retain-on-failure --output (Join-Path $council 'playwright') `
    --junitxml $junit 2>&1 | Tee-Object -FilePath (Join-Path $council 'pytest.log') | Select-Object -Last 15
$councilExit = $LASTEXITCODE

# ---- 2) qa-externo: scripts proprios, intocados, cada um no seu log ----
$extResults = @()
Get-ChildItem scripts/qa/runtime -Filter 'qa_ext_*.py' | Sort-Object Name | ForEach-Object {
    $log = Join-Path $externo ($_.BaseName + '.log')
    & py $_.FullName 2>&1 | Out-File -FilePath $log -Encoding utf8
    $extResults += [pscustomobject]@{ script = $_.Name; exit = $LASTEXITCODE }
}

# ---- 3) Sumario ----
$cases = Get-ChildItem (Join-Path $council 'cases') -Filter '*.json' -ErrorAction SilentlyContinue
$falhas = 0; $warns = 0
foreach ($c in $cases) {
    $j = Get-Content $c.FullName -Raw | ConvertFrom-Json
    if ($j.pageerrors.Count -or $j.console_errors.Count -or $j.http5xx.Count) { $falhas++ }
    if ($j.warn.Count) { $warns++ }
}
$dur = [int]((Get-Date) - $inicio).TotalSeconds
$linhas = @(
    "# TestGrapete $dia (HEAD $head, $($env:WATCHERDB_BASE_URL))",
    "",
    "| Metade | Resultado |",
    "|---|---|",
    "| Council | pytest exit $councilExit; $($cases.Count) casos; $falhas com erro; $warns com aviso de tempo |",
    "| qa-externo | $($extResults.Count) scripts; $(@($extResults | Where-Object exit -ne 0).Count) com exit != 0 |",
    "| Duracao | $dur s |",
    "",
    "## qa-externo por script",
    ""
) + ($extResults | ForEach-Object { "- $($_.script): exit $($_.exit)" })
$linhas | Set-Content -Path (Join-Path $bundle 'SUMMARY.md') -Encoding utf8

$logLine = "| $dia | $head | council exit $councilExit ($($cases.Count) casos, $falhas erro, $warns aviso) | externo $(@($extResults | Where-Object exit -ne 0).Count)/$($extResults.Count) com erro | $dur s |"
$nightly = Join-Path $repo 'docs\qa\externo\NIGHTLY_LOG.md'
if (-not (Test-Path $nightly)) {
    "# TestGrapete - corridas noturnas`n`n| Dia | HEAD | Council | qa-externo | Duracao |`n|---|---|---|---|---|" | Set-Content $nightly -Encoding utf8
}
Add-Content -Path $nightly -Value $logLine -Encoding utf8
# ---- 4) Painel (TG-1b): resultados do externo em JSON + index.html/board.html ----
$extResults | ConvertTo-Json -AsArray | Set-Content -Path (Join-Path $externo 'results.json') -Encoding utf8
if (Test-Path scripts/qa/testgrapete_board.py) { & py scripts/qa/testgrapete_board.py 2>&1 | Select-Object -Last 2 }

Write-Host $logLine
exit $councilExit
