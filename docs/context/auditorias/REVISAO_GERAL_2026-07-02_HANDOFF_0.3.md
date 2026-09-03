# Handoff — Mini-wave 0.3 (identity flip sql_monitoring)

> Data: 2026-07-02 | Para: `watcherdb-v1-intel-specialist` (veto BD partilhada) +
> `watcherdb-deploy-architect` (service account / xp_readerrorlog).
> Contexto completo: `auditorias/REVISAO_GERAL_2026-07-02_MINIWAVE_0.3_identity_flip.md`.

## Resumo em 3 linhas

O V3.3 corre em runtime com `Trusted_Connection=yes` (conta de domínio com dbo), violando a
Regra de Ouro #2. Queremos flip para `sql_monitoring` (SQL Auth, least-privilege). A
verificação mostrou que **a maior parte da infra já existe e foi aplicada (Dec 2025)** — o
que falta é reconciliar e fechar 3 gaps específicos do V3.3, não construir do zero.

## O que já está feito (confirmado, não reinventar)

- GRANTs `sql_monitoring`: `V1/database/GRANTS_SQL_MONITORING_SEGUROS.sql` v1.3 (VIEW SERVER
  STATE + VIEW DATABASE STATE per-DB + DENY SELECT dbo + msdb backup/jobs). Aplicado
  2025-12-26 (`V1/logs/grants/`).
- `VIEW ANY DEFINITION`: `V1/database/CONFIGURAR_PERMISSOES_SQL_MONITORING.sql`.
- Wrapper proc de errorlog: `V1/database/CREATE_PROCEDURE_COLLECT_ERRORLOG.sql`.
- Orquestrador: `V1/scripts/apply_grants_all_servers.py`.
- Plumbing SQL-auth no V3.3: `api/connection_pool.py` (`_build_connection_string_sql_auth`,
  `_resolve_credentials`, decrypt Fernet/DPAPI, `servers.json`).

## Perguntas concretas para os specialists

### Para `watcherdb-v1-intel-specialist` (BD partilhada, direito de veto)
1. **Gap 1 (msdb):** OK adicionar `GRANT SELECT` em `sysjobsteps`/`sysjobschedules`/
   `sysschedules` ao `SEGUROS.sql` (aditivo, mesmo padrão)? Afeta V1 collector de alguma forma?
2. **Gap 3 (divergência):** o `apply_grants_all_servers.py` aplicou o subset msdb-only
   inline — os grants server/per-DB do `SEGUROS.sql` chegaram mesmo a todos os servidores,
   ou há servidores só com msdb? Qual é o canonical a re-aplicar?
3. O flip do V3.3 para `sql_monitoring` altera a carga de conexões na BD partilhada ou nos
   servidores monitorizados de forma que o V1 collector sinta? Vetas alguma parte?

### Para `watcherdb-deploy-architect` (service account + errorlog)
1. **Gap 2 (xp_readerrorlog):** confirmas a opção (A) — apontar o V3.3 ao wrapper proc já
   existente do collector — como caminho? Ou preferes (C) degradação graciosa em fase 1?
2. Onde vive hoje a password de `sql_monitoring` para o runtime do V3.3 (cofre/env/DPAPI)?
   O `connection_pool` já decripta — falta popular `servers.json` com `use_windows_auth=false`
   + credenciais para os servidores-piloto?
3. O flip de `intelligence_use_windows_auth` default para False tem impacto no packaging /
   service account atual (o serviço deixa de precisar de correr sob conta de domínio com dbo)?

## Sequência proposta (após respostas)

1. Owner corre a query de levantamento (PASSO 1 do doc da mini-wave) em 3 pilotos
   (standalone / FCI / AlwaysOn) → mapa real de gaps por servidor.
2. Specialists validam Gaps 1-3 + decisão errorlog (A/C).
3. Owner aplica Gap 1 + reconcilia Gap 3 (V1 specialist aprova o SQL).
4. Flip de código numa branch (settings default + wiring do `_build_connection_string`),
   validação piloto, rollout.

## Estado

Aguarda: (a) query de levantamento correr nos pilotos; (b) respostas dos 2 specialists.
Sem isto, NÃO avançar para GRANTs nem flip de código.
