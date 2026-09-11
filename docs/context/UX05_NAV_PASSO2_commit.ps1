# UX-05 - PASSO 2: teste estatico, restart (teu), prova em runtime a 1093x614, commit. PS7. Corre TU.
$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
if (-not (Select-String -Path templates/watcherdb_portal.html -Pattern 'UX-05 \(2026-09-11\)' -Quiet)) { throw "PASSO 1 nao aplicado. ABORT." }

& py -m pytest tests/unit/test_ux05_nav_compacta_20260911.py tests/unit/test_template_modal_escaping.py -q --no-cov -p no:cacheprovider 2>&1 | Select-Object -Last 2
if ($LASTEXITCODE -ne 0) { throw "teste estatico vermelho. ABORT." }

Write-Host "`nRESTART (teu) e prova em runtime:"
Write-Host "  Restart-Service WatcherDBWebServiceV34"
$go = Read-Host "Ja reiniciaste o servico? [s/N]"
if ($go -notmatch '^[sS]') { throw "reinicia e volta a correr este PASSO 2. ABORT (nada commitado)." }

Get-Content .env.qa | ForEach-Object { if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"'), 'Process') } }
if (-not $env:WATCHERDB_BASE_URL) { $env:WATCHERDB_BASE_URL = 'https://localhost:8434' }
$env:WATCHERDB_QA_BUNDLE = Join-Path (Get-Location) ("docs\qa\externo\" + (Get-Date -Format 'yyyy-MM-dd') + "\council")
Write-Host "== TestViewport 1093x614 e 1366x768 na 8434 =="
& py -m pytest tests/e2e/test_semantic_e2e.py -m e2e --no-cov -p no:cacheprovider -q -k Viewport 2>&1 | Select-Object -Last 4
if ($LASTEXITCODE -ne 0) { throw "viewport ainda falha: ver council\cases\viewer_viewport_1093x614.json (nav.right vs innerWidth). ABORT." }

git add templates/watcherdb_portal.html tests/unit/test_ux05_nav_compacta_20260911.py docs/context/UX05_NAV_PASSO1_apply.py docs/context/UX05_NAV_PASSO2_commit.ps1
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"
$msg = @'
fix(ux-05): barra de abas cabe na janela a 1093 px (so' icone abaixo de 1200 px, nome do servidor trunca)

Relatorio QA (UX-05) descrevia sobreposicao; o TestSukita mediu corte: a 1093 px CSS (1366x768 @125%) a barra
terminava em 1196 px. So' CSS: @media (max-width: 1200px) esconde o rotulo dos 16 botoes (o title da' o nome),
compacta-os e trunca o h2. TestViewport 1093x614 (fd0d7f0) passa a verde; teste estatico novo.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'ux05_msg.txt'; Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: git push origin main"
