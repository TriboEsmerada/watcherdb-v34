# TESTSUKITA TG-1 - corrida noturna: council (afirma) e depois qa-externo (confere).
# PS7. Corre no host da 8434. Credenciais em .env.qa (fora do git) ou no ambiente.
#
# Uso manual:   pwsh scripts/qa/nightly_testsukita.ps1
# Agendado:     ver docs/context/PLANO_TESTSUKITA_2026-09-09.md (TG-2)
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
#   # qa-externo (scripts/qa/runtime/qa_ext_*.py): conta unica + URL proprio
#   WATCHERDB_QA_USER=qa_viewer
#   WATCHERDB_QA_PASS=...
#   WATCHERDB_QA_ROLE=viewer
#   # WATCHERDB_QA_URL e' derivado de WATCHERDB_BASE_URL se faltar

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
# TG-1 PASSO 7: os scripts do qa-externo leem WATCHERDB_QA_URL (convencao deles, intocada)
if (-not $env:WATCHERDB_QA_URL) { $env:WATCHERDB_QA_URL = $env:WATCHERDB_BASE_URL }
if (-not (Test-Path $envFile)) { Write-Host "AVISO: $envFile nao existe; a usar so' o ambiente da shell (ver cabecalho deste script)." }

$dia = Get-Date -Format 'yyyy-MM-dd'
$bundle = Join-Path $repo "docs\qa\externo\$dia"
$council = Join-Path $bundle 'council'
$externo = Join-Path $bundle 'externo'
New-Item -ItemType Directory -Force -Path $council, $externo, (Join-Path $council 'cases') | Out-Null
# TG-1 PASSO 5: cada corrida comeca sem JSON de caso da anterior (na 2.a corrida o sumario
# contou os 5 casos da 1.a). Screenshots/traces ficam (so' existem em falha).
Get-ChildItem (Join-Path $council 'cases') -Filter '*.json' -ErrorAction SilentlyContinue | Remove-Item -Force
$env:WATCHERDB_QA_BUNDLE = $council

$inicio = Get-Date
$head = (git rev-parse --short HEAD).Trim()
# TESTSUKITA V1: janela do log do servico desta corrida (offset no inicio, delta no fim)
$svcLog = Join-Path $repo 'logs\service_stderr.log'
$svcOffset = if (Test-Path $svcLog) { (Get-Item $svcLog).Length } else { 0 }

# ---- 1) Council: runner Playwright ----
$junit = Join-Path $council 'junit.xml'
& py -m pytest tests/e2e/test_smoke_modules_e2e.py tests/e2e/test_semantic_e2e.py tests/e2e/test_interactions_e2e.py tests/e2e/test_api_smoke_e2e.py -m e2e --no-cov -p no:cacheprovider -q `
    --screenshot only-on-failure --tracing retain-on-failure --output (Join-Path $council 'playwright') `
    --junitxml $junit 2>&1 | Tee-Object -FilePath (Join-Path $council 'pytest.log') | Select-Object -Last 15
$councilExit = $LASTEXITCODE

# ---- 2) qa-externo: scripts proprios, intocados, cada um no seu log ----
# TG-1 PASSO 8: /api/auth/login aceita 5/min. O council gastou 2-3; os scripts do
# externo fazem 1 cada. Pausa entre as metades e entre scripts para nao ver 429.
Write-Host "pausa 65 s (rate limit do login) antes do qa-externo"
Start-Sleep -Seconds 65
$extResults = @()
# TG-1 PASSO 3: so' os scripts listados em scripts/qa/runtime/NIGHTLY.txt (um por linha;
# o qa-externo e' dono da lista). 4 dos 9 exigem argumentos de pauta e nao sao noturnos.
$lista = Join-Path $repo 'scripts\qa\runtime\NIGHTLY.txt'
$nomes = if (Test-Path $lista) { Get-Content $lista | Where-Object { $_ -and -not $_.StartsWith('#') } | ForEach-Object { $_.Trim() } } else { @() }
Get-ChildItem scripts/qa/runtime -Filter 'qa_ext_*.py' | Where-Object { $nomes -contains $_.Name } | Sort-Object Name | ForEach-Object {
    $log = Join-Path $externo ($_.BaseName + '.log')
    & py $_.FullName 2>&1 | Out-File -FilePath $log -Encoding utf8
    $extResults += [pscustomobject]@{ script = $_.Name; exit = $LASTEXITCODE }
    Start-Sleep -Seconds 15
}

# ---- 3) Sumario ----
$cases = Get-ChildItem (Join-Path $council 'cases') -Filter '*.json' -ErrorAction SilentlyContinue
# TG-1 PASSO 5: verde vazio nao e' verde. Sem casos medidos (todos saltados por falta de
# credenciais, ou coleccao vazia) o job falha com 2, mesmo que o pytest tenha devolvido 0.
$saltados = (Select-String -Path (Join-Path $council 'pytest.log') -Pattern 'SKIPPED \[(\d+)\]' -AllMatches -ErrorAction SilentlyContinue |
    ForEach-Object { $_.Matches } | ForEach-Object { [int]$_.Groups[1].Value } | Measure-Object -Sum).Sum
if (-not $saltados) { $saltados = 0 }
if (@($cases).Count -eq 0) {
    Write-Host "COUNCIL: nada medido ($saltados casos saltados). Preenche .env.qa (WATCHERDB_QA_VIEWER/DBA/ADMIN_USER+PASS)."
    if ($councilExit -eq 0) { $councilExit = 2 }
}
$falhas = 0; $warns = 0
foreach ($c in $cases) {
    $j = Get-Content $c.FullName -Raw | ConvertFrom-Json
    if ($j.pageerrors.Count -or $j.console_errors.Count -or $j.http5xx.Count) { $falhas++ }
    if ($j.warn.Count) { $warns++ }
}
$dur = [int]((Get-Date) - $inicio).TotalSeconds
$linhas = @(
    "# TestSukita $dia (HEAD $head, $($env:WATCHERDB_BASE_URL))",
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

$logLine = "| $dia | $head | council exit $councilExit ($(@($cases).Count) casos, $falhas erro, $warns aviso, $saltados saltados) | externo $(@($extResults | Where-Object exit -ne 0).Count)/$($extResults.Count) com erro | $dur s |"
$nightly = Join-Path $repo 'docs\qa\externo\NIGHTLY_LOG.md'
if (-not (Test-Path $nightly)) {
    "# TestSukita - corridas noturnas`n`n| Dia | HEAD | Council | qa-externo | Duracao |`n|---|---|---|---|---|" | Set-Content $nightly -Encoding utf8
}
Add-Content -Path $nightly -Value $logLine -Encoding utf8
# ---- 4) Painel (TG-1b): resultados do externo em JSON + index.html/board.html ----
$extResults | ConvertTo-Json -AsArray | Set-Content -Path (Join-Path $externo 'results.json') -Encoding utf8
# TESTSUKITA V1: janela do log do servico + ratchet (regressoes e hipoteses) antes do painel
try {
    if (Test-Path $svcLog) {
        $fs = [IO.FileStream]::new($svcLog, 'Open', 'Read', 'ReadWrite')
        $len = $fs.Length; $off = if ($len -ge $svcOffset) { $svcOffset } else { 0 }
        $fs.Seek($off, 'Begin') | Out-Null
        $buf = New-Object byte[] ($len - $off); $fs.Read($buf, 0, $buf.Length) | Out-Null; $fs.Close()
        [IO.File]::WriteAllBytes((Join-Path $council 'service_log_window.log'), $buf)
    }
} catch { Write-Host "janela do log nao copiada: $($_.Exception.Message)" }
if (Test-Path scripts/qa/testsukita_ratchet.py) { & py scripts/qa/testsukita_ratchet.py 2>&1 | Select-Object -Last 2 }
if (Test-Path scripts/qa/testsukita_board.py) { & py scripts/qa/testsukita_board.py 2>&1 | Select-Object -Last 2 }

Write-Host $logLine
exit $councilExit
