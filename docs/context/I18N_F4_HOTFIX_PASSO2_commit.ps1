# i18n lote F4 HOTFIX (category 'Espaco' reposto) - PASSO 2: commit
# Identidade: owner (git). Onde: raiz do V3.4. Rollback: git reset --soft HEAD~1 ou git revert <sha>.
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current
git status --short
git add templates/watcherdb_portal.html docs/changelog/CHANGELOG.md docs/context/I18N_F4_PAIRS.json `
        docs/context/I18N_F4_HOTFIX_PASSO1_apply.py docs/context/I18N_F4_HOTFIX_PASSO2_commit.ps1 docs/context/CONTEXT.md .nestor/session.log
$msg = @'
fix(i18n): hotfix F4 - repoe category 'Espaco' nas 4 entradas de KPI_DOCUMENTATION

O commit 27d427e aplicou o par "Espaco"->"Espaço" do sidecar do linguista tambem ao campo
category das 4 entradas de Espaco. Esse valor e identificador (KPI_CATEGORIES, categoryColors,
KPI_METADATA), nao texto: o menu de ajuda deixava de listar os 4 KPIs de Espaco. Reposto nas
4 linhas, par reclassificado no sidecar (skip_identifier), CHANGELOG 33->32 literais.
Sessao paralela retomada apos fecho acidental apanhou o defeito ao rever a lista.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
