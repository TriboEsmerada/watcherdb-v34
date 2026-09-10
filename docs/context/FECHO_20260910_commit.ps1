# Fecho 10/09: commita o blackboard (CONTEXT +4 linhas), o script de reset e o que restar de docs/context. PS7. Corre TU.
# Correr DEPOIS de TG1C_PASSO4 (que commita smoke/nightly/plano/scripts TG-1c e TG-2).
$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
git add docs/context/CONTEXT.md docs/context/QA_RESET_PASSWORD.ps1 docs/context/FECHO_20260910_commit.ps1
git add docs/context/findings-inbox.md 2>$null
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"
$msg = @'
docs(context): fecho 10/09 - TestGrapete TG-1/TG-1c/TG-2 provados, FIX DB-FILTER, Always On TC-011 diagnosticado

Blackboard: 4 linhas (TG-1 fechado, TG-2 tarefa 02:00 provada em S4U/bateria, FIX DB-FILTER shipped,
TG-1c + diagnostico do TC-011 do TestSprite: bases vs instancias, nao regra; by_env conta linhas).
QA_RESET_PASSWORD.ps1: reset por conta com prova de 1 login e actualizacao do .env.qa.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'fecho_20260910_msg.txt'
Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: git push origin main"
