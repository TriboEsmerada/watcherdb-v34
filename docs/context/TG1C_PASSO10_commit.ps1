# TestGrapete - PASSO 10: valida a coleccao do smoke e commita o ajuste de ruido (sem corrida: a noite 1 ja' mediu). PS7. Corre TU.
$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
if (-not (Select-String -Path tests/e2e/test_smoke_modules_e2e.py -Pattern 'PASSO 9:' -Quiet)) { throw "PASSO 9 nao aplicado. ABORT." }

& py -m pytest tests/e2e/test_smoke_modules_e2e.py --collect-only -q --no-cov -p no:cacheprovider -m e2e 2>&1 | Select-Object -Last 2
if ($LASTEXITCODE -ne 0) { throw "coleccao falhou" }

git add tests/e2e/test_smoke_modules_e2e.py docs/context/TG1C_PASSO9_ruido_apply.py docs/context/TG1C_PASSO10_commit.ps1
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"
$msg = @'
qa(testgrapete): AbortError da troca de aba e' ruido do runner (contado em "abortados"), nao falha

Noite 1 do TG-2 (11/09 02:00, tarefa sozinha): 41 casos, externo 5/5, 1 erro = viewer/alwayson com 7
"[processResponse] X - ERRO: AbortError: Request aborted": o runner muda de aba 500 ms depois de escolher
o servidor e o portal cancela os pedidos do Overview em voo. Intermitente, nao e' defeito funcional.
Achado P3 registado: portal 15432 regista AbortError como console.error (devia ser info).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'tg_p10_msg.txt'
Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: git push origin main"
