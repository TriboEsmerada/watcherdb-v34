# Lote F7 (checklist de carregamento) - PASSO 2: commit
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current
git status --short
git add templates/watcherdb_portal.html static/i18n/pt.json static/i18n/en.json static/i18n/es.json docs/changelog/CHANGELOG.md `
        docs/context/I18N_F7_PASSO1_apply.py docs/context/I18N_F7_PASSO2_commit.ps1 docs/context/CONTEXT.md .claude/agents/v33-i18n-coverage.md
$msg = @'
fix(i18n): lote F7 BUG-003 - checklist de carregamento das abas segue o idioma

Owner 09/09: "achei mais 1 caso" (A carregar Filegroups e espaco por database...
em EN). 26 lc.track('<PT>') em 13 abas + "A carregar ${label}..." / "sem resposta"
no renderer startLoadingChecklist. Namespace lc.* em pt-PT/en/es (pt-BR herda),
renderer via _kpiTp com fallback ao literal, call sites via t('lc.*').
Charter v33-i18n-coverage: inventario das superficies de texto do portal +
varrimento obrigatorio dos literais JS. Zero backend.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
