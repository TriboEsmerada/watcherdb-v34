# Lote F4b (titulos da modal KPI Documentation) - PASSO 2: commit
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current
git status --short
git add templates/watcherdb_portal.html static/i18n/pt.json static/i18n/en.json static/i18n/es.json docs/changelog/CHANGELOG.md `
        docs/context/I18N_F4B_PASSO1_apply.py docs/context/I18N_F4B_PASSO2_commit.ps1 docs/context/I18N_F4B_TITLES.json docs/context/CONTEXT.md
$msg = @'
fix(i18n): lote F4b - titulos da modal KPI Documentation seguem o idioma

Owner 09/09 (EN): "a interrogacao dos KPIs nao esta sendo traduzida". As
categorias traduziam; os 29 title: de KPI_DOCUMENTATION eram PT cru sem chave
(menu, pesquisa, cabecalho). Namespace novo kpi_doc.<id>.title em pt/en/es
(pt = texto actual; pt-BR herda), helper _docTitle com fallback ao title.
Texto de ajuda dos jobs de backup deixa de citar instancia de cliente pelo
nome (repo publico). Traducoes verificadas pelo v33-i18n-linguist. Zero backend.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
