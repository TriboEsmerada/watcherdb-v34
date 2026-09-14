# FIX API 500 - PASSO 2: testes, commit; depois (manual) migracao SQL + Restart V34 + smoke de API do TestSukita. PS7. Corre TU.
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
if (-not (Test-Path tests\unit\test_api_500s_20260911.py)) { throw "PASSO 1 nao aplicado. ABORT." }

Write-Host "== Testes: 5 novos + routers + qa_comprehensive =="
& py -m pytest tests/unit/test_api_500s_20260911.py tests/unit/test_api_routers.py tests/unit/test_critical_routers.py tests/unit/test_qa_comprehensive.py -q --no-cov -p no:cacheprovider 2>&1 | Select-Object -Last 4
if ($LASTEXITCODE -ne 0) { throw "testes vermelhos. ABORT." }
& py -c "import api.routers.sqlserver_kpis, watcherdb.api.routers.security, modules.monitoring.backup_pattern_analysis, modules.monitoring.queries; print('imports OK')"
if ($LASTEXITCODE -ne 0) { throw "import falhou. ABORT." }

git add api/routers/sqlserver_kpis.py modules/monitoring/queries.py modules/monitoring/backup_pattern_analysis.py `
    watcherdb/api/routers/security.py tests/unit/test_api_500s_20260911.py `
    docs/context/FIX_API500_PASSO1_apply.py docs/context/FIX_API500_PASSO2_commit.ps1
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"
$msg = @'
fix(api): 8 endpoints a 500 apanhados pelo smoke de API do TestSukita v1 (achados 1-4 de 11/09)

- sqlserver_kpis: JSONResponse com jsonable_encoder (Decimal/datetime) - 5 endpoints /api/sqlserver-kpis/* voltam a responder
- queries.py: hint WITH(NOLOCK) numa TVF (database-io-stats: Incorrect syntax near 'with', desde sempre) e
  caracter U+2248 num comentario de TEMPDB_GROWTH_ANALYSIS (pyodbc UnicodeEncodeError) removidos
- backup_pattern_analysis: execute_query nao aceita params= (2 chamadas em TypeError, padroes nunca calculados) -> literal escapado
- security.py: get_critical_issues converte a JSONResponse da analise em dict (era AttributeError .get)
- 5 testes de regressao. Fora: active-sessions 976 por reproduzir; migracao must_change_password corre-a o owner

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'fix_api500_msg.txt'; Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline

Write-Host "`nAGORA (manual, e' teu):"
Write-Host "  1) SSMS na WatcherDB_Intelligence (SQLHDSTST505\I01) - bloco do canonico 10136-10142 (must_change_password):"
Write-Host "     IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'must_change_password')"
Write-Host "     BEGIN ALTER TABLE dbo.WatcherDB_Users ADD must_change_password BIT NOT NULL DEFAULT 1;"
Write-Host "           EXEC('UPDATE dbo.WatcherDB_Users SET must_change_password = 0 WHERE disabled = 0'); END"
Write-Host "  2) Restart-Service WatcherDBWebServiceV34"
Write-Host "  3) prova (com .env.qa carregado): py -m pytest tests/e2e/test_api_smoke_e2e.py -m e2e --no-cov -p no:cacheprovider -q -k viewer"
Write-Host "  4) git push origin main"
