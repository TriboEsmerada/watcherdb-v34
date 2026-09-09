# Lote F3 (ajudas "?" dos cartoes das abas) - PASSO 2: commit
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current
git status --short
git add templates/watcherdb_portal.html static/i18n/pt.json static/i18n/pt-BR.json static/i18n/en.json static/i18n/es.json docs/changelog/CHANGELOG.md `
        docs/context/I18N_F3_PASSO1_apply.py docs/context/I18N_F3_PASSO2_commit.ps1 docs/context/I18N_F3_CARD_HELP.json docs/context/CONTEXT.md `
        .claude/agents/v33-i18n-coverage.md tests/unit/test_i18n_parity.py
$msg = @'
feat(i18n): lote F3 BUG-003 - ajudas "?" dos cartoes das abas seguem o idioma

Owner 09/09: "acho que todas as interrogacoes nao traduzem". As 92 ajudas de
CARD_HELP_TEXTS (444 textos) eram PT cru sem acentos e sem chave. Namespace
card_help.<id>.{title,s<i>_label,s<i>_text,tip} em pt-PT acentuado, en-US e es
(pt-BR herda), helper _chT com fallback ao literal; "Dica:" passa a t('help.tip').
Traducoes: 3 lotes do v33-i18n-linguist, validados por estrutura (mesmo nº de
seccoes e placeholders por locale). Zero backend.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
