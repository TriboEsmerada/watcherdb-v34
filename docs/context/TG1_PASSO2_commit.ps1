# TestGrapete TG-1 - PASSO 2: valida (coleccao + corrida manual na 8434) e commita. PS7. Corre TU.
# Pre-requisito: PASSO 1 aplicado; servico 8434 vivo; .env.qa preenchido (ver scripts/qa/nightly_testgrapete.ps1).

$ErrorActionPreference = 'Stop'
$repo = 'c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'main') { throw "Branch actual e' '$branch', esperado 'main'. ABORT." }
foreach ($f in @('tests\e2e\test_smoke_modules_e2e.py', 'scripts\qa\nightly_testgrapete.ps1')) {
    if (-not (Test-Path $f)) { throw "PASSO 1 nao aplicado: falta $f. ABORT." }
}

# 1) O ficheiro novo NAO entra na corrida por omissao (marker e2e) e nao parte a coleccao
Write-Host "== Coleccao (default, sem e2e) =="
$collect = & py -m pytest --collect-only -q --no-cov -p no:cacheprovider 2>&1
$n1 = ($collect | Select-String -Pattern '^tests/.*: (\d+)$' | ForEach-Object { [int]$_.Matches[0].Groups[1].Value } | Measure-Object -Sum).Sum
Write-Host "Testes recolhidos (default): $n1 (esperado 824; o smoke fica de fora por -m 'not e2e')"
if ($n1 -le 0) { throw "0 testes recolhidos. ABORT." }

Write-Host "== Coleccao do smoke (so' contagem) =="
& py -m pytest tests/e2e/test_smoke_modules_e2e.py --collect-only -q --no-cov -p no:cacheprovider -m e2e 2>&1 | Select-Object -Last 2
# esperado: 51 casos = 3 fleet + 16 abas x 3 perfis

# 2) Corrida manual contra a 8434 (usa .env.qa via o script noturno)
Write-Host "== Corrida manual (council + externo) na 8434 =="
& pwsh scripts/qa/nightly_testgrapete.ps1
$exit = $LASTEXITCODE
Write-Host "nightly exit = $exit  (0 = council verde; != 0 = ver docs/qa/externo/<hoje>/SUMMARY.md antes de commitar)"
if ($exit -ne 0) {
    Write-Host "Council com falhas: le o SUMMARY.md e os JSON em council/cases. Se for defeito real do portal, e' achado (findings-inbox); se for credencial/servidor, corrige .env.qa e repete."
    throw "Nao commito com o council vermelho na primeira corrida. ABORT."
}

# 3) Commit (sem evidencias pesadas: playwright/ e .env.qa estao no .gitignore)
git add tests/e2e/test_smoke_modules_e2e.py scripts/qa/nightly_testgrapete.ps1 .gitignore `
    docs/context/PLANO_TESTGRAPETE_2026-09-09.md docs/context/TG1_PASSO1_apply.py docs/context/TG1_PASSO2_commit.ps1 `
    docs/qa/externo/NIGHTLY_LOG.md
git add docs/qa/externo/*/SUMMARY.md docs/qa/externo/*/council/cases docs/qa/externo/*/council/junit.xml docs/qa/externo/*/council/pytest.log docs/qa/externo/*/externo 2>$null

$msg = @'
qa(testgrapete): TG-1 - runner do council (fleet + 16 abas x 3 perfis) + corrida noturna com qa-externo

Decisao do council 2026-09-09 (qa-specialist + challenger) sobre TestSprite:
nao construir clone; construir a cola que falta. Lacuna real: nenhum e2e corria
sem uma pessoa o lancar.

- tests/e2e/test_smoke_modules_e2e.py: invariantes (0 pageerror, 0 erros de
  consola fora do ruido, 0 5xx, aba responde), evidencias JSON por caso, perfis
  sem credenciais saltam com motivo (licao 19/08). Marker e2e: fora do run default.
- scripts/qa/nightly_testgrapete.ps1: council (afirma) e depois qa_ext_*.py do
  qa-externo (confere), intocados; bundle em docs/qa/externo/<dia>/; SUMMARY.md;
  linha em NIGHTLY_LOG.md. Credenciais em .env.qa (ignorado).
- .gitignore: screenshots/traces do playwright e .env.qa.
- Plano em docs/context/PLANO_TESTGRAPETE_2026-09-09.md (TG-1..TG-4, barra de 4 semanas).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'tg1_commit_msg.txt'
Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: git push origin main; depois TG-2 (tarefa agendada) em docs/context/PLANO_TESTGRAPETE_2026-09-09.md"
