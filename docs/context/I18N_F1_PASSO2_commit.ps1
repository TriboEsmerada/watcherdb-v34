# i18n lote F1 (BUG-003) - PASSO 2: commit (depois do PASSO 1 sem ABORT + pytest --no-cov + validador + browser)
# Identidade: owner (git). Onde: raiz do V3.4. Rollback: git reset --soft HEAD~1 ou git revert <sha>.
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current
git status --short
git add templates/watcherdb_portal.html static/i18n/pt.json static/i18n/pt-BR.json static/i18n/en.json static/i18n/es.json `
        docs/changelog/CHANGELOG.md docs/context/I18N_F1_PASSO1_apply.py docs/context/I18N_F1_PASSO2_commit.ps1 docs/context/CONTEXT.md
$msg = @'
feat(i18n): lote F1 BUG-003 - dashboard KPI e modais de backup/integridade sem texto PT hardcoded

Pedido owner 03/09 (modal "Backup Delayed - Critico" em PT-BR: "se esse tem os outros
devem estar assim tbm"). Traducoes v33-i18n-linguist; plano de lotes frontend-specialist.
- ~110 strings de _advRow/_advCard, cartoes das modais, accoes de clique e linhas de
  resumo/reconciliacao -> chaves kpi_adv.* (4 locales) ou chaves ja existentes
  (modal.*, kpi_report.*, kpi_modal.*). Helper _kpiTp para placeholders {n}.
- acentuacao corrigida em todos os fallbacks; "Outros falhou"->"Outros falharam";
  "accionaveis"->"acionaveis" (AO90).
Lotes seguintes F2-F6 planeados. Zero backend.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
