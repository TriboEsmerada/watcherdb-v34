# Backup Delayed - PASSO 3: ordem da modal (desc por urgencia) + acertos do runbook V34
# Identidade: owner (git). Impacto: so' git local. Rollback: git reset --soft HEAD~1
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current   # esperado: main
git status --short

git add templates/watcherdb_portal.html docs/changelog/CHANGELOG.md docs/context/CONTEXT.md `
        docs/context/SERVICO_V34_8434_RUNBOOK_2026-09-03.md docs/context/DELAYED_ORDEM_PASSO3_commit.ps1

$msg = @'
fix(backup-delayed): modal ordena por urgencia (critico->aviso, horas DESC)

Owner 03/09, validacao viva na 8434 ("o order by deve ser desc"). A regra
generica dos KPIs de backup (evento mais recente primeiro, Wave R+7.T2) e'
correcta para falhas mas invertia a urgencia no em-atraso: ultimo backup mais
recente = MENOS atrasado. backup-delayed passa a ter ordem propria: severidade
da base (critico > aviso > politica > info) e depois Hours_Since_Backup DESC;
sem horas (C1) vai para o topo. Restantes KPIs de backup mantem a ordem antiga.
node --check OK (12 blocos inline).

Runbook V34: pip via `python -m pip` (Scripts\pip.exe bloqueado por AppLocker/AV),
URLs https (TLS ON herdado do .env da 3.3).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
