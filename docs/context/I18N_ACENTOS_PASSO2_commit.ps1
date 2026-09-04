# Lotes B/C do linguista (acentos pt/es) - PASSO 2: commit
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current
git status --short
git add static/i18n/pt.json static/i18n/es.json static/i18n/pt-BR.json docs/changelog/CHANGELOG.md `
        docs/context/I18N_ACENTOS_PASSO1_apply.py docs/context/I18N_ACENTOS_PASSO2_commit.ps1 `
        docs/context/I18N_ACENTOS_PT.json docs/context/I18N_ACENTOS_ES.json docs/context/CONTEXT.md
$msg = @'
fix(i18n): lotes B/C do linguista - acentuacao em pt.json e es.json

Owner: acentos correctos como P1; screenshot ES de 04/09 mostrava "Tamano",
"diagnostico", "analisis". Varrimento mecanico (455 candidatos es, 227 pt)
confirmado palavra a palavra pelo v33-i18n-linguist; so' acentos, til, cedilha,
ñ e grafia AO90 dessas palavras - termos, frases e placeholders intactos.
Aplicado por texto (pt.json tem chaves duplicadas; nunca round-trip).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
