# TestGrapete TG-1c - PASSO 6: semantico completo na 8434 e commit do que ficou fora (smoke+contexto, nightly,
# plano, scripts TG-1c/TG-2/reset). PS7. Corre TU. Pre-requisito: PASSO 5 aplicado. Espera 65 s antes do semantico (rate limit).

$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
if (-not (Select-String -Path tests/e2e/test_semantic_e2e.py -Pattern 'TG-1c PASSO 5' -Quiet)) { throw "PASSO 3 nao aplicado. ABORT." }

Get-Content .env.qa | ForEach-Object { if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"'), 'Process') } }
if (-not $env:WATCHERDB_BASE_URL) { $env:WATCHERDB_BASE_URL = 'https://localhost:8434' }
$hoje = Get-Date -Format 'yyyy-MM-dd'
$env:WATCHERDB_QA_BUNDLE = Join-Path $repo "docs\qa\externo\$hoje\council"
New-Item -ItemType Directory -Force -Path (Join-Path $env:WATCHERDB_QA_BUNDLE 'cases') | Out-Null

Write-Host "pausa 65 s (rate limit do login)"; Start-Sleep -Seconds 65
Write-Host "== Semantico completo (grupos, drill-down, viewport, filtro) na 8434 =="
& py -m pytest tests/e2e/test_semantic_e2e.py -m e2e --no-cov -p no:cacheprovider -q `
    --screenshot only-on-failure --tracing retain-on-failure --output (Join-Path $env:WATCHERDB_QA_BUNDLE 'playwright') 2>&1 | Select-Object -Last 12
if ($LASTEXITCODE -ne 0) { throw "semantico vermelho: ver council\cases\*drilldown*.json e playwright\. ABORT." }
& py scripts/qa/testgrapete_board.py | Select-Object -Last 1

git add tests/e2e/test_semantic_e2e.py tests/e2e/test_smoke_modules_e2e.py scripts/qa/nightly_testgrapete.ps1 `
    docs/context/PLANO_TESTGRAPETE_2026-09-09.md docs/context/TG1C_PASSO1_apply.py docs/context/TG1C_PASSO2_commit.ps1 `
    docs/context/TG1C_PASSO3_fix_apply.py docs/context/TG1C_PASSO4_commit.ps1 `
    docs/context/TG1C_PASSO5_fix_apply.py docs/context/TG1C_PASSO6_commit.ps1 `
    docs/context/TG2_TAREFA_AGENDADA.ps1 docs/context/QA_RESET_QA_DBA.ps1
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"

$msg = @'
qa(testgrapete): TG-1c - assercoes semanticas (contexto, grupos de KPI, drill-down por clique real, viewport) + TG-2

O TestSprite (10/09) mede o que o smoke nao media. Sem crawler nem IA:
- smoke: aba activa pertence ao servidor escolhido e #serverName mostra o nome (TC-003) - 17/17 verde
- semantico: grupos com cartoes e valores legiveis (TC-007..014); cartoes de topo abertos por clique real
  (a lista _kpiCardClickHandlers e' esvaziada pelo portal apos ligar os listeners), cartao > 0 => modal com
  conteudo, valor e linhas gravados; 1093x614 e 1366x768 sem scroll horizontal nem sobreposicao (UX-05)
- nightly corre smoke + semantico
- TG-2: tarefa WatcherDB-TestGrapete 02:00 S4U provada (15:16, 34 casos); bateria permitida; QA_RESET_QA_DBA.ps1

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'tg1c_p4_msg.txt'
Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: git push origin main"
