# i18n lote F4 (acentos na documentacao dos KPIs) - PASSO 2: commit
# Identidade: owner (git). Onde: raiz do V3.4. Rollback: git reset --soft HEAD~1 ou git revert <sha>.
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current
git status --short
git add templates/watcherdb_portal.html docs/changelog/CHANGELOG.md `
        docs/context/I18N_F4_PASSO1_apply.py docs/context/I18N_F4_PAIRS.json docs/context/I18N_F4_PASSO2_commit.ps1 docs/context/CONTEXT.md
$msg = @'
fix(i18n): lote F4 - acentos e AO90 na documentacao dos KPIs (KPI_DOCUMENTATION, campos PT)

Campos portugueses do bloco KPI_DOCUMENTATION (o texto de cada "?" do dashboard) com
acentos em falta ou grafia pre-AO90 corrigidos sem reescrever frases; blocos i18n.en/es
intocados. Traducoes/revisao v33-i18n-linguist. So texto, zero logica.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
