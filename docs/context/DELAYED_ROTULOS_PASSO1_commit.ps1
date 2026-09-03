# Backup Delayed - Lote A (rotulos honestos) + council v34 - PASSO 1: commit
# Identidade: owner (git). Onde: PowerShell na raiz do V3.4. Impacto: so' git local.
# Rollback: git reset --soft HEAD~1 (mantem ficheiros) ou git revert <sha> apos push.
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current   # esperado: main
git status --short          # esperado: 6 M + 4 ?? (v34-specialist, PLANO, PROMPT_V6, este .ps1)

git rm --quiet .claude/agents/watcherdb-v33-specialist.md
git add .claude/agents/watcherdb-v34-specialist.md `
        docs/context/PLANO_BACKUP_DELAYED_MELHORIAS_2026-09-03.md `
        docs/context/PROMPT_PROPAGACAO_V6_BACKUP_DELAYED_ROTULOS_2026-09-03.md `
        docs/context/DELAYED_ROTULOS_PASSO1_commit.ps1 `
        docs/changelog/CHANGELOG.md docs/context/CONTEXT.md `
        static/i18n/pt.json static/i18n/en.json static/i18n/es.json `
        templates/watcherdb_portal.html

$msg = @'
feat(backup-delayed): rotulos honestos na modal e banda DIFF + council v34

Lote A do PLANO_BACKUP_DELAYED_MELHORIAS_2026-09-03 (revisao owner 03/09,
consenso v33-specialist, gate i18n PASS):
- modal: "Esperado" -> "Limite de aviso: dd/mm hh:mm (excedido ha Nh)";
  o valor e' last+warning_h (sempre no passado) e lia-se como proximo backup.
  Linha "Gap ... vs expected" removida (redundante). 2 chaves i18n x 3 locales.
- banda diff_schedule_stopped: "Agendamento DIFF parado" -> "Cadeia DIFF
  parada (FULL a cobrir)" em tile, titulo da modal, chip e 2 reconciliacoes;
  help backup-delayed (pt/en/es) explica porque so' DIFF e o limite de aviso.
- council: watcherdb-v33-specialist -> watcherdb-v34-specialist (identidade
  V3.4, seccao Linhagem preserva historico V3.3 como precedente).
Zero mudanca de numeros/backend. Docs: PLANO + PROMPT_PROPAGACAO_V6 + CHANGELOG.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
# -m $msg falha no PS7 quando a mensagem tem aspas duplas (split em argumentos);
# usar ficheiro + -F (licao 03/09).
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
