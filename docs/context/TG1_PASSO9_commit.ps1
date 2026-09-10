# TestGrapete TG-1 - PASSO 9: 4.a corrida e commit do motor (PASSOS 5, 7 e 8). PS7. Corre TU.
# Pre-requisitos: PASSO 8 aplicado; .env.qa com qa_viewer e qa_dba correctas (qa_dba deu 401 na 3.a corrida:
# confirmar a password ou reset pela API); 15 min desde a ultima tentativa falhada de qa_dba (lockout).

$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
foreach ($p in @('TG-1 PASSO 5', 'TG-1 PASSO 7', 'TG-1 PASSO 8')) {
    if (-not (Select-String -Path scripts/qa/nightly_testgrapete.ps1 -Pattern $p -Quiet)) { throw "$p nao aplicado no nightly. ABORT." }
}
if (-not (Select-String -Path tests/e2e/test_smoke_modules_e2e.py -Pattern 'TG-1 PASSO 8' -Quiet)) { throw "PASSO 8 nao aplicado no teste. ABORT." }

Write-Host "== 4.a corrida (council + externo) na 8434 =="
& pwsh scripts/qa/nightly_testgrapete.ps1
$exit = $LASTEXITCODE
$hoje = Get-Date -Format 'yyyy-MM-dd'
$n = @(Get-ChildItem "docs\qa\externo\$hoje\council\cases" -Filter '*.json' -ErrorAction SilentlyContinue).Count
Write-Host "nightly exit = $exit; casos medidos = $n"
if ($n -eq 0) { throw "Nada medido. ABORT." }
if ($exit -ne 0) {
    Write-Host "Council vermelho com $n casos: docs\qa\externo\$hoje\council\pytest.log (grep '^E ')."
    throw "Nao commito com o council vermelho. ABORT."
}

git add scripts/qa/nightly_testgrapete.ps1 scripts/qa/testgrapete_board.py tests/e2e/test_smoke_modules_e2e.py `
    docs/context/TG1_PASSO5_fix2_apply.py docs/context/TG1_PASSO6_commit.ps1 docs/context/TG1_PASSO7_envqa_apply.py `
    docs/context/TG1_PASSO8_fix3_apply.py docs/context/TG1_PASSO9_commit.ps1
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"

$msg = @'
qa(testgrapete): TG-1 - corridas 2-4: verde vazio, .env.qa, arg= no wait, login falhado em cache, pausas do rate limit

- nightly: limpa council/cases por corrida; 0 casos medidos => exit 2 (2.a corrida: 51 saltados deram verde)
- nightly: deriva WATCHERDB_QA_URL para os scripts do qa-externo; aviso sem .env.qa; pausa 65 s entre
  metades e 15 s entre scripts (login aceita 5/min; 3/5 scripts viam 429)
- board: corrida sem casos do council fica cinzenta
- runner: Page.wait_for_function exige arg= por nome (16 "avisos" de 10 ms eram TypeError apanhado);
  timeout e erro do runner distinguidos; 1.o login falhado por perfil fica em cache (17 x 401 em qa_dba
  bloqueava a conta por 15 min)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'tg1_fix3_commit_msg.txt'
Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: git push origin main; abrir docs\qa\externo\index.html"
