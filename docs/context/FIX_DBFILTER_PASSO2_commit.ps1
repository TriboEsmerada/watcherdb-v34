# FIX DB-FILTER - PASSO 2: testes unitarios + i18n, commit, e depois (manual) restart do V34 + prova e2e. PS7. Corre TU.
# Pre-requisito: PASSO 1 aplicado. O restart do servico e' teu (processo); o e2e de prova corre DEPOIS do restart.

$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
if (-not (Select-String -Path templates/watcherdb_portal.html -Pattern 'function applyDbFilter' -Quiet)) { throw "PASSO 1 nao aplicado. ABORT." }

Write-Host "== node --check do JS do portal (sintaxe) =="
$js = Join-Path $env:TEMP 'portal_dbfilter_check.js'
$html = Get-Content templates/watcherdb_portal.html -Raw
$m = [regex]::Match($html, '(?s)function renderDbTable\(.*?window\.renderDbTable = renderDbTable;')
if (-not $m.Success) { throw "bloco renderDbTable nao encontrado" }
Set-Content -Path $js -Value ("function t(k){return k}; var window={}; var document={createElement:function(){return {}}, getElementById:function(){return null}};`n" + $m.Value) -Encoding utf8
& node --check $js
if ($LASTEXITCODE -ne 0) { throw "sintaxe JS do bloco renderDbTable/applyDbFilter falhou" }

Write-Host "== Testes unitarios (novo + paridade i18n + escaping) =="
& py -m pytest tests/unit/test_overview_db_filter_20260910.py tests/unit/test_i18n_parity.py tests/unit/test_template_modal_escaping.py -q --no-cov -p no:cacheprovider 2>&1 | Select-Object -Last 4
if ($LASTEXITCODE -ne 0) { throw "testes unitarios vermelhos. ABORT." }
& py scripts/i18n_validate.py 2>&1 | Select-Object -Last 2

git add templates/watcherdb_portal.html static/i18n/pt.json static/i18n/en.json static/i18n/es.json `
    tests/unit/test_overview_db_filter_20260910.py tests/e2e/test_semantic_e2e.py `
    docs/context/FIX_DBFILTER_PASSO1_apply.py docs/context/FIX_DBFILTER_PASSO2_commit.ps1
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"

$msg = @'
fix(overview): filtro de bases nao filtrava (oninput descartava renderDbTable) + estado vazio

Achado do TestSprite (TC-003, 10/09) confirmado no codigo: o campo chamava renderDbTable(this.value)
e descartava o HTML devolvido; os cabecalhos de ordenacao, que fazem innerHTML = renderDbTable(...),
funcionavam. Sem mensagem quando o filtro nao encontra nada.

- applyDbFilter(valor): gera a seccao num elemento solto e copia SO' #db-table-body e #db-count
  (o input nao e' recriado; foco e cursor mantem-se)
- linha de estado vazio (colspan 5) com overview.no_databases_found em pt/en/es
- tests/unit/test_overview_db_filter_20260910.py (regressao estatica, 4 testes)
- TestFiltroBases em tests/e2e/test_semantic_e2e.py (TG-1c): filtra, contagem acompanha, foco mantido, estado vazio

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'fix_dbfilter_msg.txt'
Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline

Write-Host "`nAGORA (manual, e' teu):"
Write-Host "  Restart-Service WatcherDBWebServiceV34"
Write-Host "  py -m pytest tests/e2e/test_semantic_e2e.py -m e2e --no-cov -p no:cacheprovider -q -k FiltroBases   (com .env.qa carregado)"
Write-Host "  git push origin main"
