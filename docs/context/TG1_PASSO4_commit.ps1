# TestGrapete TG-1 - PASSO 4: 2.a corrida real com o runner corrigido e commit do motor. PS7. Corre TU.
# Pre-requisito: PASSO 3 aplicado; .env.qa com WATCHERDB_QA_VIEWER/DBA/ADMIN_USER+PASS (cada conta com o role
# do perfil) e WATCHERDB_QA_SERVER opcional (sem ele: primeiro servidor 'test'). Esperar 1 min desde o ultimo
# login falhado (rate limit 5/min).

$ErrorActionPreference = 'Stop'
$repo = 'c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'main') { throw "Branch actual e' '$branch', esperado 'main'. ABORT." }
if (-not (Select-String -Path tests/e2e/test_smoke_modules_e2e.py -Pattern 'TG-1 PASSO 3' -Quiet)) { throw "PASSO 3 nao aplicado. ABORT." }
if (-not (Test-Path scripts\qa\runtime\NIGHTLY.txt)) { throw "PASSO 3 nao aplicado (NIGHTLY.txt). ABORT." }

Write-Host "== Coleccao do smoke =="
& py -m pytest tests/e2e/test_smoke_modules_e2e.py --collect-only -q --no-cov -p no:cacheprovider -m e2e 2>&1 | Select-Object -Last 2

Write-Host "== 2.a corrida real (council + externo) na 8434 =="
& pwsh scripts/qa/nightly_testgrapete.ps1
$exit = $LASTEXITCODE
$hoje = Get-Date -Format 'yyyy-MM-dd'
Write-Host "nightly exit = $exit  -> docs\qa\externo\$hoje\SUMMARY.md e docs\qa\externo\index.html"
if ($exit -ne 0) {
    Write-Host "Council ainda vermelho. Ver council/pytest.log: se for 'role ... perfil' ou 429 e' .env.qa/tempo; se for pageerror/5xx e' achado do portal."
    throw "Nao commito com o council vermelho. ABORT."
}

# Commit so' do motor (docs/qa/externo e' ignorado por desenho)
git add tests/e2e/test_smoke_modules_e2e.py .gitignore scripts/qa/nightly_testgrapete.ps1 scripts/qa/runtime/NIGHTLY.txt `
    docs/context/PLANO_TESTGRAPETE_2026-09-09.md docs/context/TG1_PASSO1_apply.py docs/context/TG1_PASSO2_commit.ps1 `
    docs/context/TG1_PASSO3_fix_apply.py docs/context/TG1_PASSO4_commit.ps1
$diff = (git diff --cached --name-only) -join ', '
Write-Host "Ficheiros no commit: $diff"
if ($diff -match 'docs/qa/externo') { throw "evidencias no commit: nao pode. ABORT." }

$msg = @'
qa(testgrapete): TG-1 - runner do council (fleet + 16 abas x 3 perfis) corrigido apos a 1.a corrida

1.a corrida (09/09, 8434, admin): 15 FAILED por defeitos do runner, nao do portal:
- login em cada caso batia no rate limit 5/min (24 x 429) -> um login por perfil, token em cache
- fallback WATCHERDB_QA_USER sem ROLE caia no perfil admin -> so' com ROLE explicito, e o role
  devolvido pelo login tem de ser o do perfil
- servidor escolhido em producao (environment e' 'production'/'quality'/'test') -> test > quality,
  producao so' com WATCHERDB_QA_SERVER explicito
- id da aba calculado com generateTabId() (leva timestamp) -> activeTabId do portal
Externo: so' os scripts em scripts/qa/runtime/NIGHTLY.txt (5 de 9 correm sem argumentos).
Evidencias e painel ficam locais (docs/qa/externo/ ignorado desde 05/09).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'tg1_fix_commit_msg.txt'
Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: git push origin main; abrir docs\qa\externo\index.html; depois TG-2 (tarefa agendada)."
