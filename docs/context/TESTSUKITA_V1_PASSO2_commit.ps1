# TESTSUKITA V1 - PASSO 2: coleccao, corrida completa na 8434 (~35-45 min), commit se o council ficar verde. PS7. Corre TU.
# Pre-requisitos: PASSO 1 aplicado; .env.qa valido; 1 min desde o ultimo login de teste.
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
foreach ($f in @('tests\e2e\test_interactions_e2e.py', 'tests\e2e\test_api_smoke_e2e.py', 'scripts\qa\testsukita_ratchet.py')) {
    if (-not (Test-Path $f)) { throw "PASSO 1 nao aplicado: falta $f. ABORT." }
}
if (-not (Select-String -Path scripts/qa/nightly_testsukita.ps1 -Pattern 'TESTSUKITA V1' -Quiet)) { throw "PASSO 1 nao aplicado no nightly. ABORT." }

Write-Host "== Coleccao dos 4 ficheiros e2e =="
& py -m pytest tests/e2e/test_smoke_modules_e2e.py tests/e2e/test_semantic_e2e.py tests/e2e/test_interactions_e2e.py tests/e2e/test_api_smoke_e2e.py --collect-only -q --no-cov -p no:cacheprovider -m e2e 2>&1 | Select-Object -Last 6
if ($LASTEXITCODE -ne 0) { throw "coleccao falhou. ABORT." }
& py -c "import ast; [ast.parse(open(f, encoding='utf-8').read()) for f in ('scripts/qa/testsukita_board.py','scripts/qa/testsukita_ratchet.py','tests/e2e/conftest.py')]; print('sintaxe OK')"

Write-Host "== Corrida completa (council + externo + ratchet + painel) na 8434 =="
& pwsh scripts/qa/nightly_testsukita.ps1
$exit = $LASTEXITCODE
$hoje = Get-Date -Format 'yyyy-MM-dd'
$n = @(Get-ChildItem "docs\qa\externo\$hoje\council\cases" -Filter '*.json' -ErrorAction SilentlyContinue).Count
Write-Host "nightly exit = $exit; casos medidos = $n"
if (Test-Path "docs\qa\externo\$hoje\council\RATCHET.md") { Get-Content "docs\qa\externo\$hoje\council\RATCHET.md" | Select-Object -First 12 }
if ($n -eq 0) { throw "Nada medido. ABORT." }
if ($exit -ne 0) {
    Write-Host "Council vermelho: ver RATCHET.md (hipoteses) e council\pytest.log. Falha do runner -> corrigir o runner; falha do portal -> achado."
    throw "Nao commito com o council vermelho. ABORT."
}

git add tests/e2e/test_interactions_e2e.py tests/e2e/test_api_smoke_e2e.py tests/e2e/test_semantic_e2e.py tests/e2e/conftest.py `
    scripts/qa/testsukita_ratchet.py scripts/qa/nightly_testsukita.ps1 scripts/qa/testsukita_board.py `
    docs/context/PLANO_TESTSUKITA_2026-09-09.md docs/context/TESTSUKITA_README.md `
    docs/context/TESTSUKITA_V1_PASSO1_apply.py docs/context/TESTSUKITA_V1_PASSO2_commit.ps1
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"
$msg = @'
qa(testsukita): V1 - explorador de interaccoes, smoke de API pelo OpenAPI, ratchet com hipoteses, DOM em falha, janela do log, unidade do Always On

Paridade com o TestSprite e o que ele nao faz (owner 11/09: "tudo o que o TestSprite faz e mais"):
- test_interactions_e2e.py: por aba e perfil, 6 cliques nao destrutivos + 2 campos + 1 select, modais fechadas; invariantes
- test_api_smoke_e2e.py: GET do /openapi.json por perfil; nunca 5xx; viewer sem campos sensiveis nem 200 em /admin
- conftest: DOM em falha; nightly: janela de logs/service_stderr.log da corrida no bundle
- testsukita_ratchet.py: regressoes/novas/resolvidas/persistentes vs corrida anterior + endpoints que mudaram + hipotese por assinatura
- semantico: Always On sempre no drill-down; cartao == instancias distintas na modal (regra unica ce0db42)
- painel: seccao Ratchet, cobertura de interaccoes e API; README do TestSukita

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'testsukita_v1_msg.txt'; Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: git push origin main; abrir docs\qa\externo\index.html (seccao Ratchet)"
