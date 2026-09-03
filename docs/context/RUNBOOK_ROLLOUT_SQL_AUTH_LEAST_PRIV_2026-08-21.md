# Runbook — Rollout do SQL Auth least-privilege (Fase 1)

**Data:** 2026-08-21 · **Autor:** sessão AI (desenho v33-specialist, implementação revista pelo owner)
**Objetivo:** o produto passa a ligar aos servidores monitorizados por **SQL Auth com
`sql_monitoring` least-privilege**, em vez de `Trusted_Connection` (Windows Auth) —
removendo a violação da Regra de Ouro #2 — **sem apagar o monitoring da frota**.

---

## Porque um gate de rollout (e não a flag do servers.json)

`config/servers.json` **já tem `use_windows_auth: false` + `username: sql_monitoring`
+ `password: encrypted:...` nas 63 entradas + master**. Se o código ligasse o branch
de auth diretamente a essa flag, o **próximo restart mudava os 63 servidores para SQL
Auth de uma vez** — e onde os GRANTs least-priv ainda não estão aplicados ao
`sql_monitoring`, o login falha (18456) e o monitoring apaga-se.

Por isso a Fase 1 introduz um **gate separado, explícito e default-vazio**:
`api/connection_pool.py::_sql_auth_enabled_for(server_id)`, alimentado por
`config/sql_auth_rollout.json`. Um servidor só liga por SQL Auth se estiver **nessa
allowlist**. Deploy do código com allowlist vazia = **zero mudança** (todos Trusted).

**Invariante de ouro:** `use_windows_auth:false` no JSON ≠ "grants já aplicados neste
servidor". Só a allowlist significa "pronto". Nunca inverter a ordem.

---

## Formato da allowlist — `config/sql_auth_rollout.json`

```json
{ "sql_auth_servers": ["CAGENPRD06_I06", "SQLHDSTST505_I01"] }
```
- Lista de `server_id`s (case-insensitive; tolera `_` ↔ `\`).
- Valor especial `"*"` liga SQL Auth para **todos** — usar só quando a frota inteira
  tiver os grants aplicados e validados.
- Ficheiro ausente / inválido = allowlist vazia (**fail-closed**, todos Trusted).
- Recarrega quando o ficheiro muda (sem restart necessário para adicionar servidores).

---

## Sequência POR SERVIDOR (nunca inverter)

Para cada `server_id`, por esta ordem:

1. **Aplicar os grants** — correr `docs/security/LEAST_PRIVILEGE_SETUP.sql` nesse
   servidor, com o login-alvo = **`sql_monitoring`** (ver secção seguinte).
2. **Validar** — ligar como `sql_monitoring` e correr as 6 leituras do produto
   (xp_readerrorlog, sysjobactivity, syssessions, dm_os_wait_stats, backupset,
   query_plan) — todas têm de devolver linhas, `is_sysadmin = 0`. (Mesmo teste que
   validou a Fase 0 em 2026-08-21.)
3. **Só então** adicionar o `server_id` a `config/sql_auth_rollout.json`.
4. **Restart/observar** — no próximo `get_connection` daquele pool_key o produto liga
   por SQL Auth. Confirmar no portal que o servidor continua a reportar.

**Canário:** 1 servidor **não-produção** primeiro (ex. `SQLHDSTST505_I01`, o de teste da
Fase 0). Depois lotes de 5–10. **Produção por último.** Meta final: allowlist = `"*"` e,
aí, remover o `Trusted_Connection` como fallback (fecha a Regra de Ouro #2 por completo).

---

## Aplicar o script à conta `sql_monitoring` (adaptação da Fase 0)

O `LEAST_PRIVILEGE_SETUP.sql` foi **validado em teste com um login descartável
`WatcherDBReader`**. Mantém-se assim (é o artefacto de prova). Para PRODUÇÃO, o alvo é a
conta canónica `sql_monitoring`, que **já existe** na frota:

- **Find/replace** `WatcherDBReader` → `sql_monitoring` no script antes de correr, OU
  correr as mesmas declarações GRANT/`CREATE USER`/`ALTER ROLE` com esse nome.
- **NÃO** correr o bloco `CREATE LOGIN` (o `sql_monitoring` já existe; criar dava erro).
- **Rollback = REVOKE, não DROP.** `sql_monitoring` é a conta partilhada — **nunca**
  `DROP LOGIN`. Reverter um servidor = remover da allowlist (volta a Trusted); reverter
  os grants (se necessário) = `REVOKE`/`ALTER ROLE ... DROP MEMBER`, um a um.

> Os grants em si (VIEW SERVER STATE/DEFINITION/DATABASE, msdb backup*/sysjobs*,
> `SQLAgentReaderRole`, `xp_readerrorlog`, `SHOWPLAN`) são idênticos aos validados —
> o nome do login é só um rótulo; o **conjunto** de permissões é que foi provado.

---

## Diagnóstico durante o rollout

- Hoje o `get_connection` trata **qualquer** exceção como "offline" e quarentena 60s —
  isso **mascara um grant em falta** (18456 / SQLSTATE 28000) como "servidor em baixo".
  Durante o rollout, ao ver um servidor "offline" logo após entrar na allowlist,
  suspeitar **primeiro de grant em falta**, não de rede.
- Fix lateral aplicado nesta wave: `watcherdb_alwayson_check.py::_decrypt_password`
  passou a usar a cadeia DPAPI completa (Tiers 3→2→1) — antes, no serviço packaged,
  devolvia o ciphertext cru e os checks AlwaysOn falhavam em silêncio com 18456.

---

## Rollback

- **Por servidor:** remover o `server_id` de `config/sql_auth_rollout.json`. O próximo
  `get_connection` desse pool_key volta a Trusted. Conexões já no pool (até
  `POOL_CONNECTION_LIFETIME`, ~30 min) continuam no modo com que foram abertas —
  aceitável; para forçar já, reiniciar o serviço.
- **Global:** allowlist vazia = tudo Trusted (estado de deploy inicial).

---

## Ficheiros desta wave (Fase 1)

- `api/connection_pool.py` — branch em `_build_connection_string` + `_sql_auth_enabled_for`
  + `_load_sql_auth_rollout` (gate default-vazio).
- `tests/unit/test_connection_pool.py` — `TestSQLAuthRollout` (5 testes: gate on→SQL Auth,
  gate off→Trusted apesar do JSON, creds incompletas→fallback, ficheiro ausente→fail-closed,
  leitura da allowlist + wildcard).
- `modules/monitoring/watcherdb_alwayson_check.py` — `_decrypt_password` via cadeia DPAPI.
- `config/sql_auth_rollout.json` — **a criar quando o rollout começar** (não versionar se
  contiver nomes de servidores sensíveis; alinhar com a política do servers.json).

### Follow-up conhecido (não bloqueia)
- `api/routers/network_diagnostics.py:180` — terceira cópia do branch de creds
  (connection_pool + alwayson + este). Candidato a um helper único de resolução de
  credenciais partilhado, para não haver drift entre os três caminhos.
