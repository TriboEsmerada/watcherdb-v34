# Prompt Completo — Sessao WatcherDB V3.2 (06/04/2026)

## Resumo Executivo
Sessao focada em: deploy comercial (PyArmor Pro), documentacao de uso, instaladores, investigacao de bugs no dashboard KPIs, filtro de ambiente, e renomeacao do botao Dashboard de KPIs para KPIs.

---

## 1. PYARMOR PRO — Proteccao de Codigo Comercial

### Licenca adquirida
- **Tipo:** PyArmor Pro ($89 USD, pagamento unico)
- **Licenca:** pyarmor-vax-011618
- **Titular:** Salomao Netto
- **Produto:** WatcherDB
- **Modos:** BCC (bytecode→C nativo) + RFT (rename functions/types)

### Activacao
```powershell
pip install -U pyarmor
pyarmor reg -p WatcherDB pyarmor-regcode-11618.txt
pyarmor reg pyarmor-regfile-11618.zip
```

### Teste de encriptacao
- Ficheiro `cors.py` encriptado com sucesso
- Codigo 100% ilegivel (bytecode encriptado)
- Runtime `pyarmor_runtime_011618.pyd` gerado

### Ficheiros de licenca (BACKUP CRITICO)
- `pyarmor-regcode-11618.txt` — codigo de activacao (max 10 usos)
- `pyarmor-regfile-11618.zip` — ficheiro de registo (max 100 devices)
- Backup em: `c:/Users/ue_e-snetto/Documents/projetosPython/`

---

## 2. SCRIPTS DE DEPLOY

### deploy/build.py (script de build)
- Corre PyArmor sobre todos os .py (~160 ficheiros activos)
- Copia sem proteger: templates/, static/, config/, database/
- Output: `dist/WatcherDB_V3.2/` pronto para copiar ao servidor
- Exclui: tests/, docs/, .env, __pycache__, REGISTRO_IGAC

### deploy/install_watcherdb.ps1 (PowerShell unificado — 801 linhas)
- Instala TUDO: WatcherDB V3.2 + Intelligence V1 Collector + BD
- Parametros: -SqlServer, -InstallPath, -Port, -SkipDB, -SkipCollector
- 17 passos: prereqs → copy → pip → DB → secrets → services → firewall → validate
- Cria backup automatico se instalacao existente
- Gera JWT + Fernet keys
- Configura conta de servico interactivamente

### deploy/install_wizard.py (Wizard Python — 654 linhas)
- Interface texto colorida com ASCII art
- 6 opcoes: Full Install, Web Only, Collector Only, DB Only, Verify, Uninstall
- Progress bars com [step/total] e simbolos ✓/✗
- Dry-run mode (-n flag)
- Verify: check 8 items (Python, ODBC, services, ports, health, DB, configs)

### deploy/setup_database.ps1 (Setup BD)
- Cria BD WatcherDB_Intelligence
- Executa 23 scripts SQL pela ordem correcta

---

## 3. DOCUMENTACAO

### docs/commercial/ (5 documentos comerciais)
| Documento | Conteudo |
|-----------|---------|
| ROI_CALCULATOR.md | 3 cenarios (50/100/200 srv), poupanca 36.400EUR/ano, ROI 264% |
| PRICING_MODEL.md | 4 tiers (Starter 150EUR/srv, Professional 100EUR, Enterprise 75EUR), perpetua |
| DPIA_DISCOVERY.md | DPIA do Discovery module, RGPD Art.28, medidas de mitigacao |
| PRODUCT_SHEET.md | One-pager comercial (problema, solucao, diferenciais, stack) |
| CONTRACT_CLAUSES.md | Clausulas: responsabilidade, IP, RGPD, SLA, termino, garantia |

### docs/guides/ (4 documentos de uso)
| Documento | Audiencia | Linhas |
|-----------|:---------:|:------:|
| WATCHERDB_OVERVIEW.md | Gestores | ~200 |
| WATCHERDB_OVERVIEW_EN.md | Managers | ~200 |
| USER_GUIDE_PT.md | DBAs/Tecnicos | ~3000 |
| USER_GUIDE_EN.md | DBAs/Technical | ~2500 |

---

## 4. BUGS CORRIGIDOS

### BUG CRITICO: Jobs contava TODOS como falhados
- **Ficheiro:** api/routers/intelligence/helpers.py linha 1720
- **Bug:** `if not is_failed: is_failed = True` — logica invertida que marcava TODOS os jobs como falhados
- **Fix:** `if not is_failed: continue` — skip rows sem coluna de falha
- **Impacto:** Jobs Falhados baixou de 275 para valor real (~272-280 reais)

### BUG MEDIO: Session restore ao abrir pagina
- **Problema:** Portal restaurava servidor/tab anterior em vez de abrir nos KPIs
- **Causa:** `restoreUserSession()` chamado incondicionalmente na linha 4160 (login flow), ignorando o check de reload
- **Fix:** Adicionado `performance.getEntriesByType('navigation')` check na linha 4160
- **Comportamento:** F5 restaura sessao, navegacao directa abre nos KPIs

### BUG MEDIO: Session restore duplicado
- **Causa:** Havia 2 locais que chamavam restoreUserSession() — linha 4160 (login) e linha 5296 (loadServers)
- **Fix:** Ambos os locais agora verificam `_isPageReload` antes de restaurar

### FIX: TempDB shrink recommendation
- **Ficheiro:** modules/monitoring/queries.py linha 230
- **Fix:** `WHEN s.database_name = 'tempdb' THEN 'OK'` — TempDB nunca recomenda shrink
- **Ficheiro:** api/routers/sql_queries.py
- **Fix:** TempDB shrink severity mudada de WARNING para INFO com aviso

---

## 5. INVESTIGACAO DE KPIs

### Views testadas (20 total)
- **OK (13):** DB Availability, Instance Availability, Blocked Sessions, Processes, FG Usage, TLog Usage, Disk Usage, Backups, Agent Jobs, Job Failures, AlwaysOn, Error Log, Server Offline
- **EMPTY (6):** Service Status, Blocked Users, Long Locks, Backup Status, DB IO Stats, Deadlocks
- **MISSING (1):** TempDB Usage (KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW nao existe — user a criar)

### Diagnostico TempDB
- View `KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW` nao existe na Intelligence DB
- Zero rows de tempdb em FG_USAGE_STG e FG_USAGE_ALL_STG
- Collector V1 exclui tempdb da recolha de filegroups
- Cards mostram 0 OK (graceful degradation) — user a criar view + collector

---

## 6. FILTRO DE AMBIENTE NOS KPIs

### Feature nova: dropdown de ambiente no dashboard
- **Localizacao:** Toolbar do dashboard, entre fonte de dados e botao Compacto
- **Opcoes:** Todos Ambientes | PRD | QLT | TST | PRD+QLT | PRD+TST | QLT+TST
- **Funcao:** filterKPIsByEnv() recalcula valores dos cards usando dados _by_env
- **Persistencia:** localStorage('kpi-env-filter')
- **Cores:** Verde=0/OK, Amarelo=WARNING, Vermelho=CRITICAL, Azul=info/total

### Cards cobertos pelo filtro (27 total)
- Disponibilidade: db-availability-abnormal, db-availability-total, db-availability-ok, instance-availability-off, instance-availability-ok, service-down
- Performance: blocked-sessions, blocked-users, processes-alarm, cpu-critical, memory-critical
- Espaco: transaction-logs-critical, transaction-logs-warning, filegroup-usage-critical, filegroup-usage-warning
- Disco: disk-file-system-critical, disk-file-system-warning, disk-latency-critical, tempdb-critical, tempdb-warning
- Backup: backup-failed, backup-delayed
- Jobs: jobs-failed, jobs-collisions
- Alta Disponibilidade: always-on-unhealthy, mirroring-unhealthy
- Server Offline: server-offline

---

## 7. RENOMEACAO: Dashboard de KPIs → KPIs

### Ficheiros alterados (25+)
- **templates/watcherdb_portal.html** — botao header, titulo dashboard, tab label
- **static/i18n/pt.json** — todas as chaves i18n PT
- **static/i18n/en.json** — todas as chaves i18n EN
- **static/i18n/es.json** — todas as chaves i18n ES
- **static/js/watcherdb_i18n.js** — traducoes v1
- **docs/** — 15 ficheiros de documentacao
- **scripts/** — i18n_final_keys.py, i18n_final_replace.py

### O que NAO foi alterado (nomes tecnicos internos)
- Nomes de funcoes/variaveis no Python (ex: `refreshDashboardKPIs()`)
- Comentarios de codigo tecnico (ex: `# KPI Dashboard cache`)
- Nomes de testes (ex: `TestKPIDashboard`)

---

## 8. SERVICO WINDOWS

### Porta alterada: 8446 → 8449
- 17 ficheiros em services/web_service/ actualizados
- Firewall reconfigurado

### Startup non-blocking
- Lifespan pesado (inventory, KPI cache, database discovery) movido para background task
- `asyncio.create_task(_background_prewarm())` com sleep(2) antes de comecar
- Porta abre em segundos, dados carregam em background

### ResponseValidationError handler
- Adicionado em services/web_service/server.py
- Previne crash quando response_model nao match com dados reais
- response_model mantido para documentacao OpenAPI

### Circuit breaker Intelligence removido
- Intelligence pool nao tem mais circuit breaker (causava login failures)
- Mantido retry com tenacity (3x, backoff 1-10s)
- SQL Server pool mantem circuit breaker (5 fails/30s)

---

## 9. AVALIACAO 20 PERGUNTAS DE INVESTIDOR

### Aplicavel ao V3.2 (9 items analisados)
| # | Pergunta | Estado |
|---|---------|:------:|
| 3 | Responsabilidade legal | VERMELHO — falta advogado |
| 4 | Hardware minimo | VERDE — 8GB RAM, 4 cores |
| 9 | Decomposicao de custos | AMARELO — falta pricing formal → CRIADO |
| 10 | ROI concreto | VERMELHO → CRIADO (ROI_CALCULATOR.md) |
| 11 | Vendor lock-in | VERDE — 100% self-hosted |
| 12 | Continuidade da empresa | VERMELHO — key-person dependency |
| 13 | Valor vs dashboard | VERDE — correlacao multi-sinal |
| 16 | Escala de producao | AMARELO — 100 srv testados |
| 20 | DPIA do Discovery | VERMELHO → CRIADO (DPIA_DISCOVERY.md) |

---

## 10. FICHEIROS CRIADOS/MODIFICADOS

### Novos (15)
```
deploy/build.py                          — Script build PyArmor
deploy/install_watcherdb.ps1             — Instalador PowerShell unificado
deploy/install_wizard.py                 — Wizard Python interactivo
deploy/setup_database.ps1                — Setup BD
deploy/DEPLOY_GUIDE.md                   — Guia de deploy
deploy/CHECKLIST_DEPLOY.md               — Checklist verificacao
docs/commercial/ROI_CALCULATOR.md        — ROI calculator
docs/commercial/PRICING_MODEL.md         — Modelo de pricing
docs/commercial/DPIA_DISCOVERY.md        — DPIA do Discovery
docs/commercial/PRODUCT_SHEET.md         — Product sheet
docs/commercial/CONTRACT_CLAUSES.md      — Clausulas contratuais
docs/guides/WATCHERDB_OVERVIEW.md        — Visao geral (gestores) PT
docs/guides/WATCHERDB_OVERVIEW_EN.md     — Overview (managers) EN
docs/guides/USER_GUIDE_PT.md             — Guia utilizador PT (3000 linhas)
docs/guides/USER_GUIDE_EN.md             — User guide EN (2500 linhas)
```

### Modificados (30+)
```
api/routers/intelligence/helpers.py      — Fix jobs bug (linha 1720)
modules/monitoring/queries.py            — TempDB shrink exclusion
api/routers/sql_queries.py               — TempDB shrink severity
templates/watcherdb_portal.html          — Session restore fix + filtro ambiente + rename KPIs
static/i18n/pt.json                      — Rename Dashboard de KPIs → KPIs
static/i18n/en.json                      — Rename KPI Dashboard → KPIs
static/i18n/es.json                      — Rename
static/js/watcherdb_i18n.js              — Rename
services/web_service/server.py           — ResponseValidationError handler
services/web_service/*.py,*.bat,*.yaml   — Porta 8449
watcherdb_main.py                        — Background prewarm, session restore
docs/ (15 ficheiros)                     — Rename Dashboard de KPIs → KPIs
```

---

## 11. ESTADO FINAL

| Metrica | Valor |
|---------|------:|
| Testes | 360 passed, 0 failed |
| Porta servico | 8449 |
| PyArmor | Pro activado (BCC+RFT) |
| Filtro ambiente | 27 cards cobertos |
| Documentacao | 4 guias (PT+EN) + 5 docs comerciais |
| Instaladores | 2 (PowerShell + Wizard Python) |
| Bugs corrigidos | 3 (jobs, session restore, TempDB shrink) |

---

*Sessao 06/04/2026 | WatcherDB V3.2*
