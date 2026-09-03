# RUNBOOK Etapa 1 — Estado e identidade (empacotamento)

Data: 2026-07-03 | Modo consultor: owner executa. Branch: wave-packaging-etapa0.
Itens: 1.1 resolver WATCHERDB_DATA_DIR + 1.6 .env 3-tier (EXECUTÁVEL JÁ);
1.2 identity flip, 1.3 sanitização bundle, 1.4 DPAPI, 1.5 mutex (seguem).

## 1.1 + 1.6 — Desenho

Novo módulo watcherdb/core/paths.py (criado pelo aplicador): resolução 3-tier
espelhando licensing/crl.py — (1) env WATCHERDB_DATA_DIR, (2) frozen →
C:\ProgramData\WatcherDB, (3) dev → raiz do projeto. GARANTIA: em dev,
sem env var, tudo resolve para onde sempre resolveu (zero mudança), com
UMA exceção deliberada e inofensiva: o pickle watcherdb_cache.db passa da
raiz para <root>\cache\ (regenerável; nenhum teste o referencia).

Decisões de âmbito:
- watcherdb_intelligence.py (15 ocorrências): NÃO migrado — ficheiro morto,
  sai do bundle na Etapa 1.3. Migrá-lo seria polir código que não shippa.
- RedisLikeCache.__init__ resolve paths RELATIVOS via cache_dir() — um único
  edit cobre TODOS os call-sites do cache (backup/cpu/memory/dashboard_api/
  inventory_manager/cache_factory ficam corretos sem tocar neles).
- ACHADO NOVO (B0-4 extensão): inventory_manager.py:31 tinha
  C:\Server_Inventory hardcoded como default + mkdir — criava pastas na
  máquina do cliente. Migrado para inventory_dir() (dev mantém o path
  histórico; frozen → ProgramData\WatcherDB\inventory).
- dotenv (watcherdb_main:22-28): cadeia .env 3-tier INLINE (sem importar
  watcherdb.*) porque tem de correr ANTES do settings singleton ler o env.
- schema_manager: sem mudança (db_path é injetado pelo inventory_manager).

Edits aplicados pelo script (âncoras exatas, R1-R7):
R1 cache.py __init__ resolve relativo→cache_dir()      (B1-6)
R2 watcherdb_main dotenv 3-tier                        (B1-8/1.6)
R3 watcherdb_main _CONFIG_DIR via config_dir()         (B0-4)
R4 SERVERS_INVENTORY_PATH via _CONFIG_DIR              (B0-4)
R5 custom_queries via _CONFIG_DIR (2 sites)            (B1-7)
R6 helpers._SNAPSHOT_PATH via cache_dir()              (B0-4)
R7 inventory_manager default → inventory_dir()         (B0-4 novo)

## Execução

```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
python "C:\Users\ue_e-snetto\AppData\Local\Temp\claude\c--Users-ue-e-snetto-Documents-projetosPython-WATCHERDB-V3-3\43da03f6-3535-42f4-8f8b-cad42baa685b\scratchpad\apply_etapa1_1.py"
python -m pytest tests/unit -q --no-cov
```
Critério pytest: as MESMAS 7 falhas do baseline da Etapa 0.

Smoke de arranque dev (verifica resolução de paths ao vivo):
```powershell
python watcherdb_main.py
```
Esperar /health responder em :8000, Ctrl+C. Verificar que apareceu
<root>\cache\watcherdb_cache.db (novo local) e que config/ continua a ser
lida da raiz.

Commit:
```powershell
git add watcherdb/core/paths.py watcherdb/core/cache.py watcherdb/core/inventory_manager.py watcherdb_main.py api/routers/intelligence/helpers.py
git commit -m 'fix(packaging): etapa 1.1+1.6 resolver WATCHERDB_DATA_DIR' -m 'novo watcherdb/core/paths.py 3-tier (env, ProgramData frozen, raiz dev) espelhando licensing/crl.py; RedisLikeCache resolve paths relativos via cache_dir (B1-6, cobre todos os call-sites); config editavel via config_dir (B0-4); snapshot via cache_dir; .env 3-tier inline pre-settings (B1-8); inventory_manager sem C:\Server_Inventory hardcoded (B0-4 novo achado). watcherdb_intelligence.py fora do ambito (ficheiro morto, sai na 1.3). Ver docs/context/auditorias/AUDITORIA_EMPACOTAMENTO_2026-07-03_RUNBOOK_ETAPA1.md'
```

Rollback: git restore dos 5 ficheiros + apagar watcherdb/core/paths.py.

## 1.3 — Sanitização do bundle + first-run bootstrap (B0-3) [PREPARADA]

Aplicador: scratchpad/apply_etapa1_3.py (6 edits B1-B6 + cria servers.json.template).
Estratégia (âncoras verificadas nas linhas reais):
- B1 build.py: remove watcherdb_intelligence.py de PROTECT_FILES (morto, zero
  imports confirmado por grep, ~277KB IP vendor). Ficheiro fica no repo (dev
  imports OK), só NÃO entra no bundle.
- B2 build.py copytree: ignore dos 5 *.json vivos (servers, sql_servers,
  sql_servers_new, alwayson_inventory, custom_queries). alerts.json MANTÉM-SE
  (thresholds, não é infra leak).
- B3 build.py: remove auto-create de .env no bundle (B1-8; .env vive em ProgramData).
- B4 spec: config bundled file-by-file com denylist dos 5 leaky + *.bak/*.backup.
  (config lido do source pelo spec; filtro necessário aqui além do build.py).
- B5 paths.py: bootstrap_config() — seed skeletons vazios (servers/sql_servers/
  custom_queries) em config_dir() se ausentes. Idempotente, no-op em dev.
  NÃO lê templates (os *.json.template têm /* */ no fim, JSON inválido — são docs).
- B6 watcherdb_main: chama bootstrap_config() após _CONFIG_DIR.
- servers.json.template criado (não existia; par doc do ficheiro stripado).
alwayson_inventory.json: stripado mas SEM bootstrap — degrada com try/except
(alwayson.py:736 confirmado). Cliente configura se usar AlwaysOn.

Execução:
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
python "C:\Users\ue_e-snetto\AppData\Local\Temp\claude\c--Users-ue-e-snetto-Documents-projetosPython-WATCHERDB-V3-3\43da03f6-3535-42f4-8f8b-cad42baa685b\scratchpad\apply_etapa1_3.py"
python -m pytest tests/unit -q --no-cov
```
Critério pytest: mesmas 7 falhas baseline.

Teste do bootstrap (frozen-like, temp dir — verifica skeletons + parse):
```powershell
cd "c:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
$env:WATCHERDB_DATA_DIR="$env:TEMP\wdb_boottest"
Remove-Item -Recurse -Force $env:WATCHERDB_DATA_DIR -ErrorAction SilentlyContinue
python -c "from watcherdb.core.paths import bootstrap_config, config_dir; import json; bootstrap_config(); c=config_dir(); [print(n, 'OK', type(json.load(open(c/n,encoding='utf-8'))).__name__) for n in ['servers.json','sql_servers.json','custom_queries.json']]"
Remove-Item -Recurse -Force $env:WATCHERDB_DATA_DIR -ErrorAction SilentlyContinue
Remove-Item Env:\WATCHERDB_DATA_DIR
```
Esperado: 3 linhas "... OK dict/dict/list". (Confirma que o skeleton parseia.)

Smoke dev (bootstrap no-op, config lida da raiz):
```powershell
python watcherdb_main.py   # /health :8000, Ctrl+C
```

Commit:
```powershell
git add deploy/build.py deploy/watcherdb.spec watcherdb/core/paths.py watcherdb_main.py config/servers.json.template
git commit -m 'fix(packaging): etapa 1.3 sanitizacao do bundle (B0-3)' -m 'remove watcherdb_intelligence.py de PROTECT_FILES (morto, IP vendor); exclui 5 config/*.json vivos (99 servers reais + Fernet) do build.py copytree E do spec DATAS; bootstrap_config() seed skeletons vazios em config_dir frozen first-run; nao cria .env no bundle (B1-8); servers.json.template novo. alerts.json mantem-se (config). Ver docs/context/auditorias/AUDITORIA_EMPACOTAMENTO_2026-07-03_RUNBOOK_ETAPA1.md'
```

## Pendentes da Etapa 1 (diffs preparados a pedido, por ordem)

1.2 identity flip sql_monitoring — APROVADO-COM-CONDIÇÕES pelo v1-intel
    (ver VETO_1.2.md). GATED em ops SQL do owner (GRANTs Gap 1+3) antes do
    diff de código. Runbook DBA a preparar quando owner der GO à frente SQL.
1.4 secrets DPAPI machine-scope em secrets\ (reusa services/secrets.py)
1.5 named mutex instância única
