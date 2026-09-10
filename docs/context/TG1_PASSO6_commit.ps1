# TestGrapete TG-1 - PASSO 6: 3.a corrida (com credenciais) e commit do fix "verde vazio". PS7. Corre TU.
# Pre-requisito: PASSO 5 aplicado; .env.qa com WATCHERDB_QA_VIEWER_USER/PASS, WATCHERDB_QA_DBA_USER/PASS
# e (opcional) WATCHERDB_QA_ADMIN_USER/PASS. Sem admin, o perfil admin salta com motivo e conta como medido
# desde que viewer/dba tenham corrido.

$ErrorActionPreference = 'Stop'
$repo = 'c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
if (-not (Select-String -Path scripts/qa/nightly_testgrapete.ps1 -Pattern 'TG-1 PASSO 5' -Quiet)) { throw "PASSO 5 nao aplicado. ABORT." }

Write-Host "== 3.a corrida (council + externo) na 8434 =="
& pwsh scripts/qa/nightly_testgrapete.ps1
$exit = $LASTEXITCODE
$hoje = Get-Date -Format 'yyyy-MM-dd'
$n = @(Get-ChildItem "docs\qa\externo\$hoje\council\cases" -Filter '*.json' -ErrorAction SilentlyContinue).Count
Write-Host "nightly exit = $exit; casos medidos = $n"
if ($n -eq 0) { throw "Nada medido: .env.qa sem credenciais de perfil. Nao commito. ABORT." }
if ($exit -ne 0) {
    Write-Host "Council vermelho com $n casos medidos: ler docs\qa\externo\$hoje\council\pytest.log. pageerror/5xx = achado do portal (findings-inbox); role/429 = .env.qa."
    throw "Nao commito com o council vermelho. ABORT."
}

git add scripts/qa/nightly_testgrapete.ps1 scripts/qa/testgrapete_board.py `
    docs/context/TG1_PASSO5_fix2_apply.py docs/context/TG1_PASSO6_commit.ps1 docs/context/TG1_PASSO7_envqa_apply.py
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"

$msg = @'
qa(testgrapete): TG-1 - verde vazio nao e' verde (casos limpos por corrida, exit 2 sem medicoes)

2.a corrida (09/09): 51/51 casos saltados por falta de credenciais e o job devolveu 0;
o sumario contou os JSON da 1.a corrida, que ficavam na mesma pasta do dia.
- nightly: limpa council/cases/ no inicio; 0 casos medidos => exit 2; linha do log com "N saltados"
- board: corrida sem casos do council fica cinzenta, nao verde

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'tg1_fix2_commit_msg.txt'
Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: git push origin main; abrir docs\qa\externo\index.html"
