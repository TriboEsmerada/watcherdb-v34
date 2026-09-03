# i18n lote F2 (KPI_METADATA segue o idioma) - PASSO 2: commit (depois do PASSO 1 + pytest --no-cov + validador + browser)
# Identidade: owner (git). Onde: raiz do V3.4. Rollback: git reset --soft HEAD~1 ou git revert <sha>.
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current
git status --short
git add templates/watcherdb_portal.html static/i18n/pt.json static/i18n/pt-BR.json static/i18n/en.json static/i18n/es.json `
        docs/changelog/CHANGELOG.md docs/context/I18N_F2_PASSO1_apply.py docs/context/I18N_F2_KEYS.json `
        docs/context/I18N_F2_PASSO2_commit.ps1 docs/context/CONTEXT.md docs/context/PLANO_I18N_LINGUIST_PTBR_2026-09-03.md
$msg = @'
feat(i18n): lote F2 BUG-003 - titulos dos cartoes principais seguem o idioma escolhido

Decisao owner 03/09 (recomendacao aceite): os 24 cartoes de KPI_METADATA que ainda
tinham title/subtitle/modalTitle como literais (EN puro misturado com PT) passam ao
padrao de getter que cpu-critical/memory-critical/jobs-* ja usavam, com chaves
kpi_meta.<id>.* em 4 idiomas e o literal actual como fallback. Nenhum sitio de
render muda. Traducoes v33-i18n-linguist. Zero backend.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
