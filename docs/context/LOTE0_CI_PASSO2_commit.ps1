# LOTE 0 (CI vivo) - PASSO 2: move tests/integration para fora do testpaths,
# valida a coleccao local e commita. PS7. Corre TU (git = escrita).
#
# Pre-requisito: PASSO 1 aplicado (py docs/context/LOTE0_CI_PASSO1_apply.py).
#
# Porque mover a pasta inteira e nao so' 7 ficheiros: dos 11 test_*.py em
# tests/integration, 10 ligam a instancias reais (SQLADSPRD002, SQLHDSPRD214,
# SQLHDSTST505...) e 2 deles (test_conversion.py, test_det_view.py) fazem
# pyodbc.connect com Trusted_Connection=yes = domain user a tocar em BD
# (Regra de Ouro #2) so' por o pytest os recolher. Os check_*_manual.py ja'
# nao eram recolhidos; vao juntos para manter o conjunto coerente.
#
# Rollback: git revert do commit (ou `git mv` inverso antes do commit).

$ErrorActionPreference = 'Stop'
$repo = 'c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'main') { throw "Branch actual e' '$branch', esperado 'main'. ABORT." }

if (-not (Select-String -Path .github/workflows/ci.yml -Pattern 'Collect tests \(fail if zero collected\)' -Quiet)) {
    throw "PASSO 1 nao aplicado (ci.yml sem step de collect). ABORT."
}

# 1) git mv tests/integration -> scripts/manual_debug/integration
New-Item -ItemType Directory -Force -Path scripts\manual_debug | Out-Null
if (Test-Path tests\integration) {
    git mv tests/integration scripts/manual_debug/integration
    if ($LASTEXITCODE -ne 0) { throw "git mv falhou" }
    Write-Host "OK: tests/integration -> scripts/manual_debug/integration"
} elseif (Test-Path scripts\manual_debug\integration) {
    Write-Host "Ja movido."
} else {
    throw "tests/integration nao existe e scripts/manual_debug/integration tambem nao. ABORT."
}

# 2) Coleccao local (agora segura: nada em tests/ liga a PRD ao ser recolhido)
Write-Host "`n== Coleccao local (py -m pytest, sem correr testes) =="
$collect = & py -m pytest --collect-only -q --no-cov -p no:cacheprovider 2>&1
$n1 = ($collect | Select-String -Pattern '^tests/.*: (\d+)$' | ForEach-Object { [int]$_.Matches[0].Groups[1].Value } | Measure-Object -Sum).Sum
$n2 = ($collect | Select-String -Pattern '::' | Measure-Object).Count
$n  = [Math]::Max([int]$n1, [int]$n2)
$collect | Select-Object -Last 3
Write-Host "Testes recolhidos localmente: $n  (referencia 04/09 sem integration/e2e/performance: 824)"
if ($n -le 0) { throw "0 testes recolhidos localmente. Nao commitar. ABORT." }

# 3) Commit (mensagem via ficheiro: -m com aspas duplas falhou no PS7, ver SOLUCOES)
git add .github/workflows/ci.yml scripts/manual_debug tests/integration 2>$null
git add .github/workflows/ci.yml scripts/manual_debug
$msg = @'
ci: LOTE0 - pipeline volta a correr (working-directory inexistente) + gate 0-collected

Council 2026-09-04 sobre relatorio QA externo (Fable 5.1), item 3:
- ci.yml: remove `working-directory: WATCHERDB_V3.3` (pasta inexistente desde o
  snapshot 8631e50) nos 3 jobs; corrige caminhos de coverage.xml/bandit-report.json
- step novo "Collect tests": falha visivel se 0 testes recolhidos (item 3c do QA)
- lint e Safety em continue-on-error (674 achados ruff; `safety check` deprecado);
  o sinal do CI passa a ser o job `test`
- tests/integration -> scripts/manual_debug/integration: 10 dos 11 test_*.py
  ligavam a instancias PRD/TST ao serem recolhidos (2 com Trusted_Connection,
  viola Regra de Ouro #2); fora do testpaths, tal como os check_*_manual.py
- pywin32 marker JA existia (requirements.txt:71) - premissa 3a do QA era falsa

Nao inclui e2e_mock no CI: tests/e2e faz page.goto ao servico vivo (8433),
"CI-able" no marker mas nao na pratica. Fica para wave propria.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'lote0_commit_msg.txt'
Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline

Write-Host "`nPROXIMO PASSO (manual, e' o que dispara o CI):"
Write-Host "  git push origin main"
Write-Host "Depois: Actions -> job 'Run Tests' -> step 'Collect tests' mostra 'Testes recolhidos: N'."
Write-Host "Se o job test ficar vermelho por ImportError em Linux (pywin32/wmi), e' achado novo: registar em CONTEXT."
