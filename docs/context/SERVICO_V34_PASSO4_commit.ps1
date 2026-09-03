# Servico V34 - PASSO 4: install/update registam python.exe do venv (fim do pythonservice.exe)
# Identidade: owner (git). Impacto: so' git local. Rollback: git reset --soft HEAD~1
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current   # esperado: main
git status --short

git add watcherdb_service.py docs/changelog/CHANGELOG.md docs/context/CONTEXT.md docs/context/SOLUCOES.md `
        docs/context/SERVICO_V34_8434_RUNBOOK_2026-09-03.md docs/context/SERVICO_V34_PASSO4_commit.ps1

$msg = @'
fix(service): install/update registam o python.exe do venv, nao pythonservice.exe

Owner 03/09 ("aplicar a solucao no servico de forma antecipada"). O
_exe_name_/_exe_args_ que ja existia para frozen passa a existir em venv:
sys.executable + caminho absoluto do wrapper. Sem isto o pywin32 copiava
pythonservice.exe para a raiz do venv — host sem python311.dll ao lado nem
site-packages, que morre antes do handshake SCM sem mensagem (SOLUCOES
2026-08-31 no V33; repetido 03/09 na 1a instalacao do V34, corrigido a mao
com sc.exe config binPath=). Frozen inalterado. Testes do servico verdes.
Runbook V34 passo 4 e SOLUCOES actualizados.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
