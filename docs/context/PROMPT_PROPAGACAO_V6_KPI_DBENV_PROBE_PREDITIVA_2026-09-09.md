# PROPAGAÇÃO V6 — lote 09/09/2026 (tarde): tile de bases por ambiente, probe do Overview, plan cache, análise preditiva

> Para a AI do V6. Regras + contratos explicados (não só o diff). Origem: V3.4, commits
> `e46c8bc` (KPI/probe/plan cache) e `8c531b1` (preditiva); scripts de aplicação em
> `docs/context/FIX_KPI_DBENV_PROBE_PLANCACHE_2026-09-09_apply.py` e
> `docs/context/FIX_PREDITIVA_FUNCIONA_2026-09-09_apply.py` (âncoras exactas, --check/--preview).
> **Portal V6 não é superset — grep das âncoras antes.** `helpers.py` e `modules/` **não são
> partilhados**: cada produto tem a sua cópia, logo o V6 pode ter cada anti-padrão de forma
> independente. Verificar, não assumir herdado.

---

## 1. Tile "Bases de dados" do resumo executivo ignora o filtro de ambiente

**Bug (V3.4):** ao seleccionar PRD/QLT/TST, todos os números mudavam menos o de bases de dados.
Duas causas somadas: (a) o tile lia `dba2.total_databases` directamente, sem o helper `evN()`
que os outros tiles usam; (b) mesmo com o helper, o backend não expunha `total_databases_by_env`
— e o contrato do `evN()` é "se a chave `X_by_env` não existir, cai no total da frota"
(anti-padrão do FIND-20260818-101, já propagado em 18/08).

**Fix:**
- backend (`api/routers/intelligence/helpers.py`, bloco "Calcular por ambiente" do
  `collect_db_availability`): chave nova `total_databases_by_env` (+ alias `total_by_env`) com a
  **mesma fonte do total** (`KPI_MSSQL_DB_AVAILABILITY_DET_VIEW`) classificada por
  `LEFT JOIN KPI_MSSQL_INST_ENVS e ON e.Instance = d.Instance` (padrão de 07/08 — nunca LIKE no
  nome). Defaults `{}` em `init_dashboard_results` para o caminho de erro não dar KeyError.
- portal: `const dbTotal = evN(dba2, 'total_databases') || evN(dba2, 'total_count');` nas
  **duas** funções (`_repTopCards` modo dashboard e `_repExecCard`).
- teste de contrato `tests/unit/test_kpi_env_breakdown_20260818.py`: `REQUIRED_BACKEND_KEYS`
  ganha as duas chaves + teste que o padrão antigo `(+dba2.total_databases || 0)` não existe.

**Verificar no V6:**
```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V6"
Select-String -Path templates\*.html -Pattern 'dba2\.total_databases|total_databases \|\|' -Recurse
Select-String -Path api -Pattern 'total_databases_by_env|"by_environment"' -Recurse
```
Se o V6 tiver o mesmo `dbTotal` directo e não tiver a chave: aplicar os dois lados. Se só tiver um
dos lados, o filtro continua a cair no total — o contrato é "todo `ev()`/`evN()` tem fonte".

---

## 2. Banner "N/6 checks failed — Databases" e cartão "DBs com Problema" em N/D, em TODOS os servidores

**Bug (V3.4, desde 07/08):** o probe do banner de diagnóstico
(`_probeResults['Databases']`) e `dbDataAvailable` exigiam `databasesData?.success === true`, mas
o endpoint `/api/queries/databases/{id}` (`api/routers/queries/space.py::get_databases`) devolve
`{server_id, databases, server_info, cached}` — **nunca teve `success`**. Resultado: o check
falhava em todos os servidores e o cartão ficava N/D sempre, com a tabela de bases carregada logo
abaixo (o log mostrava o GET a responder 200 na mesma página).

**Fix:** o endpoint devolve `"success": True` nas duas respostas (cache e fresca); o portal aceita
`success === true || (Array.isArray(databasesData?.databases) && databasesData.databases.length > 0)`
nos dois sítios. Regra: **um probe só é honesto se a fonte que ele lê existir no payload** — antes
de adicionar um check, `grep` do endpoint pela chave.

**Verificar no V6:** o V6 tem o banner de 07/08 (propagado em `8751f5b`). Grep:
```powershell
Select-String -Path templates\*.html -Pattern "'Databases': databasesData\?\.success|dbDataAvailable = databasesData" -Recurse
Select-String -Path api,watcherdb -Pattern '"databases": (serialized_result|cached_entry)' -Recurse
```

---

## 3. Erro 8115 "Arithmetic overflow converting expression to data type int" na plan cache

**Bug:** `plan_cache_query` faz `SUM(size_in_bytes)` sobre `sys.dm_exec_cached_plans`;
`size_in_bytes` é **INT** e em SQL Server `SUM(int)` devolve INT → rebenta quando a plan cache
passa 2 GB (servidores DW/MDM). O wrapper `_safe_query` engole em `logger.debug` e a secção
Plan Cache do card de Memória fica vazia sem aviso. 16 ocorrências em 2 servidores no V3.4.

**Fix:** `SUM(CAST(size_in_bytes AS BIGINT))` e `THEN CAST(size_in_bytes AS BIGINT) ELSE 0 END`
nas 5 expressões — em **duas cópias** (`modules/monitoring/memory_analysis.py` e
`modules/monitoring/queries.py`). Regra geral: qualquer `SUM` sobre coluna INT de DMV
(`size_in_bytes`, `size` de master_files, contadores) leva CAST para BIGINT.

**Verificar no V6:**
```powershell
Select-String -Path . -Pattern 'SUM\(size_in_bytes\)' -Include *.py -Recurse
```

---

## 4. Análise Preditiva de Crescimento (filegroup) — nunca tinha funcionado na máquina

**Contexto de tier:** a Feature Matrix classifica analytics/ML como Pro-only. No V3.4 a feature
ficou viva por esquecimento; o owner decidiu **mantê-la e pô-la a funcionar** (09/09). No V6 (Pro)
ela é legítima — mas provavelmente tem os **mesmos três defeitos**, porque o código é o mesmo
snapshot.

**Cadeia de causas (cada uma escondia a seguinte):**
1. `modules/analytics/__init__.py` arrancava o subprocess com o literal `"python"` → resolve pelo
   PATH da conta do serviço (aqui: Python 3.14 sem pyodbc), não pelo interpretador do serviço.
   → `sys.executable`.
2. `scripts/filegroup_interactive_report_v5_watcherdb.py` ligava à Intelligence com servidor
   **hardcoded** (`SQLHDSTST505\I01`) e `Trusted_Connection=yes` (identidade Windows da conta do
   serviço — viola a Regra de Ouro #2). → função `build_intelligence_conn_str()` no script:
   `sys.path` com a raiz do repo, `.env` 3-tier como fallback (`WATCHERDB_DATA_DIR`, ProgramData,
   raiz), `watcherdb.core.settings` para servidor/BD/driver/user, `db_identity.resolve()` e
   **recusa explícita** se a identidade não for SQL, `services.secrets.get_secret` para a password
   (desencripta Fernet/DPAPI). **Sem ramo Windows Auth de propósito.**
3. `watcherdb_main.py` (rota `POST /api/monitoring/space/filegroup/generate-report`) devolvia a
   falha como `dict` com HTTP **200** → o portal via `response.ok` e injectava o JSON (com traceback
   e caminhos `C:\Users\...`) no modal como se fosse o relatório. → `JSONResponse(status_code=500)`
   com mensagem saneada por `_sanitize_script_error()` (última linha útil, caminhos Windows
   mascarados com `<path>`, 300 chars); o traceback integral fica só no log do serviço.
4. Gate `_require_admin` chamado **inline** no corpo (anti-padrão R2-01 que o docstring do gate
   proíbe: corpo inválido devolve 422 a quem não está autorizado). → `Depends(_auth_require_admin)`
   na assinatura. Role mantida admin; passar a dba é trocar um nome.
5. Portal: botão "Análise" renderizado para toda a gente (o `data-admin-gated` só corre no login e
   este botão nasce depois) → condição `window._currentUser.role === 'admin'` no render; em falha
   lê `error` **ou** `detail` (401/403 do FastAPI vêm em `detail`) e trata `content-type:
   application/json` como erro mesmo com 200.

**Verificar no V6 (por ordem):**
```powershell
Select-String -Path modules\analytics\__init__.py -Pattern '"python",|sys\.executable'
Select-String -Path scripts\filegroup_interactive_report_v5*.py -Pattern 'Trusted_Connection|SQLHDSTST505'
Select-String -Path . -Include *.py -Pattern 'filegroup/generate-report' -Recurse   # que ficheiro serve a rota no V6?
Select-String -Path templates\*.html -Pattern "generateReport\('|'Databases': databasesData" -Recurse
```
Atenção: no V3.4 existiam **dois** ficheiros com a rota (`watcherdb_main.py` = vivo;
`watcherdb_intelligence.py` = legado sem referências nem gates). A sessão da manhã de 09/09 leu o
legado e concluiu erradamente que o 403 vinha do SameOriginMiddleware; a prova foi o log
(zero recusas de origem para a rota; heartbeat real 200 ×1113) e o `ImagePath` do serviço.
Confirmar no V6 **qual** ficheiro está no serviço antes de diagnosticar.

**Prova real usada no V3.4 (repetir no V6):** correr o script com o Python do venv do serviço e
`PYTHONPATH`/`WATCHERDB_DATA_DIR` apontados à raiz:
`Instance=<SERVER>;DatabaseName=<DB>;filegroup_name=<FG>` → deve imprimir "Histórico encontrado:
N dias" e gerar `scripts/reports/interactive_<FG>_<ts>_forecast.html/.csv` (já no .gitignore).

**Teste estático a portar:** `tests/unit/test_predictive_report_hardening_20260909.py`
(5 testes: sem Trusted_Connection no script, `sys.executable` + sanitizer no analisador, sanitizer
mascara caminhos e devolve a última linha, gate via Depends + 500, botão admin + guarda JSON).

---

## 5. O que o V6 deve saber sem aplicar

- **Achado aberto (V3.4 e provavelmente V6):** `modules/monitoring/backup_pattern_analysis.py`
  chama `sql_monitoring.execute_query(server_id, query, params=[database_name])` em duas linhas
  (~220 e ~368), mas a assinatura em `modules/monitoring/monitoring.py::SQLServerMonitoring.
  execute_query(self, server_id, query, database=None)` **não aceita `params`** → TypeError em
  toda a base, engolido; o contexto de padrões dos Backup Gaps está vazio desde sempre. Diff por
  preparar no V3.4; o V6 pode verificar já com
  `Select-String -Path modules -Pattern 'execute_query\([^)]*params=' -Recurse`.
- i18n do modal preditivo: no V3.4 saiu no lote F6a (`cb938f3`, 27 chaves `predict.*`) na mesma
  manhã; o V6 tem i18n própria — ver prompt F6a se existir.
- Cosmético não tocado: o script imprime `\n` literais (`print(f"\\n...")`).
