# Inventário de servidores — fonte única `servers.json` (wave 19-20/08/2026)

Estado: **em produção** (V1 collector + V3.3 portal). Plano e histórico completo:
`docs/context/PLANO_SERVERS_JSON_FONTE_UNICA_2026-08-19.md`. Gates: sql-deep-reviewer
(modelo) + watcherdb-v1-intel-specialist (veto holder; VETO a `databases[]` como scope).

## Arquitectura (fluxo)

```
V1/config/servers.json  (CANÓNICO — única fonte de verdade; edição manual do owner)
   │  discover_databases (1×/dia): sys.databases → databases[] no JSON
   │  (único escritor automático; atomic write + backup config/_backup/)
   ▼
InventoryProvider (leitor único: validação warn+skip, ENV_ALIASES, hash s/ voláteis)
   │                                    │
   │ sync_monitored_servers (10 min,    │ collectors (base_collector + agent_jobs/2pc/
   │ SKIP por hash; full 03h + @Purge)  │ ping/kpi/disk_unallocated): membership+env
   ▼                                    ▼ do provider; creds do ServerManager
WatcherDB_Intelligence:
   metadata.monitored_server ─1:N─ monitored_server_database   (SECÇÃO 34)
   metadata.server_sync_run  ─1:N─ server_sync_audit (changed_cols por UPDATE)
   projecções transição: server_config (row base) · KPI_MSSQL_INST_ENVS (sem DELETE)
   usp_reconcile_inst_envs (SECÇÃO 17): lê monitored_server; DELETE c/ guarda 30d
   ▼
V3.3 portal: services/inventory_repo.py (cache 60s; inventory_source db|file;
   has_credentials × ficheiro local) → /api/v3/servers (source=db), sidebar,
   _load_monitored_servers, monitoring.py
```

## Regras que não se quebram

- `databases[]` é **catálogo** (o que existe), nunca scope de coleta — os KPIs per-DB
  enumeram `sys.databases` ao vivo (veto v1-intel 19/08). Exclusões: `WDB_KPI_MUTE`.
- Credenciais **nunca** na BD. V1 = Fernet (`.encryption_key`); V3.3 = ficheiro local
  próprio (DPAPI) só para creds; servidor na BD sem creds locais fica fora da sidebar.
- Desactivação **só por ausência da run processada** (nunca por idade); guarda de frota
  20 %; staging vazia = FAILED sem mutar.
- Zero `Trusted_Connection` na coleta; master sem SQL auth = raise (Regra de Ouro #2).
- Suporte por versão: pleno 2012+; 2005/2008 = parcial (availability OK — uptime via
  tempdb `create_date`; nunca `sqlserver_start_time`/`CONNECTIONPROPERTY` sem gate).
- Porta dinâmica: aprendida em `WDB_INSTANCE_TCP_PORT`; se falhar → retry via Browser
  → re-aprende (auto-heal, caso PRD214 pós-patch).

## Rollbacks

| Camada | Rollback |
|---|---|
| Portal | `INVENTORY_SOURCE=file` (env) ou `settings.inventory_source` |
| Sync | `dry_run: true` no config.yaml + Restart-Service |
| BD | BAKs `*_BAK_20260819`; objectos novos sem consumidores externos = DROP |
| Collectors | fail-open automático para filtro env local se o provider falhar |

## Casos aprendidos (ver docs/context/SOLUCOES.md)

OATXP01 (SQL 2005: coluna 2008+ fora do gate), SQLHDSPRD214 (porta stale pós-patch),
PRD502 (2008 R2 TLS: fora por decisão), 31 fantasmas do sql_servers.json arquivado.
