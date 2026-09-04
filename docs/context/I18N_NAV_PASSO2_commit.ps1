# Botoes de navegacao da instancia traduzidos - PASSO 2: commit
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current
git status --short
git add templates/watcherdb_portal.html static/i18n/pt.json static/i18n/pt-BR.json static/i18n/en.json static/i18n/es.json `
        docs/changelog/CHANGELOG.md docs/context/I18N_NAV_PASSO1_apply.py docs/context/I18N_NAV_PASSO2_commit.ps1 docs/context/CONTEXT.md
$msg = @'
fix(i18n): botoes de navegacao da instancia traduzem (tab.* + data-i18n nos 16 botoes)

Owner 04/09 (ES): "os nomes do menu nao traduziram". Os 16 nav-btn tinham o rotulo
hardcoded em ingles; passam a <span data-i18n="tab.*">. O namespace tab.* ja'
existia mas em pt estava em ingles -> pt-PT (Visão Geral, Espaço, Disco, Memória,
Serviços, Sessões, Segurança, Utilizadores, Encriptação); es "Sesiones"; chave nova
tab.performance; pt-BR override users. Zero backend.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
