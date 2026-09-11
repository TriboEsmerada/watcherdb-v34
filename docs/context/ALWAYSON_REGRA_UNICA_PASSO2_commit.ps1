# ALWAYS ON REGRA UNICA - PASSO 2: testes, commit; depois (manual) Restart V34 + prova no cartao/modal. PS7. Corre TU.
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.4'
Set-Location $repo
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { throw "branch != main. ABORT." }
if (-not (Test-Path api\routers\intelligence\alwayson_rules.py)) { throw "PASSO 1 nao aplicado. ABORT." }

Write-Host "== Testes: regra unica (8) + i18n + os que tocam KPIs/helpers =="
& py -m pytest tests/unit/test_alwayson_rules_20260911.py tests/unit/test_i18n_parity.py tests/unit/test_kpi_env_breakdown_20260818.py `
    tests/unit/test_api_routers.py tests/unit/test_critical_routers.py -q --no-cov -p no:cacheprovider 2>&1 | Select-Object -Last 5
if ($LASTEXITCODE -ne 0) { throw "testes vermelhos. ABORT." }
& py -c "import api.routers.intelligence.helpers, api.routers.intelligence_kpis; print('imports OK')"
if ($LASTEXITCODE -ne 0) { throw "import dos routers falhou. ABORT." }
& py scripts/i18n_validate.py 2>&1 | Select-Object -Last 1

git add api/routers/intelligence/alwayson_rules.py api/routers/intelligence/helpers.py api/routers/intelligence_kpis.py `
    templates/watcherdb_portal.html static/i18n/pt.json static/i18n/en.json static/i18n/es.json `
    tests/unit/test_alwayson_rules_20260911.py docs/context/ALWAYSON_REGRA_UNICA_PASSO1_apply.py docs/context/ALWAYSON_REGRA_UNICA_PASSO2_commit.ps1
$diff = (git diff --cached --name-only) -join ', '
if ($diff -match 'docs/qa/externo|\.env') { throw "evidencias ou .env no commit. ABORT." }
Write-Host "Ficheiros no commit: $diff"
$msg = @'
fix(alwayson): regra unica card/modal/breakdown + modal diz "N instancia(s) . M base(s)" (TestSprite TC-011)

Diagnostico 10/09: os 4 "instancias" do TC-011 eram bases (DATACAP_01/FENIX/MicroStrategyRep em PRD211,
MYBAGP2 em PRD405); o cartao conta DISTINCT Instance = 2. Unidade e rotulo, nao regra. Mas havia duas
copias do WHERE (resumo com excepcao Availability_Mode, modal sem) e o breakdown por ambiente contava
linhas por base em vez de instancias distintas.

- api/routers/intelligence/alwayson_rules.py: UMA regra (WHERE, CASE dos motivos, classificador Python,
  contagens por instancia distinta, deteccao cacheada da coluna Availability_Mode)
- helpers.collect_alwayson e intelligence_kpis (modal always-on) usam a regra; +unhealthy_db_count,
  +unhealthy_instances_count; unhealthy_by_env por instancia distinta (soma o cartao)
- portal: modal always-on "Total: N instancia(s) . M base(s) com problema" (kpi_modal.database_s pt/en/es)
- 8 testes: 2 instancias reais, linhas duplicadas por base, assincrona em SYNCHRONIZING (com e sem coluna),
  suspensa + lado vazio, dados vazios, CASE coerente com WHERE, contrato dos 3 sitios

Fora: dados ausentes ainda viram 0 no cartao (lote N/D dos cartoes); coluna Availability_Mode na STG e'
infra partilhada V1 (veto v1-intel). Propagar a V6.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
'@
$msgFile = Join-Path $env:TEMP 'alwayson_msg.txt'; Set-Content -Path $msgFile -Value $msg -Encoding utf8
git commit -F $msgFile
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git log -1 --oneline
Write-Host "`nAGORA (manual):"
Write-Host "  Restart-Service WatcherDBWebServiceV34"
Write-Host "  no portal: cartao 'Always On unhealthy' = N; abrir a modal: 'Total: N instancia(s) . M base(s)'"
Write-Host "  SELECT (tu, Intelligence): SELECT COUNT(DISTINCT Instance) AS instancias, COUNT(*) AS bases FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_STG s WITH (NOLOCK) WHERE s.Update_TS >= DATEADD(MINUTE,-5,GETDATE()) AND (<WHERE de alwayson_rules>)"
Write-Host "  git push origin main"
