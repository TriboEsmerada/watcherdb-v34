# TESTSUKITA V1 - PASSO 4: commita o motor v1 (a 1.a corrida ja provou: 72 casos medidos, 8 achados no portal). PS7. Corre TU.
# A corrida das 02:00 e' a prova seguinte; o vermelho que fica e' do portal (achados #1-#5), nao do runner.
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
if (-not (Select-String -Path tests/e2e/test_semantic_e2e.py -Pattern 'V1 PASSO 3' -Quiet)) { throw "PASSO 3 nao aplicado. ABORT." }

& py -m pytest tests/e2e/test_smoke_modules_e2e.py tests/e2e/test_semantic_e2e.py tests/e2e/test_interactions_e2e.py tests/e2e/test_api_smoke_e2e.py --collect-only -q --no-cov -p no:cacheprovider -m e2e 2>&1 | Select-Object -Last 5
if ($LASTEXITCODE -ne 0) { throw "coleccao falhou. ABORT." }
& py -c "import ast; [ast.parse(open(f, encoding='utf-8').read()) for f in ('scripts/qa/testsukita_board.py','scripts/qa/testsukita_ratchet.py','tests/e2e/conftest.py')]; print('sintaxe OK')"
& py scripts/qa/testsukita_ratchet.py | Select-Object -Last 1
& py scripts/qa/testsukita_board.py | Select-Object -Last 1

git add tests/e2e/test_interactions_e2e.py tests/e2e/test_api_smoke_e2e.py tests/e2e/test_semantic_e2e.py tests/e2e/conftest.py `
    scripts/qa/testsukita_ratchet.py scripts/qa/nightly_testsukita.ps1 scripts/qa/testsukita_board.py `
    docs/context/PLANO_TESTSUKITA_2026-09-09.md docs/context/TESTSUKITA_README.md docs/context/FINDINGS_TESTSUKITA_2026-09-11.md `
    docs/context/TESTSUKITA_V1_PASSO1_apply.py docs/context/TESTSUKITA_V1_PASSO2_commit.ps1 `
    docs/context/TESTSUKITA_V1_PASSO3_fix_apply.py docs/context/TESTSUKITA_V1_PASSO4_commit.ps1
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"
$msg = @'
qa(testsukita): V1 - interaccoes por aba, smoke de API pelo OpenAPI, ratchet com hipoteses, DOM em falha, janela do log, unidade do Always On

Owner 11/09: "tudo o que o TestSprite faz e outras coisas que ele nao faz".
- test_interactions_e2e.py: por aba e perfil, cliques nao destrutivos + campos + select, modais fechadas
- test_api_smoke_e2e.py: GET do /openapi.json por perfil (150/250); nunca 5xx; viewer sem campos sensiveis nem 200 em /admin
- conftest: DOM em falha; nightly: janela de logs/service_stderr.log da corrida; ratchet antes do painel
- testsukita_ratchet.py: regressoes/novas/resolvidas/persistentes + endpoints que mudaram + hipotese por assinatura
- semantico: Always On sempre no drill-down e cartao == instancias distintas na modal; 3 leituras dos cartoes (re-render)
- painel: seccao Ratchet + cobertura de interaccoes e API; README

1.a corrida (14:16-14:49): 72 casos medidos, externo 5/5, 33 min. 8 achados no portal registados em
FINDINGS_TESTSUKITA_2026-09-11.md: 5 endpoints /api/sqlserver-kpis 500 (Decimal), database-io-stats e
tempdb-growth-analysis 500 (execute_query(params=)), security/critical 500 (JSONResponse.get), coluna
must_change_password em falta, active-sessions 500 em AG secundaria, /api/admin/health publico, 2 endpoints >20 s,
125 tracebacks 10054. Restart do servico a meio da corrida (Event 7039 14:20) explica os ERR_CONNECTION_REFUSED.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'testsukita_v1_p4_msg.txt'; Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: git push origin main. A corrida das 02:00 corre o v1 completo; de manha: NIGHTLY_LOG + RATCHET.md do dia."
