# TestGrapete TG-1b - PASSO 2: gera o painel com o que houver e commita. PS7. Corre TU.
# Pre-requisito: PASSO 1 aplicado (py docs/context/TG1B_PASSO1_apply.py). Pode correr antes ou depois do TG-1.

$ErrorActionPreference = 'Stop'
$repo = 'c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'main') { throw "Branch actual e' '$branch', esperado 'main'. ABORT." }
if (-not (Test-Path scripts\qa\testgrapete_board.py)) { throw "PASSO 1 nao aplicado. ABORT." }

Write-Host "== Gerar painel =="
& py scripts/qa/testgrapete_board.py
if ($LASTEXITCODE -ne 0) { throw "gerador falhou" }
Write-Host "Abrir: $repo\docs\qa\externo\index.html"

git add scripts/qa/testgrapete_board.py docs/qa/externo/index.html `
    docs/context/TG1B_PASSO1_apply.py docs/context/TG1B_PASSO2_commit.ps1 docs/context/PLANO_TESTGRAPETE_2026-09-09.md
if (Test-Path scripts\qa\nightly_testgrapete.ps1) { git add scripts/qa/nightly_testgrapete.ps1 }
git add docs/qa/externo/*/board.html 2>$null

$msg = @'
qa(testgrapete): TG-1b - painel estatico (index.html + board.html por corrida)

scripts/qa/testgrapete_board.py le os bundles de docs/qa/externo/<dia>/ e gera
uma pagina sem servidor nem dependencias: linha do tempo das corridas, council
(afirma) e qa-externo (confere) lado a lado, e a seccao de divergencias, que e'
onde nascem os achados. O job noturno chama-o no fim e grava externo/results.json.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'tg1b_commit_msg.txt'
Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
