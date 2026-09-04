# Troca de idioma sem refetch - PASSO 2: commit (depois do PASSO 1 + node --check + validacao no browser)
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current
git status --short
git add static/js/watcherdb_i18n_v2.js templates/watcherdb_portal.html docs/changelog/CHANGELOG.md `
        docs/context/I18N_PERF_SWITCH_PASSO1_apply.py docs/context/I18N_PERF_SWITCH_PASSO2_commit.ps1 docs/context/CONTEXT.md
$msg = @'
fix(i18n): troca de idioma traduz a aba visivel na hora; restantes ao serem activadas

Owner 04/09: "demora para traduzir quando mudo de idioma". Causa: o motor
chamava refreshTab(tab.id) e a propriedade e' tabId -> no-op; so' [data-i18n]
mudava na hora, o resto esperava pelo refresh periodico. Como 11 tipos de aba
guardam na cache HTML ja' renderizado (lingua antiga), nao da' para servir da
cache: a aba activa recarrega ja' (1 recolha), as outras ficam _i18nStale com a
cache limpa e activateTab recarrega-as quando forem activadas. Corrigido tambem
mainContentArea -> tabsContentArea (ramo morto). Parecer frontend-specialist +
verificacao do orquestrador. Zero backend.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
