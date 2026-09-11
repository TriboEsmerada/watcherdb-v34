# Fecho 11/09: commita CONTEXT (+1 linha) e o prompt de propagacao V6. PS7. Corre TU.
$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
git add docs/context/CONTEXT.md docs/context/PROMPT_PROPAGACAO_V6_DBFILTER_ALWAYSON_2026-09-11.md docs/context/FECHO_20260911_commit.ps1
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"
$msg = @'
docs(context): fecho 11/09 - Always On regra unica, rename TestSukita, ponto 3; prompt V6 (db-filter + always on + AbortError)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'fecho_20260911_msg.txt'; Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: git push origin main"
