# TestGrapete TG-1c - PASSO 2: corre so' o ficheiro semantico + smoke (rapido) na 8434 e commita se verde. PS7. Corre TU.
# Pre-requisitos: PASSO 1 aplicado; .env.qa valido; 1 min desde o ultimo login de teste (rate limit).
# Nao usa o nightly (demoraria 20 min): corre os dois ficheiros directamente com o mesmo bundle.

$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
if (-not (Test-Path tests\e2e\test_semantic_e2e.py)) { throw "PASSO 1 nao aplicado. ABORT." }
if (-not (Select-String -Path tests/e2e/test_smoke_modules_e2e.py -Pattern 'TESTGRAPETE TG-1c' -Quiet)) { throw "PASSO 1 nao aplicado no smoke. ABORT." }

# .env.qa -> ambiente desta shell (mesma logica do nightly)
Get-Content .env.qa | ForEach-Object { if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"'), 'Process') } }
if (-not $env:WATCHERDB_BASE_URL) { $env:WATCHERDB_BASE_URL = 'https://localhost:8434' }
$hoje = Get-Date -Format 'yyyy-MM-dd'
$env:WATCHERDB_QA_BUNDLE = Join-Path $repo "docs\qa\externo\$hoje\council"
New-Item -ItemType Directory -Force -Path (Join-Path $env:WATCHERDB_QA_BUNDLE 'cases') | Out-Null

Write-Host "== Coleccao =="
& py -m pytest tests/e2e/test_semantic_e2e.py --collect-only -q --no-cov -p no:cacheprovider -m e2e 2>&1 | Select-Object -Last 2

Write-Host "== Semantico (grupos, drill-down, viewport) na 8434 =="
& py -m pytest tests/e2e/test_semantic_e2e.py -m e2e --no-cov -p no:cacheprovider -q `
    --screenshot only-on-failure --tracing retain-on-failure --output (Join-Path $env:WATCHERDB_QA_BUNDLE 'playwright') 2>&1 | Select-Object -Last 12
$exitSem = $LASTEXITCODE

Write-Host "== Smoke com contexto (TC-003), so' perfil viewer para ser rapido =="
$env:WATCHERDB_QA_DBA_USER = ''; $env:WATCHERDB_QA_DBA_PASS = ''
& py -m pytest tests/e2e/test_smoke_modules_e2e.py -m e2e --no-cov -p no:cacheprovider -q -k "viewer" 2>&1 | Select-Object -Last 6
$exitSmoke = $LASTEXITCODE

& py scripts/qa/testgrapete_board.py | Select-Object -Last 1
Write-Host "semantico exit=$exitSem; smoke(viewer) exit=$exitSmoke"
if ($exitSem -ne 0 -or $exitSmoke -ne 0) {
    Write-Host "Vermelho: docs\qa\externo\$hoje\council\cases\*.json e playwright\ (screenshots). Se for contexto errado, e' o TC-003 reproduzido em casa: achado."
    throw "Nao commito com vermelho. ABORT."
}

git add tests/e2e/test_semantic_e2e.py tests/e2e/test_smoke_modules_e2e.py scripts/qa/nightly_testgrapete.ps1 `
    docs/context/PLANO_TESTGRAPETE_2026-09-09.md docs/context/TG1C_PASSO1_apply.py docs/context/TG1C_PASSO2_commit.ps1 `
    docs/context/TG2_TAREFA_AGENDADA.ps1 docs/context/QA_RESET_QA_DBA.ps1
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"

$msg = @'
qa(testgrapete): TG-1c - assercoes semanticas (contexto da aba, grupos de KPI, drill-down, viewport 1093x614) + TG-2 scripts

O TestSprite do owner (10/09) mede o que o smoke nao media: TC-003 contexto do servidor (FAILED la),
TC-006 desktop, TC-007..014 grupos de KPI. Sem crawler nem IA, com invariantes:
- smoke: aba activa pertence ao servidor escolhido e #serverName mostra o nome (TC-003)
- test_semantic_e2e.py: grupos com cartoes e valores legiveis; cartoes de topo abrem #instancesModal
  com conteudo quando > 0 (valor e linhas gravados para o ratchet); 1093x614 e 1366x768 sem scroll
  horizontal nem sobreposicao nome/abas (UX-05)
- nightly corre os dois ficheiros
- TG-2: tarefa WatcherDB-TestGrapete (02:00, S4U, bateria permitida) provada as 15:16; QA_RESET_QA_DBA.ps1

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'tg1c_commit_msg.txt'
Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: git push origin main"
