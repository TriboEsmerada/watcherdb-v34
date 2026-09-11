# RENAME TestGrapete -> TestSukita - PASSO 1: git mv dos 3 ficheiros + substituicao de texto nos 8 ficheiros vivos + commit. PS7. Corre TU.
# Historico (PASSO scripts antigos, CONTEXT.md, NIGHTLY_LOG local) fica como esta': e' registo do que aconteceu.
# Depois: pwsh docs/context/RENAME_SUKITA_PASSO2_tarefa.ps1 (admin) para renomear a tarefa agendada.
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
if (Test-Path scripts\qa\testsukita_board.py) { throw "ja renomeado. ABORT." }

git mv scripts/qa/nightly_testgrapete.ps1 scripts/qa/nightly_testsukita.ps1
git mv scripts/qa/testgrapete_board.py scripts/qa/testsukita_board.py
git mv docs/context/PLANO_TESTGRAPETE_2026-09-09.md docs/context/PLANO_TESTSUKITA_2026-09-09.md

$py = @'
import re, pathlib
files = ["tests/e2e/test_smoke_modules_e2e.py", "tests/e2e/test_semantic_e2e.py", "scripts/qa/nightly_testsukita.ps1",
         "scripts/qa/testsukita_board.py", "scripts/qa/runtime/NIGHTLY.txt", "docs/context/PLANO_TESTSUKITA_2026-09-09.md",
         "docs/context/TG2_TAREFA_AGENDADA.ps1", ".gitignore"]
pares = [("TestGrapete", "TestSukita"), ("TESTGRAPETE", "TESTSUKITA"), ("testgrapete", "testsukita"), ("Grapete", "Sukita")]
total = 0
for f in files:
    p = pathlib.Path(f); t = p.read_text(encoding="utf-8"); o = t
    for a, b in pares: t = t.replace(a, b)
    n = sum(o.count(a) for a, _ in pares)
    if t != o:
        p.write_text(t, encoding="utf-8", newline="\n"); total += n; print(f"{f}: {n}")
print("total substituicoes:", total)
assert "grapete" not in "".join(pathlib.Path(f).read_text(encoding="utf-8").lower() for f in files)
'@
$tmp = Join-Path $env:TEMP 'rename_sukita.py'; Set-Content -Path $tmp -Value $py -Encoding utf8
& py $tmp
if ($LASTEXITCODE -ne 0) { throw "substituicao falhou" }

& py -m pytest tests/e2e/test_smoke_modules_e2e.py tests/e2e/test_semantic_e2e.py --collect-only -q --no-cov -p no:cacheprovider -m e2e 2>&1 | Select-Object -Last 3
& py -c "import ast,sys; ast.parse(open('scripts/qa/testsukita_board.py',encoding='utf-8').read()); print('board OK')"

git add -A scripts/qa tests/e2e .gitignore docs/context/PLANO_TESTSUKITA_2026-09-09.md docs/context/TG2_TAREFA_AGENDADA.ps1 docs/context/RENAME_SUKITA_PASSO1_commit.ps1 docs/context/RENAME_SUKITA_PASSO2_tarefa.ps1
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"
$msg = @'
qa(testsukita): rename TestGrapete -> TestSukita (motor, testes, plano, tarefa)

Decisao do owner 11/09. Renomeados: scripts/qa/nightly_testsukita.ps1, scripts/qa/testsukita_board.py,
docs/context/PLANO_TESTSUKITA_2026-09-09.md; texto nos testes e2e, NIGHTLY.txt, .gitignore e no script da
tarefa (WatcherDB-TestSukita; re-registo em RENAME_SUKITA_PASSO2_tarefa.ps1). Historico em docs/context fica.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'rename_sukita_msg.txt'; Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nPROXIMO: pwsh docs/context/RENAME_SUKITA_PASSO2_tarefa.ps1 (admin); git push origin main"
