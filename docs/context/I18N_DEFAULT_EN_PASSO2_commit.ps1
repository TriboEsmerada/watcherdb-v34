# Ingles como idioma por omissao - PASSO 2: commit (depois do PASSO 1 + node --check + browser em janela privada)
# Identidade: owner (git). Onde: raiz do V3.4. Rollback: git reset --soft HEAD~1 ou git revert <sha>.
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current
git status --short
git add static/js/watcherdb_i18n_v2.js templates/watcherdb_portal.html docs/FEATURE_MATRIX.md `
        knowledge_base/domain/i18n_glossary.md docs/changelog/CHANGELOG.md `
        .claude/agents/v33-i18n-linguist.md .claude/agents/v33-i18n-coverage.md `
        docs/context/I18N_DEFAULT_EN_PASSO1_apply.py docs/context/I18N_DEFAULT_EN_PASSO2_commit.ps1 docs/context/CONTEXT.md
$msg = @'
feat(i18n): ingles passa a idioma por omissao do portal

Decisao owner 03/09. Aplica-se a quem ainda nao escolheu idioma (localStorage
watcherdb_lang continua a mandar). pt.json mantem-se ground truth de chaves;
fallback en -> pt mantido (chave em falta mostra pt, nunca a chave crua).
<html lang> do portal -> en. Docs (FEATURE_MATRIX, glossario) e charters dos
micro-agents i18n alinhados.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
