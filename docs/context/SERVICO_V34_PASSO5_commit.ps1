# Servico - PASSO 5: redirect de stdout/stderr tambem com host python.exe (logs voltam a escrever)
# Identidade: owner (git). Impacto: so' git local. Rollback: git reset --soft HEAD~1
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current   # esperado: main
git status --short

git add watcherdb_service.py tests/unit/test_service_entry.py `
        docs/changelog/CHANGELOG.md docs/context/CONTEXT.md docs/context/SOLUCOES.md `
        docs/context/PROMPT_PROPAGACAO_SERVICE_LOGS_2026-09-03.md docs/context/SERVICO_V34_PASSO5_commit.ps1

$msg = @'
fix(service): redirigir stdout/stderr para logs tambem com host python.exe

Achado 03/09 ao validar a licenca do V34 (afecta V3.3 desde 21/08 18:24):
com o binPath em python.exe o SCM entrega streams VALIDOS para NUL, o
redirect so' testava `is None` (pythonservice.exe) e nunca corria — toda a
saida da app (uvicorn, AUTH, reconciliacoes) era descartada; rotacao de
10 MB nunca rodou; so' o Event Log tinha registos. Novo helper puro
_std_needs_redirect(stdout, stderr, as_service) = algum None OU
servicemanager.RunningAsService(); __init__ usa-o. 3 testes. Portar V3.3/V6
(PROMPT_PROPAGACAO_SERVICE_LOGS_2026-09-03.md).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
