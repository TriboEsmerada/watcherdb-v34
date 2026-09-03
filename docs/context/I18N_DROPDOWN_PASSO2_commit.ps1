# Selector de idioma em dropdown - PASSO 2: commit (depois do PASSO 1 sem ABORT + validacao no browser)
# Identidade: owner (git). Onde: PowerShell na raiz do V3.4. Impacto: so' git local.
# Rollback: git reset --soft HEAD~1 ou git revert <sha>.
Set-Location "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4"
git branch --show-current   # esperado: main
git status --short

git add static/js/watcherdb_i18n_v2.js static/css/i18n_selector.css `
        templates/watcherdb_portal.html docs/changelog/CHANGELOG.md `
        docs/context/I18N_DROPDOWN_PASSO1_apply.py docs/context/I18N_DROPDOWN_PASSO2_commit.ps1 `
        docs/context/CONTEXT.md

$msg = @'
feat(i18n): selector de idioma em dropdown no header (4 opcoes, teclado)

Pedido owner 03/09 ("prefiro drill-down"); parecer frontend-specialist:
- header: botao de ciclo PT->PT-BR->EN->ES substituido pelo dropdown do motor
  (WatcherI18N.createLanguageSelector; CSS ja' linkado, 4 opcoes desde 5612d68).
- runtime: navegacao por teclado que faltava (setas/Home/End, Enter/Espaco,
  Escape devolve foco, Tab fecha), aria-selected + aria-controls, foco visivel,
  estado activo sincronizado via onLanguageChange.
- portal: kpiCycleLang (nunca ligado a botao) e cycleLangGlobal removidos;
  ciclo do Relatorio KPI mantido (fast-follow).
Zero backend, zero BD. Nomes dos idiomas na propria lingua (sem chaves i18n novas).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP "wdb_commit_msg.txt"
[IO.File]::WriteAllText($msgFile, $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -q -F $msgFile
Remove-Item $msgFile -ErrorAction SilentlyContinue
git log --oneline -1
