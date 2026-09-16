# 04 — Divergência 63 vs 62: comparação dos conjuntos (qa-externo, 2026-09-15)

Autor: qa-externo, só leitura. Verificação do orquestrador: ver 00_INDICE.md.

Nomes de host, instância e ID substituídos por `<srv-NN>` (01–63 = ordem de `config/servers.json`; 64–96 = só em `sql_servers.json`). A correspondência com os nomes reais ficou **fora do repo**, no scratchpad da sessão (`placeholder_map.json`), que é temporário. Nota do orquestrador: `<srv-51>` / `<srv-84>` = caso `SQLHDSSQLT301_I01` (host `SQLHDSQLT301`), confirmado pelo relatório 01.

**Resposta curta:** não há registo da barra lateral a devolver 62. Todos os registos do serviço dizem 63. O 62 aparece noutros sítios. O total do dashboard é uma **soma** de dois conjuntos que se podem sobrepor, não uma contagem de instâncias únicas.

## 1. Contagens por fonte

| Fonte | Registos | enabled | Sem id | Sem credenciais | Duplicados (id / host\instância) | Ambiente (prod/qual/test) |
|---|---|---|---|---|---|---|
| `config/servers.json` → `monitored_servers` | 63 | chave ausente em 61, `true` em 2, `false` em 0 | 0 | 0 | 0 / 0 | 42 / 15 / 6 |
| `config/sql_servers.json` → `servers` | 95 | schema sem a chave | 0 | schema sem credenciais | 0 / 0 | 53 / 24 / 18 |
| `config/alwayson_inventory.json` → `ag_servers` | 42 (42 únicos) | — | sem id | — | 0 | — |
| Simulação `/api/v3/servers` a partir do ficheiro (fallback) | **63** devolvidos, 0 excluídos | — | — | — | — | — |
| Runtime V3.4, `logs/service_stderr.log` e `.log.1` | **63** (`source=db`), nunca 62 | — | — | — | — | — |
| Runtime V3.3, `WATCHERDB_V3.3/logs/service_stderr.log` | **63** (`source=db`), nunca 62 | — | — | — | — | — |
| Dashboard, "Instances OK" no arranque (só log) | 50, 54, **62** e **63** em momentos diferentes | — | — | — | — | — |

63 registos de `servers.json` = 58 hosts distintos (host ≠ instância).

## 2. Diferenças entre conjuntos

**Só em `servers.json` (1):** `<srv-51>` — alias. O `id` não bate com `HOST_INSTANCE` (mais 1 carácter, "SS em vez de S" do `@@SERVERNAME`). Tem `sql_servername_alias` igual ao id. O mesmo host\instância existe em `sql_servers.json` com outro id (`<srv-84>`). Pelo par host\instância, `servers.json` está contido em `sql_servers.json`.

**Só em `sql_servers.json` (33 ids = 32 host\instância reais):** `<srv-64>` … `<srv-96>` (12 test, 11 prod, 10 quality); `<srv-84>` = mesmo host\instância que `<srv-51>`. Não estão no inventário que o portal lê.

**Nas duas por ID: 62.**

**AlwaysOn:** 42 entradas coerentes. 30 em `servers.json` = exactamente as 30 com `has_alwayson=true`. 12 só em `sql_servers.json`. `<srv-51>` não aparece no inventário AlwaysOn.

## 3. FACTOS

1. **Barra lateral** = `filteredServers.length` (`templates/watcherdb_portal.html:6465`), de `/api/v3/servers` (`:6334`, `:6396`); pesquisa activa reduz (`:7114`).
2. **`/api/v3/servers`** (`watcherdb_main.py:1138-1203`): `repo.servers(enabled_only=False, require_credentials=True)` (`:1155`); salta `enabled` falso (`:1164`) e sem id (`:1168`); sem dedup.
3. **InventoryRepo**: default BD (`settings.py:61`); query `tenant_id='default' AND is_active=1` (`:42`); `has_credentials` só se o ID está em `servers.json` com password (`:151-164`, `:176-182`); aviso `[INVENTORY_REPO] N servidor(es) na BD sem credenciais` (`:184`) **não aparece em nenhum log** V3.4/V3.3; fallback `servers.json` (`:244-248`) dá 63.
4. **Total "Instâncias"** = `totI = ok_count + off_count` (`watcherdb_portal.html:36777`, `:36826`). Soma, não união:
   - `ok_count` = `COUNT(DISTINCT Instance)` em `KPI_MSSQL_INST_AVAILABILITY_ACTIVE` com `Is_Available=1` (`helpers.py:1228-1234`);
   - `off_count` = `COUNT(DISTINCT Instance)` em `KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW` com `Ping_OK=0` (`:1238-1244`);
   - nenhuma usa `metadata.monitored_server`.
5. **`collect_service_status` soma ao `off_count`** (`helpers.py:1938-1941`) instâncias com `Services_Down_Count>0` que não estejam na lista offline. Comparação exacta (maiúsculas, `\` vs `_`) (`:1921-1926`). Podem ter `Is_Available=1` e já contar em `ok_count`.
6. **Condição de corrida**: `collect_instance_availability` e `collect_service_status` no mesmo `asyncio.gather` (`api/routers/intelligence_kpis.py:897-913`). Se o serviço terminar primeiro, `helpers.py:1335` apaga as extra; se depois, somam-se. O total pode variar entre pedidos sem mudança na frota.
7. **Sem teste** que ligue `instance_availability`/`totI` ao inventário.
8. **Runtime**: 8434 a ouvir (PID 43820, arrancado 15/09 16:52); 8433 não. GETs sem token → `401 Token nao fornecido`. `WATCHERDB_QA_URL`/`WATCHERDB_QA_USER` não definidos.

## 4. HIPÓTESES

- **H1 (mais provável para o 63 do dashboard):** 62 OK + 1 "off" que também está OK (serviço em baixo, p.ex. SQL Agent, ou em `OFFLINE_GROUPED_VIEW`) → 62 únicas contadas como 63.
- **H2:** `<srv-51>` com dois nomes pode entrar duas vezes, ou nenhuma, num `COUNT(DISTINCT Instance)`. Não provado.
- **H3:** o 62 da barra lateral foi lido com pesquisa activa, ou com 1 registo `is_active=0`/`enabled=0` na BD (sem aviso no log). Não provado.
- **H4:** a interseção por ID `servers.json` ∩ `sql_servers.json` = 62; um consumidor que cruze por ID com `sql_servers.json` perde `<srv-51>`. Não encontrado no caminho da barra lateral nem do total.

## 5. PENDENTE

- **Runtime:** conta viewer/dba (nunca admin) para GET `/api/v3/servers` e `/api/intelligence-kpis/dashboard` (`instance_availability.ok_count`, `off_count`, `instances[]`), 3 repetições para ver oscilação (facto 6).
- **BD:** não houve ligação. `watcherdb/core/settings.py:51` tem `intelligence_use_windows_auth: bool = True` por omissão; leitura do `.env` negada → sem garantia de `sql_monitoring`.
- **Definições das vistas em produção** podem diferir do repo (`database/FIX_SERVER_OFFLINE_RECONCILE_COLLECTION_SUCCESS.sql:196`).

**SELECTs para o owner correr como `sql_monitoring`** (WatcherDB_Intelligence, só leitura):

```sql
-- Q1 inventario (fonte da sidebar)
SELECT COUNT(*) total,
       SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) ativos,
       SUM(CASE WHEN is_active=1 AND enabled=1 THEN 1 ELSE 0 END) ativos_enabled,
       SUM(CASE WHEN sql_servername_alias IS NOT NULL THEN 1 ELSE 0 END) com_alias,
       COUNT(DISTINCT UPPER(instance_id)) ids_distintos
FROM metadata.monitored_server WITH (NOLOCK) WHERE tenant_id='default';

SELECT instance_id, enabled, is_active, environment,
       CASE WHEN sql_servername_alias IS NULL THEN 0 ELSE 1 END AS has_alias,
       last_seen_in_source_at, updated_at
FROM metadata.monitored_server WITH (NOLOCK)
WHERE tenant_id='default' AND (is_active=0 OR enabled=0 OR sql_servername_alias IS NOT NULL)
ORDER BY instance_id;

-- Q2 contagens cruas exactamente como o dashboard
SELECT (SELECT COUNT(DISTINCT Instance) FROM dbo.KPI_MSSQL_INST_AVAILABILITY_ACTIVE WITH (NOLOCK) WHERE Is_Available=1) AS ok_count,
       (SELECT COUNT(DISTINCT Instance) FROM dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WITH (NOLOCK) WHERE Ping_OK=0) AS off_count,
       (SELECT COUNT(*) FROM dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK) WHERE Services_Down_Count>0) AS svc_down_rows;

-- Q3 colunas da vista de servicos
SELECT TOP 0 * FROM dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW;

-- Q4 conjuntos normalizados: so' linhas que NAO sao "inventario + OK + nao off + sem servico em baixo"
;WITH inv AS (SELECT UPPER(instance_id) k FROM metadata.monitored_server WITH (NOLOCK)
              WHERE tenant_id='default' AND is_active=1 AND enabled=1
              UNION
              SELECT UPPER(REPLACE(sql_servername_alias,'\','_')) FROM metadata.monitored_server WITH (NOLOCK)
              WHERE tenant_id='default' AND is_active=1 AND sql_servername_alias IS NOT NULL),
ok  AS (SELECT DISTINCT UPPER(REPLACE(LTRIM(RTRIM(Instance)),'\','_')) k FROM dbo.KPI_MSSQL_INST_AVAILABILITY_ACTIVE WITH (NOLOCK) WHERE Is_Available=1),
off AS (SELECT DISTINCT UPPER(REPLACE(LTRIM(RTRIM(Instance)),'\','_')) k FROM dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WITH (NOLOCK) WHERE Ping_OK=0),
svc AS (SELECT DISTINCT UPPER(REPLACE(LTRIM(RTRIM(Instance)),'\','_')) k FROM dbo.KPI_MSSQL_SERVICE_STATUS_AGG_VIEW WITH (NOLOCK) WHERE Services_Down_Count>0), -- ajustar coluna conforme Q3
u AS (SELECT k,1 i,0 o,0 f,0 s FROM inv UNION ALL SELECT k,0,1,0,0 FROM ok
      UNION ALL SELECT k,0,0,1,0 FROM off UNION ALL SELECT k,0,0,0,1 FROM svc),
g AS (SELECT k, MAX(i) in_inv, MAX(o) in_ok, MAX(f) in_off, MAX(s) in_svc_down FROM u GROUP BY k)
SELECT * FROM g WHERE NOT (in_inv=1 AND in_ok=1 AND in_off=0 AND in_svc_down=0) ORDER BY k;

-- Q5 definicao instalada das vistas (requer VIEW DEFINITION)
SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW')) AS offline_view,
       OBJECT_DEFINITION(OBJECT_ID('dbo.KPI_MSSQL_INST_AVAILABILITY_ACTIVE'))    AS active_obj;
```

Ler a Q4: `in_ok=1` com `in_off=1` ou `in_svc_down=1` confirma H1; `in_inv=0` com `in_ok=1` indica nome que não bate com o inventário (H2).

## 6. O que tornaria isto verificável de vez

- Teste unitário com `collect_instance_availability` + `collect_service_status` e dados falsos em que a mesma instância está OK e com serviço em baixo: falha se `ok_count + off_count` > instâncias únicas, e se o resultado mudar com a ordem de conclusão.
- Gate em runtime com conta QA: `totI` ≤ `len(/api/v3/servers)`; diferença listada por instância.

O registo responsável pela diferença de 1 fica **por identificar** até correr a Q4 ou os GET autenticados.
