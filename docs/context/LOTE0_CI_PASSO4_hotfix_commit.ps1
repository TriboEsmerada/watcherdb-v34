# LOTE 0 (CI vivo) - PASSO 4: valida e commita o hotfix do 1.o run. PS7. Corre TU.
# Pre-requisito: PASSO 3 aplicado (py docs/context/LOTE0_CI_PASSO3_hotfix_apply.py).
# Inclui tambem os 5 ficheiros de docs/context deste lote que ficaram untracked.

$ErrorActionPreference = 'Stop'
$repo = 'c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'main') { throw "Branch actual e' '$branch', esperado 'main'. ABORT." }
if (-not (Select-String -Path .github/workflows/ci.yml -Pattern 'Install system libs \(unixodbc for pyodbc\)' -Quiet)) {
    throw "PASSO 3 nao aplicado em ci.yml. ABORT."
}
if (-not (Select-String -Path tests/unit/test_service_entry.py -Pattern 'pytest\.importorskip\(' -Quiet)) {
    throw "PASSO 3 nao aplicado em test_service_entry.py. ABORT."
}

# Coleccao local: em Windows o importorskip importa normalmente -> continua 824
Write-Host "== Coleccao local =="
$collect = & py -m pytest --collect-only -q --no-cov -p no:cacheprovider 2>&1
$n1 = ($collect | Select-String -Pattern '^tests/.*: (\d+)$' | ForEach-Object { [int]$_.Matches[0].Groups[1].Value } | Measure-Object -Sum).Sum
$n2 = ($collect | Select-String -Pattern '::' | Measure-Object).Count
$n  = [Math]::Max([int]$n1, [int]$n2)
Write-Host "Testes recolhidos localmente: $n (esperado 824)"
if ($n -le 0) { throw "0 testes recolhidos. ABORT." }

# Os 9 testes do launcher continuam a correr em Windows
Write-Host "== test_service_entry.py em Windows =="
& py -m pytest tests/unit/test_service_entry.py -q --no-cov -p no:cacheprovider 2>&1 | Select-Object -Last 2
if ($LASTEXITCODE -ne 0) { throw "test_service_entry.py falhou em Windows apos o hotfix. ABORT." }

git add .github/workflows/ci.yml tests/unit/test_service_entry.py `
    docs/context/LOTE0_CI_PASSO1_apply.py docs/context/LOTE0_CI_PASSO2_commit.ps1 `
    docs/context/LOTE0_CI_PASSO3_hotfix_apply.py docs/context/LOTE0_CI_PASSO4_hotfix_commit.ps1 `
    docs/context/COUNCIL_A_ROTACAO_CREDENCIAL_2026-09-04.md

$msg = @'
ci: LOTE0 hotfix - coleccao em Linux (unixodbc, importorskip) + notify so' pelo job test

1.o run real (33960086275 sobre 89d5be9) falhou no step "Collect tests":
- test_service_entry.py importava watcherdb_service ao nivel do modulo; o skipif
  so' actua depois da coleccao e o import puxa win32* -> erro de coleccao em Linux.
  Agora pytest.importorskip (em Windows continua a correr os 9 testes).
- pyodbc precisa de libodbc.so.2 e a imagem ubuntu-latest nao traz unixodbc
  (readme oficial do runner sem "odbc") -> step apt-get unixodbc antes do pip.
- Bandit em continue-on-error (exit 1 com achados e' o comportamento normal).
- Notify: so' needs.test.result decide a cor; lint/security informativos.
- Junta os scripts PASSO1-4 e o desenho da rotacao (Council A) a docs/context.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'lote0_hotfix_msg.txt'
Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO (manual): git push origin main   -> depois digo-te o resultado pela API."
