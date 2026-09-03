# Auditoria Empacotamento + Instalador Windows — FASE 0 (Raio-X)

Data: 2026-07-03 | Agente: orquestrador (Fable 5) + 3 Explore agents
Gate: APROVADO pelo owner 2026-07-03 ("pode seguir o plano")
Decisões do gate: alvo = cliente pagante banking (DBA do cliente instala);
baseline = pipeline PyArmor+PyInstaller+WiX existente (validar/endurecer, não
reavaliar do zero); dispatch specialists aprovado (modo B GO); persistência
em docs/context/ aprovada.

## (a) O que a app é / utilizador final

WatcherDB V3.3 Standard Edition: monitoring SQL Server 100% on-premise,
serviço Windows FastAPI porta 8433, portal SPA vanilla JS, dados da BD
partilhada `WatcherDB_Intelligence` (V1 collector NÃO faz parte do pacote).
Fluxo desenhado (deploy/INSTALL_FLOW_V0.2.md:322-334): vendor builda/assina/
emite license.dat; cliente (DBA+admin) corre preflight, MSI e wizards.

## (b) Modelo de processos

- PROD: SCM → `WatcherDBWebServiceV33` (pywin32, services/web_service/service.py:28-31),
  processo único 1 worker; `os.chdir(ROOT_DIR)` (server.py:26); thread Uvicorn
  → `services.web_service.server:app` (importa watcherdb_main.app + middlewares),
  bind 0.0.0.0:8433 (services/web_service/config.yaml:10-11); heartbeat 30s →
  service_health.txt; APScheduler in-process com 1 job (job_failures_collector,
  5 min, fan-out pyodbc ~20 servers → KPI_MSSQL_JOB_FAILURES_STG); asyncio tasks
  prewarm/discovery(+300s)/kpi-rewarm(50s); threads cache persist → watcherdb_cache.db
  (pickle, path relativo ao CWD, cache.py:24,48); WebSocket /ws.
- DEV: start_server_dev.bat → python watcherdb_main.py → 0.0.0.0:8000.
- SEM lock de instância única (grep mutex/pidfile: zero). Escreve em runtime no
  diretório de instalação: cache pickle, cache/dashboard_snapshot.json, reescrita
  de config/sql_servers.json + servers.json (watcherdb_main.py:1177,1266),
  SQLite tap_servers.db, logs em services/web_service/logs/.

## (c) Dependências

- Python 3.11.9 real (.venv-build/pyvenv.cfg); requires-python >=3.11.
- Core: fastapi, uvicorn[standard], pyodbc, aioodbc, pydantic2+settings, pandas,
  numpy, openpyxl, plotly, jinja2, python-jose, passlib/bcrypt, httpx/requests,
  psutil, pywin32/wmi/winkerberos (Windows-only SEM platform markers), ldap3,
  pyyaml, python-dotenv, slowapi, tenacity, pybreaker, cachetools, sqlparse,
  structlog, prometheus+OTel, alembic, apscheduler, websockets, aiofiles.
  redis>=5 declarado mas OFF por default (lazy import). pyproject.toml:42 ainda
  lista scikit-learn (removido do requirements por política zero-AI Std) — drift.
- Binário externo único: ODBC Driver 17 for SQL Server. Setting em settings.py:43
  mas string "Driver 17" HARDCODED em ~12 call sites (async_db.py:25, routers,
  alembic/env.py:36); preflight aceita 17|18 → divergência.
- Rede: SQL Server via Trusted_Connection=yes SEMPRE (connection_pool.py:485;
  SQL-auth existe mas nunca chamada — CRÍTICO já registado 2026-07-02);
  AD/LDAP opcional; SMTP/Teams/Slack opcional; OTLP opcional.
- Windows mínimo: Server 2016+/Win10/11 + .NET 4.7.2+ + ODBC 17/18
  (preflight_target.ps1); prereqs_check.py NÃO verifica Windows/.NET.
- Licença: license.dat Ed25519 em C:\ProgramData\WatcherDB\; runtime completo
  em watcherdb/licensing/ (validator, CRL fail-open, grace period).

## (d) Pipeline de packaging existente (builds 13-17/05/2026)

- PyArmor Pro (BCC+RFT) + PyInstaller ONEDIR: buildou OK (build_run.log).
- MSI WiX v3, UpgradeCode estável, MajorUpgrade: buildou OK 37.6 MB — NotSigned
  (Get-AuthenticodeSignature verificado). Signing DigiCert KeyLocker: scripts
  prontos, credenciais nunca configuradas.
- SBOM CycloneDX gerado. install-package zip existe (dist/, 17/05).
- Updater cliente NÃO existe (só produtor de pacotes; dist/update/ nunca gerado).
- BUG PyArmor: dashboard_api.py falhou obfuscação (relative-import overflow) e
  build.py:245-247 shipou-o SEM proteção via fallback silencioso.
- MSI: ServiceInstall nativo (NetworkService default, recovery 30s/60s), cria
  C:\ProgramData\WatcherDB\ ACL hardened, preserva ProgramData no uninstall.
  NÃO configura firewall (incidente 2026-06-12 provou necessidade).
- install_wizard.py / install_production.ps1 / install_watcherdb.ps1: stubs
  deprecados (audit S2-8).

## Incertezas declaradas

1. .env.example ilegível na sessão (permissões .env*) — chaves reconstruídas de
   settings.py+config.yaml; owner deve comparar manualmente.
2. App/testes não executados na Fase 0 — verificação de arranque proposta na Fase 1
   como comando para o owner.
3. dist/ de maio está ~7 semanas atrás do source atual.
