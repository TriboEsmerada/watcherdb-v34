# PONTO 3 - PASSO 2: valida e commita (viewport afirma UX-05; AbortError -> info). PS7. Corre TU.
$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
if (-not (Select-String -Path tests/e2e/test_semantic_e2e.py -Pattern 'PONTO 3 \(11/09\)' -Quiet)) { throw "PASSO 1 nao aplicado. ABORT." }
& py -m pytest tests/e2e/test_semantic_e2e.py --collect-only -q --no-cov -p no:cacheprovider -m e2e 2>&1 | Select-Object -Last 2
& py -m pytest tests/unit/test_template_modal_escaping.py tests/unit/test_overview_db_filter_20260910.py -q --no-cov -p no:cacheprovider 2>&1 | Select-Object -Last 2
if ($LASTEXITCODE -ne 0) { throw "testes vermelhos. ABORT." }
git add tests/e2e/test_semantic_e2e.py templates/watcherdb_portal.html docs/context/PONTO3_PASSO1_apply.py docs/context/PONTO3_PASSO2_commit.ps1
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"
$msg = @'
qa+fix: viewport afirma que a barra de abas cabe na janela (UX-05 medido: corte a 1093 px) + AbortError como info

- test_semantic_e2e.py: nav.right <= innerWidth por viewport; FALHA a 1093x614 de proposito ate' o UX-05
  ser corrigido no portal (nav so' icone < 1200 px) - o TestSukita afirma o achado todas as noites
- portal 15432: pedidos cancelados pela troca de aba deixam de ir para console.error (P3 da noite 1)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'ponto3_msg.txt'; Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: Restart-Service WatcherDBWebServiceV34 (para o AbortError); git push origin main"
