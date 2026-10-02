# Propagação para o V6 (Pro) — Atribuição de query à aplicação: P0 e P0b

**Data:** 2026-09-24
**Origem:** WatcherDB V3.4 (Standard). Plano completo: `docs/context/PLANO_ATRIBUICAO_APP_2026-09-24.md`;
parecer: `docs/context/SQLCOMMENTER_PARECER_2026-09-24.md`; SQL: `docs/context/sql/atribuicao_app_2026-09-24.sql`.
**Lote de referência no V3.4:** `docs/context/P0_PERFORMANCE_ROLE_GATE_2026-09-24_apply.py` (ler antes; portar por
intenção, não por diff — os ficheiros do V6 divergem dos do V3.4).

Cola o bloco abaixo como primeira mensagem na sessão aberta em `C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V6`.

---

## Prompt para a sessão do V6

Modo consultor (CLAUDE.md do V6). Lê primeiro `docs/context/CONTEXT.md` do V6 e, no V3.4,
`docs/context/PLANO_ATRIBUICAO_APP_2026-09-24.md` e `docs/context/P0_PERFORMANCE_ROLE_GATE_2026-09-24_apply.py`.
Consulta o watcherdb-v5-specialist e o watcherdb-security-auditor antes de propor; entrega em apply script
com --check/--preview/--repo, teste, e prova na cópia. Não commitas: o owner corre e commita.

Dois lotes, por esta ordem. Nada de L2 (parser sqlcommenter) antes de os dois fecharem.

### P0 — Performance Module sem gate de role (cross-tier, verificado a 2026-09-24)

Factos no V6 (branch wave-propagacao-v33-20260819):
- `api/routers/performance.py` (prefixo /api/v1/performance): zero `Depends()`; só passa pelo `AuthMiddleware`
  global (`api/security.py:85-154`), que autentica mas não autoriza por role. Qualquer role lê `sql_text` cru
  via `POST /investigate/{instance}/{investigator_id}` e escreve em `performance_action_history`.
- `api/routers/live_monitoring.py:79-83` já exige `_require_dba` no router inteiro (viewer recebe 403) e NÃO tem
  `_redact_node`/`_RoleRedactingRoute` (existem só no V3.4).
- Routers que expõem campo tipo `sql_text`: `live_monitoring.py` (12), `sql_queries.py` (4), `ops_dashboard.py` (6).

O que fazer (espelho do lote V3.4, adaptado):
1. Criar `api/role_redaction.py` igual ao do V3.4 (REDACTED, SQL_FIELDS, IDENTITY_FIELDS, redact_node,
   role_do_pedido, RoleRedactingRoute). Confirmar onde o middleware do V6 põe o utilizador
   (`request.state.user`? outro nome?) e adaptar `role_do_pedido`.
2. `api/routers/performance.py`: `route_class=RoleRedactingRoute`; `dependencies=[Depends(gate dba)]` nos
   decoradores de `POST /action-history` e `POST /ticket-response` (gate no decorador, nunca no corpo: 403 antes
   do 422). Confirmar o nome do helper de role do V6 (equivalente a `_require_dba` de `auth_compat.py:266`).
3. Decidir com o security-auditor se `sql_queries.py` e `ops_dashboard.py` recebem o mesmo route_class (opt-in
   explícito, routers separados). Recomendação: sim, no mesmo lote, se os endpoints são de leitura.
4. Teste `tests/unit/test_performance_role_gate_20260924.py` portado (viewer → hash/oculto; dba/admin → tudo;
   viewer POST → 403 antes do corpo; guarda de route_class nos routers cobertos).
5. Pré-requisito de CI (achado do v5-specialist): `.github/workflows/ci.yml` corre `pytest tests/ --cov=api
   --cov=services --cov=hybrid`; `modules/` está fora de cobertura, lint e bandit. Propor adicionar `modules` aos
   paths; não bloqueia o P0.

### P0b — `services/query_store_monitor.py` liga à base errada

Facto (v5-specialist, confirmado por leitura): os 4 métodos (`get_top_queries` :92-141, `detect_regressions`
:143-228, `get_plan_comparison` :230-290, `get_query_store_status` :292-324) executam `sys.query_store_*` via
`execute_on_intelligence()` (`api/connection_pool.py:945`) = WatcherDB_Intelligence, não a instância alvo.
`instance`/`database` são aceites mas nunca entram no SQL; `_get_from_staging` (:326-328) é stub `return []`.
O comentário do autor em :131-132 admite-o. Logo `/api/v1/query-store/*` (`api/routers/query_store.py`:
/status :17, /top-queries :30, /regressions :53, /plan-comparison/{query_id} :77) nunca devolve dados reais.

O que fazer:
1. Reencaminhar os 4 métodos para execução por instância (padrão dos investigators:
   `async_execute_on_server(instance, query)`), com `USE [database]` ou prefixo de base na consulta, gate
   `ProductMajorVersion >= 13` (2014 não tem Query Store: skip gracioso, sem exception) e `HAS_DBACCESS`.
2. Identidade: a ligação do pool = `sql_monitoring` (só SELECT + VIEW SERVER STATE; `sys.database_query_store_options`
   exige VIEW DATABASE STATE por base → TRY/CATCH e reportar "sem permissão").
3. Testes: mock do executor por instância; 2014 → `{"available": False}`; base sem QS → vazio sem erro.
4. Prova: `GET /api/v1/query-store/status?instance=<QLT 2016+>` devolve estado real; contra 2014 devolve
   indisponível com 200.

### Depois (não agora)

Propagar L1-SQL/L1-UI/L1b quando fecharem no V3.4 (nota própria), depois L2a/L2b/L2c (Pro-only; cabeçalho
`# PRO-ONLY - nao propagar para V3.4 sem decisao DBA Lead`). Ordem e barra no plano.

Ao fechar, anexa ao `docs/context/CONTEXT.md` do V6 uma linha `data | agente | decisão + ponteiro` e, no V3.4,
diz ao owner que o P0/P0b do V6 fecharam para ele registar no CONTEXT.md de cá.
