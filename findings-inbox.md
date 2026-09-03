# Findings Inbox — WatcherDB V3.3

Specialists do council depositam aqui findings proactivos (fora do scope da task imediata) para triagem semanal pelo orquestrador / DBA Lead.

## Convenção de numeração (estabelecida 2026-05-05)

Para evitar colisão entre o sistema formal `docs/findings/<id>-<slug>.md` e este inbox compacto:

- **`FIND-YYYYMMDD-0XX`** (sequência 0XX, i.e. 001-099) — reservada para findings em formato formal `docs/findings/FIND-YYYYMMDD-NNN-<slug>.md` (um ficheiro por finding, com tabela metadata + secções).
- **`FIND-YYYYMMDD-1XX`** (sequência 1XX, i.e. 101-199) — para findings deste inbox compacto inline.
- **Antes de numerar**: `Get-ChildItem docs/findings -Filter "FIND-YYYYMMDD-*"` E `Select-String -Path findings-inbox.md -Pattern "FIND-YYYYMMDD-"` para garantir non-collision.
- **Migração retroactiva 2026-05-05**: 7 findings deste inbox foram renumerados de 001-007 para 101-107 (colisão com `docs/findings/FIND-20260505-001-tier-inversion-collector-health-ux.md` que existia previamente).

## Formato

```
## FIND-YYYYMMDD-NNN — <título curto>

- **Severity:** P0 | P1 | P2
- **Category:** security | performance | reliability | opportunity | tiering | docs | ux | coverage | privacy | compliance | accessibility | regression-risk | i18n
- **Owner specialist:** <nome do agent>
- **Evidence:** <path:linha ou query/commit ref>
- **Recommendation:** <1 frase prescritiva>
- **Status:** open | triaged | in-progress | resolved | wont-fix
- **Created:** YYYY-MM-DD
- **Updated:** YYYY-MM-DD
```

## Severity rubric

- **P0** — produção quebrada, data loss possível, segurança crítica, regressão Std visível ao cliente
- **P1** — bug funcional, performance degradada, gap de tiering, divergência Std/Pro material
- **P2** — limpeza, docs em falta, dívida técnica não-blocking

## Triage cadence

- Diário: orquestrador relê P0 / P1 abertos no início de cada sessão
- Semanal: DBA Lead revê P2 e decide promover / arquivar

---

## FIND-20260428-001 — `bind_password` AD em plaintext em SystemConfig

- **Severity:** P1
- **Category:** security
- **Owner specialist:** watcherdb-v33-specialist (sweep Fase 4.3)
- **Evidence:** `services/auth_service.py:361` — `save_system_config("ad_domains", json.dumps(clean))` persiste `bind_password` plaintext em JSON em `WatcherDB_System_Config.ad_domains`
- **Recommendation:** aplicar encriptação DPAPI/Fernet ao valor antes de `json.dumps`, ou usar coluna separada com acesso restrito. Precedente: VC-4 (V1 Intel credential store).
- **Status:** resolved (commit 1405e16 DPAPI helpers + audit 2026-05-05 confirma kerberos integrated bind = N/A para zero-day rotation)
- **Created:** 2026-04-28
- **Updated:** 2026-05-05 (audit empty bind_password = kerberos integrated mode)
- **Handoff:** `watcherdb-security-auditor` para parecer formal sobre escolha (DPAPI vs Fernet-over-DB) em contexto Windows Service
- **Sweep 2 — security-auditor parecer formal:**
  - STRIDE: **Information Disclosure** (primary) + **Tampering** (secondary — DB write injecta rogue domain config -> credential harvest)
  - OWASP **A02:2021 Cryptographic Failures** (NÃO A07)
  - CWE-**522** Insufficiently Protected Credentials
  - Compliance: SOC 2 **CC6.6 FAIL** / ISO 27001 **A.10.1.1 FAIL** / GDPR Art. 32 PARTIAL / DORA banking **FAIL**
  - **P1 confirmado standalone**, com escalation clause: **P0 se bind account tiver qualquer write permission em AD** (delegate password reset / group modification rights)
  - **Path A (DPAPI Windows-machine-bound) recomendado** sobre Path B (Fernet+DPAPI hybrid) ou Path C (Always Encrypted) — V3.3 single-machine, precedente VC-4, `win32crypt` already available, fix de 1 sprint
  - **Zero-day rotation requerida** (não going-forward only) — passwords em plaintext desde commit 691a529 (28/04) são compromised by design
- **Sweep 2 — customer-success-persona escalation:**
  - **P0 em contexto banking** (compliance audit blocker): SOC 2 / ISO 27001 checklist standard "todas credenciais encriptadas em repouso?" tem resposta NÃO documentada; DBA Lead não pode entregar relatório de auditoria com este estado
  - Recomendação meta: manter P1 como rubric base (consistência), mas adicionar release-gate clause "pre-deploy banking-grade DEVE ter este fix antes de tag mesmo se security audit standalone diz P1"

---

## FIND-20260428-002 — Multi-domain LDAP fan-out sem circuit-breaker

- **Severity:** P2
- **Category:** reliability
- **Owner specialist:** watcherdb-v33-specialist (sweep Fase 4.3)
- **Evidence:** `services/auth_service.py:855-858` — iteração de domains sem skip de domínios já-falhados na mesma sessão; em rede degradada (TCP RST delayed), login pode bloquear até `N × timeout` segundos
- **Recommendation:** adicionar `concurrent.futures.ThreadPoolExecutor` paralelo OU flag `already_failed_domains` (skip em iterações subsequentes da mesma sessão). Documentar em `.env` que `connect_timeout` é per-domain bounded.
- **Status:** open
- **Created:** 2026-04-28
- **Updated:** 2026-04-28

---

## FIND-20260428-003 — KPI "SQL Não Respondeu" hardcoded em 5 locais (i18n gap)

- **Severity:** P1
- **Category:** i18n
- **Owner specialist:** watcherdb-frontend-specialist (sweep Fase 4.3)
- **Evidence:** `templates/watcherdb_portal.html:24436,24493,30308,30313,34297` — 5 strings literais "SQL Não Respondeu" sem chave i18n; clientes en-US verão label em português
- **Recommendation:** criar chave `kpi.sql_not_responding.title` em `static/js/watcherdb_i18n_v2.js` e substituir as 5 strings por `data-i18n=` ou `t('kpi.sql_not_responding.title')`
- **Status:** open
- **Created:** 2026-04-28
- **Updated:** 2026-04-28
- **Note:** rename "SQL Services Down" → "SQL Não Respondeu" (commit `7a9355a`) foi feito em PT hardcoded; pre-existia mas era oportunidade perdida de regularizar

---

## FIND-20260428-004 — Modal `selectInstanceFromModal` blocked-sessions: 2 call-sites sem escape

- **Severity:** P1
- **Category:** ux
- **Owner specialist:** watcherdb-frontend-specialist (sweep Fase 4.3)
- **Evidence:** `templates/watcherdb_portal.html:33029,33103` — 2 call-sites passam `instanceName` raw em template literal em vez de `escapedInstanceName` (contrato estabelecido pelo fix `49a21c0` para outros KPIs); risco com instâncias nomeadas (backslash)
- **Recommendation:** substituir por `escapedInstanceName` (mesmo padrão das linhas 32531, 32804). Adicionar regression test (Playwright OR extracted JS util + Jest)
- **Status:** open
- **Created:** 2026-04-28
- **Updated:** 2026-04-28
- **Cross-link:** FIND-20260428-007 (QA: regression test em falta para modal backslash fix)

---

## FIND-20260428-005 — `ad_domain` descartado, badge UX cego em multi-domain

- **Severity:** P2
- **Category:** ux
- **Owner specialist:** watcherdb-frontend-specialist (sweep Fase 4.3)
- **Evidence:** `services/auth_service.py:_auto_provision_ad_user (linha 898)` (omite `ad_domain` no return) + `templates/watcherdb_portal.html:4308-4309` (badge mostra só "Active Directory" sem domínio); em ambiente multi-domain (Patch D), DBA não sabe qual domínio autenticou (relevante em troubleshooting de permissões)
- **Recommendation:** backend propaga `ad_domain` no return de `_auto_provision_ad_user()`; frontend `updateUserBadge()` (linha 4309) usa `user.ad_domain` para enriquecer label (ex.: "Active Directory (tapnet.tap.pt)")
- **Status:** open
- **Created:** 2026-04-28
- **Updated:** 2026-04-28
- **Handoff:** cross-stack — frontend + v33-specialist coordenam fix

---

## FIND-20260428-006 — Patch D multi-domain: zero unit tests cobrem `_authenticate_ldap`

- **Severity:** P0
- **Category:** coverage
- **Owner specialist:** watcherdb-qa-specialist (sweep Fase 4.3)
- **Evidence:** `services/auth_service.py:797-856` (`_authenticate_ldap`) — `tests/unit/test_ad_input_validation.py:42` apenas testa regex de input validation (cria falsa sensação de coverage); auth path real está untested. Sem coverage para: (a) AD_DOMAINS=[] fallback single-domain, (b) fan-out N domains, (c) `user@fqdn` filter, (d) `DOM\user` NetBIOS filter, (e) wrong password em multi-domain
- **Recommendation:** criar `tests/unit/test_auth_service_multi_domain.py` com 5 cenários acima. Mock `_try_single_domain_bind` — sem live LDAP necessário.
- **Status:** open
- **Created:** 2026-04-28
- **Updated:** 2026-04-28
- **Veredicto QA Gate 3 (pre-tag):** GO-com-ressalvas (não bloqueia tag, mas ticket P0 pre-next-sprint)
- **Cross-link:** FIND-20260428-002 (relacionado: multi-domain fan-out sem circuit-breaker — testa também)

---

## FIND-20260428-007 — Modal backslash normalisation: zero regression test

- **Severity:** P1
- **Category:** coverage
- **Owner specialist:** watcherdb-qa-specialist (sweep Fase 4.3)
- **Evidence:** `templates/watcherdb_portal.html` emit sites linhas 33311, 33377, 33478, 33569, 33850 — fix `49a21c0` é 5 substituições find-replace; sem Playwright/Jest test que reproduza click. `tests/e2e/workflows.spec.ts` tem zero modal interaction. `tests/unit/test_connection_pool.py:217-227` testa normalização do pool, NÃO o emit path HTML.
- **Recommendation:** **(opção A baixo esforço)** extrair `normaliseInstanceName(raw)` JS util + Jest unit test; **(opção B mais alto valor)** Playwright em `tests/e2e/workflows.spec.ts` que (1) login → dashboard → KPI cards renderizam; (2) click modal trigger; (3) assert `selectInstanceFromModal()` resolve sem alert.
- **Status:** open
- **Created:** 2026-04-28
- **Updated:** 2026-04-28
- **Cross-link:** FIND-20260428-004 (frontend: 2 call-sites residuais em blocked-sessions — adicionar à mesma test sweep)

---

## FIND-20260428-008 — KPI reconcile SQL fix sem fixture pytest

- **Severity:** P2
- **Category:** regression-risk
- **Owner specialist:** watcherdb-qa-specialist (sweep Fase 4.3)
- **Evidence:** `database/FIX_SERVER_OFFLINE_RECONCILE_COLLECTION_SUCCESS.sql` — fix dos commits `33c2fed` + `9e967c6` é 100% SQL CTE; sem Python-testable surface. Validation actual = manual SSMS execution. Próximo cycle de SQL view changes pode silentemente quebrar reconcile CTE join.
- **Recommendation:** adicionar `tests/integration/test_sqlserver_kpi.py:test_ghost_card_reconcile_filters_recent_success` (skip-if-no-db tag). Inserir test rows controlled em temp schema, executar reconcile logic, assert filtered output exclui ghost rows.
- **Status:** open
- **Created:** 2026-04-28
- **Updated:** 2026-04-28
- **Handoff:** v33-specialist + v1-intel-specialist (a tabela `INST_AVAILABILITY` é shared; v1 tem veto power)

---

## FIND-20260428-009 — CVE-2025-54918 NTLM relay vector via auth fallback

- **Severity:** P1 (HIGH — environmental dependency)
- **Category:** security
- **Owner specialist:** watcherdb-security-auditor (sweep 2)
- **Evidence:** `services/auth_service.py:752-753` — `authentication=NTLM` fallback path em `_try_single_domain_bind`; CVE-2025-54918 (CVSS 8.8) é Windows NTLM stack vuln (Partial MIC Removal relay attack que bypassa LDAP signing/channel binding mesmo quando required no DC)
- **Attack vector:** WatcherDB Windows Service account coerced (Printer Bug, etc.) -> WatcherDB autentica via NTLM ao DC -> attacker relay -> credentials harvested
- **Recommendation:** (a) preferir UPN-only auth — adicionar flag `allow_ntlm_fallback: false` em domain config; (b) deployment runbook documentar requisito de DC patch (cumulative update September 2025); (c) startup health-check warning se NTLM fallback enabled E DC patch status unknown
- **Status:** open
- **Created:** 2026-04-28
- **Updated:** 2026-04-28
- **Handoff:** `watcherdb-deploy-architect` (runbook DC patch requirement) + `watcherdb-v33-specialist` (config flag impl)
- **References:** [CVE-2025-54918 NVD](https://nvd.nist.gov/vuln/detail/CVE-2025-54918), [CrowdStrike analysis](https://www.crowdstrike.com/en-us/blog/analyzing-ntlm-ldap-authentication-bypass-vulnerability/)

---

## FIND-20260428-010 — Audit log identity gap em config changes

- **Severity:** P2
- **Category:** compliance
- **Owner specialist:** watcherdb-security-auditor (sweep 2)
- **Evidence:** `services/auth_service.py:361` — `save_system_config("ad_domains", ...)` não regista identidade do admin que fez a mudança; tabela `WatcherDB_System_Config` (DDL `services/auth_service.py:226-256`) não tem coluna `changed_by` nem CDC
- **Compliance gap:** SOC 2 CC7.2 (monitoring of system changes) + ISO 27001 A.12.4.3 (administrator and operator logs) — admin que adiciona/remove domain ou rotaciona bind password não deixa identity audit trail
- **Recommendation:** (a) adicionar colunas `changed_by VARCHAR(100)` + `change_source VARCHAR(50)` ao `WatcherDB_System_Config`; (b) passar acting admin username ao `save_system_config` ou logar `[CONFIG AUDIT] ad_domains changed by {admin}` em INFO level a partir do endpoint que chama `save_ad_config()`
- **Status:** open
- **Created:** 2026-04-28
- **Updated:** 2026-04-28
- **Handoff:** `watcherdb-v33-specialist` (DDL migration + endpoint capture)

---

## FIND-20260428-011 — Startup AD diagnostic loga FQDN em INFO level

- **Severity:** P2
- **Category:** privacy
- **Owner specialist:** watcherdb-security-auditor (sweep 2 — STRIDE Patch D, Frente 2-I)
- **Evidence:** Patch C (commit `7c95c53`) loga `[AUTH_DIAG] LDAP server <FQDN>:<port> reachable: <bool>` em `logger.info(...)` no startup; em deploys banking com SIEM forwarding e log retention longa, FQDN do DC sai do perímetro e é information disclosure (topology DC)
- **Recommendation:** baixar log level para `logger.debug(...)` para linhas que contenham FQDN/connection details — default production log config (INFO) suprime; debug fica disponível para troubleshooting on-demand
- **Status:** open
- **Created:** 2026-04-28
- **Updated:** 2026-04-28
- **Handoff:** `watcherdb-v33-specialist` (mudança 1-line trivial, tirar do startup hot-path)

---

## FIND-20260428-012 — Login form sem feedback de progresso multi-domain

- **Severity:** P2
- **Category:** ux
- **Owner specialist:** watcherdb-customer-success-persona (sweep 2 — Flow 1)
- **Evidence:** `templates/watcherdb_portal.html` (login form) — quando multi-domain LDAP fan-out demora (FIND-002 scenario, até 25s pior caso com 5 domínios e DCs offline), o formulário parece congelado; DBA clica "Entrar" múltiplas vezes -> múltiplas sessões OU AD lockout do utilizador
- **Recommendation:** (a) spinner + disabled state no botão de login durante autenticação; (b) mensagem "A verificar credenciais..." com timeout visual (ex.: "5s / 25s"); (c) fetch deve abortar tentativas duplicadas (idempotency key OU AbortController)
- **Status:** open
- **Created:** 2026-04-28
- **Updated:** 2026-04-28
- **Handoff:** `watcherdb-frontend-specialist` (impl front-only) + `watcherdb-v33-specialist` (validar se backend precisa idempotency key)
- **Cross-link:** FIND-002 (root cause — multi-domain fan-out sem circuit-breaker)

---

## FIND-20260428-013 — Tier creep: `copilot_router` registado em V3.3 build (Pro feature em Std)

- **Severity:** P0
- **Category:** tiering
- **Owner specialist:** orchestrator (descoberto em FEATURE_MATRIX revisão directa, sweep 2 follow-up)
- **Evidence:**
  - `watcherdb_main.py:462` → `from api.routers.copilot import router as copilot_router`
  - `watcherdb_main.py:463` → `app.include_router(copilot_router)`
  - `api/routers/copilot.py` (~6.5 KB, 7 endpoints: status GET/POST, quick-answers, insights, ask, report) com docstring literal: "Endpoints for the DBA Copilot feature. Provides AI-assisted (or rule-based) DBA knowledge, insights, and reports."
- **Root cause confirmado:** V3.3 é fork file-system de V3.2 (copy-paste de directório, não branch git). DBA Copilot foi shipped em V3.2 antes do tiering Std/Pro existir. Herdado para V3.3 sem cleanup. Confirmado pelo user (DBA Lead) em 2026-04-28.
- **Tier classification:** "Recomendações AI" / "Análise Causa Raiz AI" estão em `docs/FEATURE_MATRIX.md` secção 4 (Pro-only). Copilot é exactamente isto.
- **Implicações comerciais:** clientes V3.3 Std actuais recebem Pro feature de graça → erosão de margem upsell Std→{}V5/V5.5/V6 Pro. Risco: cliente Std descobre dependência da feature, depois conflito ao migrar para Pro.
- **Recommendation:**
  1. Remover `app.include_router(copilot_router)` de `watcherdb_main.py` (1-line patch + try/except graceful)
  2. **NÃO** apagar `api/routers/copilot.py` — manter source-tree paridade com V5+ (facilita merge bidireccional futuro). Só não registar o router no build V3.3.
  3. Update `docs/FEATURE_MATRIX.md` secção 4.1 nova: "Features removidas do V3.3 build (Pro-only herdadas de V3.2)" — tornar tier creep historicamente visível.
  4. `v33-feature-matrix-checker` micro-agent passa a correr pre-tag (Quality Gate 3) — bloqueia release com tier creep.
- **Status:** triaged-pending-product-decision (user a confirmar se aceita remoção ou se há razão de manter atrás de feature flag)
- **Created:** 2026-04-28
- **Updated:** 2026-05-06 — Wave 0 KB bootstrap re-flagged: decision A/B/C stale 8+ days. Orchestrator escalation note: cada sprint sem decisao aumenta risco de cliente Std descobrir Copilot acidentalmente; KB bootstrap nao bloqueia mas product decision continua em backlog P1 visivel.
- **Handoff:** `watcherdb-v33-specialist` (impl remoção) + `watcherdb-frontend-specialist` (verificar SPA tem botões/links que chamem `/copilot/*` — se sim, esconder atrás de tier flag) + `watcherdb-customer-success-persona` (verificar PRODUCT_SHEET cliente Std não anuncia Copilot)

---

## FIND-20260428-014 — Tier creep: predictive_alerts ML engine activo em V3.3 build (Pro feature em Std)

- **Severity:** P0
- **Category:** tiering
- **Owner specialist:** orchestrator (descoberto em FEATURE_MATRIX revisão directa, sweep 2 follow-up)
- **Evidence:**
  - `watcherdb_intelligence.py:5854` → `async def get_predictive_alerts(server_id: str):` (endpoint exposto)
  - `watcherdb_intelligence.py:5870-5874` → import chain: tenta primeiro `modules.monitoring.predictive_alerts.PredictiveAlertsEngine`, fallback para `modules.monitoring.predictive_alerts_debug.PredictiveAlertsEngine`
  - `modules/monitoring/predictive_alerts_debug.py` (36 KB) usa **sklearn.linear_model.LinearRegression** + numpy → ML linear regression para alertas preditivos
  - Endpoint debug: `watcherdb_intelligence.py:5978` → `async def debug_predictive_alerts(server_id: str)`
- **Root cause confirmado:** mesmo padrão de FIND-013 — V3.3 fork file-system de V3.2 com herança de features ML. Confirmado pelo user (DBA Lead) em 2026-04-28.
- **Tier classification:** "Anomaly Detection ML-powered" e "Recomendações AI" em `docs/FEATURE_MATRIX.md` secção 4 (Pro-only). Predictive Alerts via sklearn é exactamente esta categoria.
- **Histórico:** `MEMORY.md/session_20260417_checkpoint_pre_find014.md` referencia FIND-014 anterior sobre "restaurar predictive_alerts em V3.3" → contexto perdido entre bootstraps; necessário re-validar se foi decisão deliberada (improvavel dada confirmação Hipótese A) ou erro de bootstrap anterior.
- **Implicações:**
  - Comerciais: idem FIND-013 (margem Pro erodida)
  - Técnicas: sklearn é dependência adicional no requirements.txt do build Std (verificar `requirements.txt` se sklearn é obrigatório ou optional)
  - Risk: ML linear regression sem validação de modelo + sem métricas pode gerar falsos positivos/negativos em prod → alertas predictivos enganadores são pior do que zero alertas predictivos
- **Recommendation:**
  1. Remover/desactivar endpoints `/api/predictive-alerts/*` de `watcherdb_intelligence.py` (linhas 5854, 5978)
  2. Manter `modules/monitoring/predictive_alerts*.py` no source tree (paridade com V5+) mas sem entry-point activo em build Std
  3. Verificar se `requirements.txt` tem `scikit-learn` como dep obrigatória — se sim, mover para `requirements-pro.txt` (separar)
  4. Cross-check com PRODUCT_SHEET Std (FIND-013 handoff também)
- **Status:** triaged-pending-product-decision
- **Created:** 2026-04-28
- **Updated:** 2026-05-06 — Wave 0 KB bootstrap re-flagged: decision A/B/C stale 8+ days. sklearn dependency continua em build Std (~30MB footprint) sem tier guard. Orchestrator escalation: cada sprint sem decisao mantem zero-tests-coverage para predictive_alerts (P0 risk material para falsos positivos em prod cliente).
- **Handoff:** `watcherdb-v33-specialist` (impl) + `watcherdb-deploy-architect` (separação requirements + footprint reduction Std)
- **Cross-link:** FIND-013 (mesmo root cause — tier creep herdado fork V3.2→{}V3.3)

---
## POST-SCAN UPDATE (28/04 evening) — FIND-013 + FIND-014 re-classificação

Após dependency scan thorough (orchestrator, read-only), descoberta de **estado mais nuanced** que invalida classificação P0 inicial:

### FIND-013 (Copilot) re-classificar P0 tier-creep → **P1 tier-architecture-confusion**

**Evidências contraditórias descobertas:**

1. `api/routers/copilot.py:143` linha literal: *"Standard Edition: rule-based only. LLM delegation is gated to Pro"* → router **assume** Std tem variante rule-based legitima
2. `watcherdb/licensing/feature_registry.py:29` lista **`"dba_copilot_rule_based"`** como feature explicit → registry confirma Std tem Copilot rule-based
3. `templates/watcherdb_portal.html:42070-42150` **TIER GUARD client-side bloqueia 100% Copilot em Std** ("DBA Copilot é feature WatcherDB Pro Edition. Contacta equipa comercial para upgrade") → frontend assume Pro-only
4. **Conflito:** backend e licensing assumem Std-rule-based + Pro-LLM; frontend bloqueia Std completamente
5. **Sem `_require_pro_tier` decorator** nos endpoints → `curl /copilot/ask` directo de utilizador Std passa sem guard

**Re-classificação:** **P1 tier-architecture-confusion** (não tier-creep simples). Decisão de produto requerida: Copilot rule-based é Std-feature ou Pro-only?

**Caminhos possíveis:**
- **A. Copilot rule-based É Std (alinhado com backend/registry):** remover TIER GUARD frontend (linhas 42096-42150) + manter backend; tier guard está a bloquear feature legítima
- **B. Copilot rule-based NÃO é Std (alinhado com frontend):** desactivar `app.include_router(copilot_router)` em V3.3 build + remover entry de `feature_registry.py:29` + corrigir docstring router linha 143
- **C. Híbrido:** Std vê Copilot mas modo "demo" (1 query/dia) + upsell prompt → upselling explícito

### FIND-014 (Predictive Alerts) **confirma P0 tier-creep**, evidência completa

**Evidências definitivas:**

1. `requirements.txt:23,26` → `numpy>=1.25.0` + `scikit-learn>=1.3.0` como **deps obrigatórias build Std** (~30 MB footprint adicional)
2. `templates/watcherdb_portal.html:21184,21204,22887,26082,26111,26137,26142` → **UI predictive alerts panel ACTIVO em Std** (loadPredictiveAlerts, renderPredictiveAlertsPanel, showPredictiveModal, painel #predictiveAlertsPanel) — sem tier guard
3. Endpoint chamado em SPA: `/api/monitoring/space/server/{serverId}/predictive-alerts` (não confirmado se este endpoint é o do `watcherdb_intelligence.py:5854` ou outro)
4. `modules/monitoring/predictive_alerts.py` (27 KB) + `predictive_alerts_debug.py` (36 KB) ambos com sklearn LinearRegression
5. Tests: **ZERO** em `tests/` (confirmado via scan)
6. Linha 14060 SPA: `// await renderPredictiveAlertsPanel(serverId);` → comentário sugere alguém **tentou** desactivar mas só comentou um call-site, não removeu o panel

**Sem tier guard** (frontend ou backend) → **tier creep confirmado P0**.

**Caminhos possíveis:**
- **A. Predictive Alerts É Std-feature deliberada:** aceitar dep sklearn + escrever tests (zero coverage actual = risk material) + remover comentário `// await` linha 14060 + documentar em FEATURE_MATRIX.md secção 3 (Std list)
- **B. Predictive Alerts é Pro-only:** desactivar endpoints (`watcherdb_intelligence.py:5854,5978`) + esconder UI panel (linhas 21184, 21204, 22887, 26082-26142) + remover sklearn de `requirements.txt` (mover para `requirements-pro.txt`) + manter source code (paridade V5+)
- **C. Status quo:** documentar em FEATURE_MATRIX.md como "tier creep accepted (will fix in V3.4)" → má prática mas honest

### Recomendação meta para sprint

**NÃO aplicar patches sem user decidir A/B/C para cada finding.** A escolha tem implicações comerciais (PRODUCT_SHEET cliente Std muda) + técnicas (deps + tests + UI) + de testing (FIND-014 sem tests é gap de produção).

**Patches em texto** (advisor mode, NÃO aplicar — apenas referência):

**Patch P-013-A** (se A escolhido para Copilot — rule-based É Std):
- `templates/watcherdb_portal.html` linhas 42096-42150: remover TIER GUARD warning
- `feature_registry.py:29`: confirmar entry `dba_copilot_rule_based` correcta
- `copilot.py:143` docstring: validar consistência

**Patch P-013-B** (se B escolhido — Copilot Pro-only):
- `watcherdb_main.py:462-466`: comentar ou remover bloco `include_router(copilot_router)` (try/except graceful)
- `feature_registry.py:29`: remover `"dba_copilot_rule_based"`
- `api/routers/copilot.py`: **manter** no source (paridade V5+); só não registar
- `templates/watcherdb_portal.html` linhas 42096-42150: tier guard fica como está (correcto)
- Adicionar `v33-feature-matrix-checker` ao Quality Gate 3 pre-tag

**Patch P-014-A** (se A — Predictive Alerts É Std):
- `templates/watcherdb_portal.html:14060`: descomentar `await renderPredictiveAlertsPanel(serverId);`
- `tests/integration/test_predictive_alerts.py` NEW: pytest com fixture sklearn mock + assertions de prediction shape
- `docs/FEATURE_MATRIX.md` secção 3: adicionar "Predictive Alerts (sklearn LinearRegression-based)" à Std list

**Patch P-014-B** (se B — Predictive Alerts Pro-only):
- `watcherdb_intelligence.py:5854,5978`: remover endpoints `get_predictive_alerts` + `debug_predictive_alerts`
- `templates/watcherdb_portal.html`: esconder/remover linhas 21184, 21204, 22887 + function bodies 26082-26142
- `requirements.txt:23,26`: mover `scikit-learn` para `requirements-pro.txt`; verificar dep numpy ainda usada por outros
- `modules/monitoring/predictive_alerts*.py`: **manter** no source tree
- `docs/FEATURE_MATRIX.md` secção 4 (Pro-only): adicionar "Predictive Alerts ML"

### Action requested

Decisão de produto de cada finding:

- [ ] FIND-013: A | B | C (Copilot)
- [ ] FIND-014: A | B | C (Predictive Alerts)

Após decisão, próxima sessão pode aplicar patches correspondentes em advisor mode (utilizador autoriza per-task) ou orquestrador produz commits step-by-step para review.

---
## Bootstrap notes

Findings 001-008 emitidos durante **first proactive sweep** (Trigger 1 → session sweep) do council Nestor V3.3 bootstrap (2026-04-28). 3 specialists em paralelo: v33-specialist + frontend-specialist + qa-specialist.

Findings 009-012 emitidos durante **second proactive sweep** (2026-04-28, mesmo dia): customer-success-persona + security-auditor (specialists não-tocados na first sweep). FIND-001 ganhou parecer formal + escalation note (P1 standalone, P0 em banking pre-deploy).

**Findings 013-014** emitidos durante **FEATURE_MATRIX revisão direct** (orchestrator, sem dispatch) — descoberta material de **tier creep P0** (Copilot router + Predictive Alerts ML engine activos em V3.3 build, herdados do fork file-system V3.2→{}V3.3). Root cause confirmado pelo user (DBA Lead) 2026-04-28: V3.3 é cópia de V3.2 sem cleanup de features Pro.

Triagem inicial sugerida pelo orquestrador (sem aplicar fix sem autorização):

- **P0 imediato:**
  - FIND-006 (coverage Patch D → auth crítico sem testes)
  - FIND-013 (Copilot router em V3.3 build → Pro feature em Std, decisão produto pending)
  - FIND-014 (Predictive Alerts ML engine em V3.3 → Pro feature em Std, decisão produto pending)
- **P1 sprint actual:** FIND-001 (security pwd plaintext → P0-banking pre-deploy clause), FIND-003 (i18n), FIND-004 (modal blocked-sessions → incident-blocking flag), FIND-007 (modal regression test), FIND-009 (CVE-2025-54918 NTLM relay)
- **P2 backlog:** FIND-002 (circuit-breaker), FIND-005 (badge UX), FIND-008 (SQL fixture), FIND-010 (audit log identity), FIND-011 (FQDN log level), FIND-012 (login progress feedback)

**Tensões / cross-links importantes:**

- FIND-001 dual-classification: P1 standalone (security-auditor rubric) vs P0 banking pre-deploy (customer-success rubric). Resolução proposta: manter P1 base + release-gate clause banking
- FIND-004 + FIND-007 + USER-FAIL Flow 2 (customer-success): cluster modal blocked-sessions é incident-blocking em instâncias nomeadas (todas as banking instances são named SQL Server). Triar como cluster, não como findings isolados
- FIND-002 + FIND-012 (cross-link): root-cause UX é o multi-domain fan-out sem feedback; fix de UX (012) sem fix de circuit-breaker (002) só esconde sintoma
- **FIND-013 + FIND-014 (tier creep cluster):** mesmo root cause (fork file-system V3.2→{}V3.3 sem cleanup); recomenda triage conjunta + ADR-003 nova "tier separation post-fork V3.2/V3.3" + sweep recursiva de tier creep similar com `v33-feature-matrix-checker` micro-agent

Nota: severity foi normalizada a partir de severity dos specialists (high→P0/P1, medium→P1/P2, low→P2) tendo em conta blast-radius e visibilidade ao cliente Std pagante. Sweep 2 trouxe 1 HIGH (FIND-009 CVE-2025-54918) na coluna P1. FEATURE_MATRIX revisão trouxe 2 P0 (FIND-013/014) em tiering — primeira vez que findings P0 vêm da decisão de produto, não da implementação.

**Recomendações operacionais para sprint actual:**

1. **Decisão produto FIND-013/014 primeiro** (user / DBA Lead)
2. Se decisão = remover, abrir patches em texto (advisor mode):
   - Patch A: `watcherdb_main.py:462-466` (remove copilot_router)
   - Patch B: `watcherdb_intelligence.py:5854,5978` (remove predictive endpoints)
   - Patch C: `docs/FEATURE_MATRIX.md` (adicionar secção 4.1 "Removidas de V3.3 build")
   - Patch D: `ADR-003-tier-separation-post-fork.md` (decisão arquitectónica documentada)
3. `v33-feature-matrix-checker` micro-agent corrida automatizada **antes da próxima tag** (sweep recursiva tier creep)
4. Findings P1 (auth + modal cluster) ficam para sprint seguinte

---

## FIND-20260429-001 — POST `/api/config/sql-servers` sem `_require_admin`

- **Severity:** P0
- **Category:** security
- **Owner specialist:** watcherdb-v33-specialist + watcherdb-frontend-specialist + v33-modal-auth-gate-checker (sweep modal Configurações)
- **Evidence:** `watcherdb_main.py:1118` (pre-fix) — handler inline aceitava `config: dict` sem `Depends(...)` nem chamada a `_require_admin`. Router alternativo `watcherdb/api/routers/config.py:53-87` com `require_role(UserRole.ADMIN)` correcto existe mas **nunca foi montado** no app FastAPI (sem `app.include_router(config_router)`)
- **Recommendation:** RESOLVED — Patch B aplicado em `watcherdb_main.py:1128` (`await _require_admin(request)`). Router `config.py` não montado fica como dívida técnica (FIND-20260429-006 abaixo) — refactor futuro para remover handler inline e usar router proper.
- **Status:** resolved
- **Created:** 2026-04-29
- **Updated:** 2026-04-29 (commit pendente — ver session log)
- **Note:** STRIDE Elevation of Privilege — qualquer role autenticado (`viewer`, `analyst`) podia sobrescrever `sql_servers.json` em disco. CWE-862 Missing Authorization. Compliance SOC 2 CC6.3 FAIL pre-fix.

---

## FIND-20260429-002 — `Path("config/sql_servers.json")` relativo falha como Windows Service

- **Severity:** P0
- **Category:** reliability
- **Owner specialist:** watcherdb-v33-specialist (sweep CWD audit)
- **Evidence:** `watcherdb_main.py:143,1103,1122,3133,5029,5069` (pre-fix, 6 sítios) + `watcherdb_main.py:1048,3116` para `servers.json` (2 sítios, mesma família) — `services/web_service/service.py` adiciona `project_root` ao `sys.path` mas **nunca faz `os.chdir(project_root)`**. SCM arranca com CWD=`C:\Windows\System32` → `open(...)` tentava gravar em `C:\Windows\System32\config\sql_servers.json` → `PermissionError` ou ficheiro escrito no sítio errado
- **Recommendation:** RESOLVED — Patch A+E aplicados. Constantes module-level `SQL_SERVERS_CONFIG_PATH` (linha 86) e `SERVERS_INVENTORY_PATH` (linha 89) definidas via `Path(__file__).resolve().parent / "config" / "..."`. 8 substituições totais.
- **Status:** resolved
- **Created:** 2026-04-29
- **Updated:** 2026-04-29
- **Note:** Sintoma reportado pelo user: "Salvar Configuração não tem efeito". Falha silenciosa porque o handler retornava 500 e o frontend mostrava `alert()` que o user fechou sem ver. Findings irmãos (paths relativos restantes em outros ficheiros) deferidos como FIND-20260429-007.

---

## FIND-20260429-003 — Modal Configurações sem `data-admin-gated` + UX cega

- **Severity:** P1
- **Category:** ux + security
- **Owner specialist:** watcherdb-frontend-specialist + watcherdb-customer-success-persona (sweep modal Configurações)
- **Evidence:**
  - `templates/watcherdb_portal.html:3551` (pre-fix) — botão `onclick="openSettingsModal()"` sem `data-admin-gated="1"`; modal `#settingsModal` (linha 3564) acessível a qualquer role
  - `templates/watcherdb_portal.html:39322-39360` (pre-fix) — handler `saveSqlServersConfig` usa `alert()` técnico em erro + flash de 2s no botão como único feedback de sucesso. Sem distinção de 401/403, sem validação JSON inline
  - Aviso rodapé linha 38933 (pre-fix) — "requerem recarregar a página" enganador (precisa restart do serviço Windows, não F5)
- **Recommendation:** RESOLVED — Patches B (frontend) + C aplicados. `data-admin-gated="1"` + `display:none` no botão (já reconciliado pelo JS handler em linha 4357 que mostra apenas para `user.role === 'admin'`). Handler reescrito com `showToast()` persistente, validação JSON inline, tratamento explícito de 401/403, mensagem clara sobre restart do serviço.
- **Status:** resolved
- **Created:** 2026-04-29
- **Updated:** 2026-04-29
- **Note:** USER-FAIL identificado por customer-success-persona — DBA seguia aviso "F5" e novo servidor não aparecia. Diff entre falha de auth, falha de JSON, e falha de rede agora é visível.

---

## FIND-20260429-004 — `sql_servers.json` e `servers.json` desincronizados (modal incompleta)

- **Severity:** P0
- **Category:** reliability
- **Owner specialist:** watcherdb-v33-specialist (follow-up audit)
- **Evidence:** Modal "Gerenciar Servidores" edita apenas `sql_servers.json` (96 entries, schema simples — usado por `app.state.sql_monitoring`) mas a sidebar SPA + KPIs leem `servers.json` (95 entries pre-fix, schema rico com `monitored_servers[]` + credenciais + AG topology — usado por `/api/v3/servers` e `/api/servers`). `DatabaseDiscoveryService` corre só no startup e apenas **actualiza** databases de entries já existentes em `servers.json` — **não cria entries novos**. Resultado: admin adiciona servidor pelo modal → save bem-sucedido em `sql_servers.json` → sidebar nunca mostra (porque `servers.json` não foi tocado)
- **Recommendation:** RESOLVED (parcialmente) — Patch D aplicado: `save_sql_servers_config` agora propaga ids novos para `servers.json` com defaults seguros (`use_windows_auth=true`, `enabled=true`, sem password, `has_alwayson=false`, `ag_name=None`, `ag_listener=None`). Backup automático `servers.json.backup_pre_sync`. Fail-open. Frontend toast mostra `synced_to_inventory` count. **Limitação assumida**: defaults Windows Auth podem falhar em servidores que requerem SQL Auth ou que sejam AG (precisa de pós-edição manual em `servers.json`).
- **Status:** resolved (com limitações documentadas em FIND-20260429-005 e FIND-20260429-008 abaixo)
- **Created:** 2026-04-29
- **Updated:** 2026-04-29
- **Note:** Causa-raiz arquitectónica: produto evoluiu com 2 ficheiros de inventory (depois descobriu-se 3 — ver FIND-20260429-006) mas modal só expõe 1. Refactor proper exigiria UI dedicada de "Adicionar Servidor" com campos completos, em vez de edição raw de JSON.

---

## FIND-20260429-005 — Patch D só faz INSERT — falta UPDATE/DELETE cascade

- **Severity:** P0
- **Category:** reliability + ux
- **Owner specialist:** orchestrator (descoberto durante validação user)
- **Evidence:** Após Patch D, user editou `description` em `sql_servers.json` via modal (adicionou sufixo `- SCOMMSPRD04 - CN_MSSQL_SCOM` aos replicas SCOM para search). Save bem-sucedido em `sql_servers.json` mas `servers.json` ficou com a description antiga. Search no portal não encontrava por "CN_MSSQL_SCOM" porque sidebar lê de `servers.json`. Mesmo problema com DELETE — user removeu entry duplicada via modal, `sql_servers.json` actualizou (96→95), mas `servers.json` manteve o entry fantasma (97 entries com auth vazia)
- **Recommendation:** RESOLVED — Patch F aplicado em `watcherdb_main.py:1152-1230`. Sync handler agora faz **UPSERT + DELETE cascade**:
  - **DELETE primeiro**: entries em `monitored_servers` cujo id já não está em `sql_servers.json` são removidos
  - **UPDATE em seguida**: campos `description`, `environment`, `priority`, `enabled` propagados de sql → inv para ids em ambos. **`port` deliberadamente EXCLUÍDO** — config de rede explícita do operador (named instances / port redirects) não deve ser sobrescrita por default 1433 que possa estar em sql_servers.json
  - **INSERT por fim**: ids novos em sql → inserir em inv com defaults seguros (Windows Auth, sem password)
  - **Idempotente**: re-save sem mudanças → 0 inserts / 0 updates / 0 deletes (write skipped, sem touch ao ficheiro)
  - **Fail-open**: erro de sync não bloqueia save em `sql_servers.json`
  - **Preservados em UPDATE**: `password`, `username`, `use_windows_auth`, `has_alwayson`, `ag_name`, `ag_listener`, `databases`, `databases_discovered_at`, `host`, `instance` (host/instance são imutáveis pos-criação — mudar = servidor diferente)
  - **Backup automático**: `servers.json.backup_pre_sync` antes de qualquer write
  - **Frontend toast** mostra contadores (+N adicionado / ~M atualizado / -K removido) ou "Sem mudanças no inventory"
- **Status:** resolved
- **Created:** 2026-04-29
- **Updated:** 2026-04-29 (Patch F shipped)
- **Note:** Smoke test pré-deploy detectou regressão potencial em `SQLHDSPRD212_I01` (port custom 55305) — motivo de excluir `port` dos UPDATABLE_FIELDS. Próximo save natural pelo modal aplicará automaticamente: -1 DELETE (`SQLHDSQLTST021_I01` órfão histórico identificado em sessões anteriores como débito técnico) sem outras mudanças (idempotente noutros 95 entries). Workaround manual aplicado anteriormente nesta sessão (cleanup CN_MSSQL_SCOM + sync descriptions SCOM) preservado. Backup `servers.json.backup_pre_description_sync_20260429_112142` mantido.

---

## FIND-20260429-006 — Patch D ignora `alwayson_inventory.json` (3º ficheiro de inventory)

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v33-specialist (descoberto pelo user durante audit)
- **Evidence:** `config/alwayson_inventory.json` (8.2KB, 42 entries em `ag_servers[]`, schema `{server, instance, server_instance, ag_name, listener}`) é lido por `modules/monitoring/watcherdb_alwayson_check.py:77` e `api/routers/alwayson.py:683-733` para feature Always On da UI. **Patch D não toca neste ficheiro.** Se admin adicionar AG novo via modal, `alwayson_inventory.json` fica desactualizado → router `/api/alwayson` não vê o AG novo
- **Recommendation:** Estender Patch D: quando entry novo tem `has_alwayson=true` (após admin editar manualmente em `servers.json`) **OU** quando heurística detecta padrão de AG (ex.: prefixos canónicos TAP, ou query a `sys.dm_hadr_*` se conexão for possível), também sincronizar entry para `ag_servers[]` em `alwayson_inventory.json`. Fail-open. Backup automático.
- **Status:** open
- **Created:** 2026-04-29
- **Updated:** 2026-04-29
- **Note:** Cluster com FIND-20260429-005 (mesmo design gap — modal expõe só 1 dos 3 ficheiros). Solução proper exigiria modal v2 com 3 secções (sql_servers / inventory / alwayson) ou — preferível — refactor para 1 ficheiro canónico com discovery automático.

---

## FIND-20260429-007 — Mais paths relativos em `watcherdb_alwayson_check.py:77` e `initialize_configs.py:250`

- **Severity:** P2
- **Category:** reliability
- **Owner specialist:** watcherdb-v33-specialist (sweep CWD audit estendido)
- **Evidence:**
  - `modules/monitoring/watcherdb_alwayson_check.py:77` — `def __init__(self, config_path: str = "config/alwayson_inventory.json", ...)` — default arg com path relativo
  - `scripts/initialize_configs.py:249-256` — `Path("config/alwayson_inventory.json")` relativo
  - `services/database_discovery_service.py` (linhas a confirmar) — `self.servers_json_path` instanciado com path relativo no `__init__` (FIND deferred quando o specialist v33 mapeou o flow)
- **Recommendation:** Aplicar pattern do Patch A/E (constante module-level absoluta via `Path(__file__).resolve().parent`) ou injectar config_dir absoluto via DI a partir de `watcherdb_main._PROJECT_ROOT`. Risk: bug silencioso se Windows Service mudar CWD ou se algum caller chamar de directório diferente. Não bloqueia produção hoje (CWD é alterado correctamente no bootstrap V3.3 wrapper) mas é fragilidade arquitectónica.
- **Status:** open
- **Created:** 2026-04-29
- **Updated:** 2026-04-29
- **Note:** Cluster com FIND-20260429-002 (mesma família CWD bug). Sweep recursivo recomendado: `Grep "Path\(\"config/" --type py` em todo o V3.3 antes da próxima release.

---

## FIND-20260429-008 — Modal sem detecção de aliases / duplicados / smoke test pré-save

- **Severity:** P1
- **Category:** ux
- **Owner specialist:** watcherdb-customer-success-persona (sweep follow-up)
- **Evidence:** Sessão 2026-04-29: user adicionou via modal entry `CN_MSSQL_SCOM_I01` (alias DNS de Always On AG `SQLAGSPRD403`). Os 2 replicas reais (`SQLHDSPRD403_I01`, `SQLHDSPRD404_I01`) já estavam em `servers.json` com config correcta. Modal não preveniu:
  - Adição de alias DNS quando o canónico já existe (`SQLAGSPRD403\I01`)
  - Adição de entry sem credenciais (Windows Auth vazio default → conexão falha → dashboard N/A)
  - Smoke test de conexão antes de gravar (admin não tinha como saber pré-save que a config estava errada)
  - Entry com `has_alwayson=false` apontando para AG real (inconsistente)
- **Recommendation:** Iterar modal v2:
  1. Cross-check com `alwayson_inventory.json` ao detectar entry novo cujo host resolva (DNS) para um IP já presente noutro entry → warning toast "Possível duplicado / alias do servidor X"
  2. Smoke test de conexão pré-save (TCP probe + tentativa de `SELECT 1` se credenciais fornecidas) → se falhar, exibir warning sem bloquear o save
  3. Se descoberta detecta `has_alwayson=true` no smoke test, auto-preencher `ag_name` + `ag_listener` via query a `sys.availability_groups` / `sys.availability_group_listeners`
  4. Validação JSON estrutural mínima já está implementada (Patch C); estender para schema check (`Pydantic model` por exemplo)
- **Status:** open
- **Created:** 2026-04-29
- **Updated:** 2026-04-29
- **Note:** Resolução pelo user na sessão (29/04): em vez de manter alias como entry separado, adicionou sufixo descritivo às descriptions dos replicas (`- SCOMMSPRD04 - CN_MSSQL_SCOM`) — solução pragmática alinhada com convenção do produto (descriptions hifenizadas). Modal v2 deve sugerir esta abordagem proactivamente quando detectar alias.

---

## FIND-20260429-009 — Router `api/routers/config.py` com `require_role(ADMIN)` correcto não está montado

- **Severity:** P2
- **Category:** regression-risk
- **Owner specialist:** watcherdb-v33-specialist (sweep auth audit)
- **Evidence:** `watcherdb/api/routers/config.py:53-87` define endpoint `POST /sql-servers` com `Depends(require_role(UserRole.ADMIN))` correcto + response model normalizado `{"status": "success", ...}`. Mas **nunca foi `app.include_router(config_router)` no `watcherdb_main.py`**. O endpoint inline em `watcherdb_main.py:1118` (resolved em FIND-20260429-001 com `_require_admin` inline) é o que está em produção
- **Recommendation:** Refactor pequeno: montar o router proper com `app.include_router(config_router, prefix="/api/config")` e remover handler inline em `watcherdb_main.py` (DRY). Cuidado: contracts de response divergem (`{"status": "success"}` vs `{"success": true}` — frontend hoje espera `success: true`). Migração exige sync handler frontend (linha 39341 do portal) para suportar ambos OU normalizar o router.
- **Status:** open
- **Created:** 2026-04-29
- **Updated:** 2026-04-29
- **Note:** Não bloqueia funcionalidade hoje (FIND-20260429-001 resolveu segurança via inline). É dívida técnica de DRY + risco de regressão se alguém modificar router.py achando que está em uso. Sugestão: se vai ficar deprecated, marcar com docstring `# UNUSED — kept for reference, see watcherdb_main.py:1118` ou simplesmente eliminar.

---

### Cluster commentary 2026-04-29 (modal Configurações sweep)

**Findings 001-009** emitidos durante audit + fix do flow modal "Gerenciar Servidores" reportado pelo user (DBA Lead) com sintoma "Salvar Configuração não tem efeito". 6 patches A-F aplicados resolveram **001, 002, 003, 004, 005**. **006, 007, 008, 009** abertos para sprint futuro.

Triagem inicial:

- **P0 imediato (resolvidos pelos commits V3.3 sessão 29/04):** 001 (auth), 002 (CWD bug), 004 (sync inventory INSERT), 005 (UPSERT + DELETE cascade)
- **P1 imediato (resolvidos pelo commit):** 003 (UX modal)
- **P1 sprint próximo:** 006 (alwayson_inventory.json sync), 008 (modal v2 com smoke test + auto-detect AG)
- **P2 backlog:** 007 (paths relativos extra), 009 (router config.py refactor)

**Tensões / cross-links:**

- 005 + 006 + 008: cluster "modal incompleta" — todos têm causa-raiz "modal expõe só 1 ficheiro de 3 e não tem UPDATE/DELETE/SMOKE TEST". Recomenda triage conjunta + design ADR-016 "Inventory schema v2" decidir se mantemos 3 ficheiros (e modal v2 cobre todos) ou consolidamos em 1 ficheiro canónico (`servers.json` torna-se source of truth, `sql_servers.json` derivado, `alwayson_inventory.json` é view computada)
- 002 + 007: cluster "CWD/path absoluto" — sweep recursivo `Grep` recomendado antes próxima tag para apanhar quaisquer paths relativos restantes
- 001 + 009: cluster "auth handler dual" — proper refactor consolida em 1 router; hoje há 2 (inline + unused router.py)

**Replicação V6 / V5 / V5.5:** muito provável que herdam todos estes bugs (V6 é fork V5, V5 evoluiu de V3.x). Prompt de auditoria preparado para `watcherdb-v5-specialist` (cobre V5+V5.5+V6) na sessão 29/04.

---

## FIND-20260505-101 — Naming inconsistente para "database" em 3 convenções na mesma BD

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist (charter delta self-doc)
- **Evidence:** Três convenções coexistem em `WatcherDB_Intelligence`:
  - `[Database]` (bracket): `KPI_MSSQL_DB_AVAILABILITY_STG_BLUE` em `database/INSTALACAO_COMPLETA_UNIFICADA.sql:1078`, `KPI_MSSQL_ALWAYSON_STATUS_STG_*` em `:1958`, LONG_LOCKS_STG, ALWAYSON_STATUS_PREV
  - `Database_Name` (underscore): `KPI_MSSQL_DB_SETTINGS_STG_BLUE` em `database/INSTALACAO_COMPLETA_UNIFICADA.sql:11670`, SUSPECT_PAGES_STG, AG_QUEUES_STG, DBCC_HISTORY_STG
  - `DatabaseName` (camelCase): `DATABASE_INVENTORY_SNAPSHOT` em `database/CREATE_DATABASE_CHANGE_DETECTION.sql:88`
  - JOINs cross-table que envolvem nome de DB falham em silêncio (resultado vazio sem erro)
- **Recommendation:** criar `database/STYLE_GUIDE.md` com secção "Naming conventions" + planear migration 2-phase (rename via synonym/computed column transient → ALTER TABLE final) que uniformiza para `Database_Name`. Blast radius: V3.3 + V5/V5.5/V6 (ambos consumem). Coordenar com `watcherdb-v5-specialist` antes de qualquer rename.
- **Status:** open
- **Created:** 2026-05-05
- **Updated:** 2026-05-05
- **Discovery context:** caso SQLHDSQLT301_I02 — query inicial usou `[Database]` (correcto para AVAILABILITY_STG) mas JOIN com SETTINGS_STG requer `s.Database_Name`. Bug silencioso descoberto durante schema introspection.

---

## FIND-20260505-102 — Schemas non-`dbo` da BD `WatcherDB_Intelligence` não documentados no charter V1

- **Severity:** P2
- **Category:** docs
- **Owner specialist:** watcherdb-v1-intel-specialist (charter delta self-doc)
- **Evidence:** `database/INSTALACAO_COMPLETA_UNIFICADA.sql:322-525` cria 8 schemas (`dbo`, `metadata`, `timeseries`, `raw`, `curated`, `alerts`, `library`, `telemetry`) mas charter v1.2.0 do specialist menciona apenas `dbo.KPI_MSSQL_*`. Specialists / orquestrador que consultam o charter assumem que toda a BD é `dbo` e ignoram views consumíveis em `raw.alwayson_health`, `metadata.server_config`, `curated.server_dna_snapshots`, etc.
- **Recommendation:** aplicar charter delta emitido em 2026-05-05 (secção "Schemas existentes na BD") que documenta os 8 schemas + sua função. Resolve-se com paste manual do delta — sem código a alterar.
- **Status:** in-progress (delta aplicado em 2026-05-05)
- **Created:** 2026-05-05
- **Updated:** 2026-05-05

---

## FIND-20260505-103 — Dual inventory de servidores monitorizados sem reconciliação automática

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist + watcherdb-v33-specialist (cross-scope)
- **Evidence:** Existem duas fontes de verdade paralelas para servidores monitorizados sem job de sync entre elas:
  - V1 collector: `metadata.server_config` na BD (`is_active=1` flag)
  - V3.3 portal: `WATCHERDB_V3.3/config/servers.json` → `monitored_servers[]` (lido por `/api/v3/servers` em `watcherdb_main.py:1046`)
  - Caso confirmado empiricamente 2026-05-05: `SQLHDSQLT301_I01` (config_id 158) e `_I02` (config_id 172) presentes em `metadata.server_config` `is_active=1` desde 2026-01-20, mas ausentes do `servers.json` V3.3. Resultado UX: card KPI "SQL Não Respondeu" mostrava a instância, mas clicar abria alert "Servidor não encontrado na lista de servidores".
  - Adicionalmente: `server_config.instance_id` usa formato underscore (`HOST_INSTANCE`); views KPI usam backslash (`HOST\INSTANCE`) — normalização obrigatória nos consumers.
- **Recommendation:** opção A — criar endpoint `/api/v1/servers/sync-check` que compara `metadata.server_config WHERE is_active=1` contra `monitored_servers[]` e devolve diff (instâncias só no V1, só no V3.3, ou em ambos com config divergente); opção B (mais leve) — adicionar verificação ao collector health dashboard que mostra contagem de instâncias em cada fonte e flag visual quando divergem. Não automatizar sync sem decisão prévia sobre fonte autoritativa.
- **Status:** open
- **Created:** 2026-05-05
- **Updated:** 2026-05-05
- **Cross-link:** caso real desencadeou esta sessão (diff `servers.json` para adicionar SQLHDSQLT301_I01/_I02). Após o diff aplicado, divergência mantém-se para outros servidores potencialmente afectados — query rápida de detecção: `SELECT instance_id FROM metadata.server_config WHERE is_active=1` vs IDs em `servers.json`.

---

## FIND-20260505-104 — Auto-discovery feature de databases não documentada no charter V33

- **Severity:** P2
- **Category:** docs
- **Owner specialist:** watcherdb-v33-specialist (charter gap)
- **Evidence:** Existe um sistema completo de auto-discovery em V3.3 com 4 componentes:
  - `services/database_discovery_service.py:109` — `async def discover_server(server_id, executor_func)` por instância
  - `services/database_discovery_service.py:182` — `async def discover_all(max_concurrent=5)` para varrer toda a `monitored_servers[]`
  - `api/routers/database_discovery.py` — endpoints REST que expõem o serviço
  - `tests/unit/test_qa_comprehensive.py` — cobertura QA
  - Mencionado em `docs/guides/referencia_tecnica.md` e `README.md`
  - Confirmado empiricamente: 85 entries em `config/servers.json` têm metadata `databases_discovered_at` + `database_count` com timestamp `2026-05-05T09:47:36.*` (run única recente). Caso SQLHDSQLT301_I01/_I02: 80 + 91 DBs populadas automaticamente.
- **Recommendation:** documentar a feature no charter `watcherdb-v33-specialist.md` (secção nova "Auto-discovery framework"), com pointer para `services/database_discovery_service.py:109/182` + `api/routers/database_discovery.py` + comportamento de side-effect (escreve `databases_discovered_at` + `database_count` em `monitored_servers[]`). Este é o mecanismo natural para popular `databases[]` quando `servers.json` é editado manualmente; futuro orquestrador deve PREFERIR trigger desta feature em vez de reconstruir manualmente o array de DBs a partir de queries HIST.
- **Status:** open
- **Created:** 2026-05-05
- **Updated:** 2026-05-05
- **Discovery context:** descoberta tardia durante esta sessão — orquestrador construiu manualmente um JSON de 111 DBs a partir de `KPI_MSSQL_DB_AVAILABILITY_HIST` (com Update_TS de 2025-12-11 stale), antes de ler o estado actual de `servers.json`. Os 91 DBs ao vivo populados pela auto-discovery hoje 09:47 eram melhores e mais frescos. Lesson learned: ler estado actual ANTES de propor patch (ver feedback memory `feedback_verify_destination_before_patch.md`).
- **Cross-link:** parcialmente mitiga FIND-20260505-103 (auto-discovery resolve o lado das DBs; entries dos próprios servers ainda dessincronizam silenciosamente).

---

## FIND-20260505-105 — Tier inversion: V3.3 "SQL Não Respondeu" diverge de V6 "SQL Services Down"

- **Severity:** P1
- **Category:** regression-risk (tier inversion per `feedback_tier_inversion_rule.md`)
- **Owner specialist:** watcherdb-v33-specialist (consumer fix) + watcherdb-frontend-specialist (i18n proper)
- **Evidence:** Tier hierarchy regra: V6 ≥ V5.5 ≥ V5 ≥ V3.3 sempre (features E labels). Estado actual:
  - **V6** (banking GA): label `"SQL Services Down"` em `WATCHERDB_V6/templates/watcherdb_portal.html:28810` (EN, label canonical)
  - **V3.3** (Standard): label `"SQL Não Respondeu"` em 5 locais hardcoded (`templates/watcherdb_portal.html:24436,24493,30308,30313,34297` per FIND-20260428-003) + view DDL `database/FIX_SERVER_OFFLINE_RECONCILE_COLLECTION_SUCCESS.sql:151` ("SQL Nao Respondeu (collector central)") + `database/INSTALACAO_COMPLETA_UNIFICADA.sql` (mesma string)
  - Origem da divergência: commit `7a9355a` em V3.3 fez rename "SQL Services Down" → "SQL Não Respondeu" (per FIND-20260428-003 nota), mas V6 manteve nome original
  - DBA Lead 2026-05-05 reforça que `"SQL Services Down"` é mais preciso pelo modelo mental DBA-céntrico: "SQL Services" = conjunto lógico (listener + SCM + agent + browser) cuja indisponibilidade afecta clientes, independentemente do estado granular dos Windows services individuais
- **Recommendation:** revert do rename em V3.3 com i18n proper (resolve simultaneamente FIND-20260428-003):
  1. Adicionar chave `kpi.sql_services_down.title` em `static/i18n/pt.json` + `pt-BR.json` + `en.json` com traduções: PT "Serviços SQL Indisponíveis" / PT-BR "Serviços SQL Indisponíveis" / EN "SQL Services Down"
  2. Substituir 5 strings literais em `templates/watcherdb_portal.html` por `data-i18n="kpi.sql_services_down.title"` ou `t('kpi.sql_services_down.title')`
  3. Update view DDL em `database/FIX_SERVER_OFFLINE_RECONCILE_COLLECTION_SUCCESS.sql:151`: `WHEN 'sql_down' THEN 'SQL Nao Respondeu (collector central)'` → `'SQL Services Down (collector central)'` (re-deploy idempotente — view recreate)
  4. Update `database/INSTALACAO_COMPLETA_UNIFICADA.sql` com a mesma mudança (grep e replace coordenado)
  5. V5/V5.5: **CONFIRMADO LIMPOS via grep 2026-05-05** — V5 e V5.5 têm 5 ocorrências de "SQL Services Down" em produção, zero de "SQL Não Respondeu". Sprint de revert é V3.3-ONLY (escopo mais pequeno do que inicialmente projectado).
- **Status:** open
- **Created:** 2026-05-05
- **Updated:** 2026-05-05
- **Cross-link:** FIND-20260428-003 (i18n hardcoded gap) — este finding combina o revert do rename com a regularização i18n já pendente. Fix conjunto resolve ambos.
- **Discovery context:** sessão V3.3 2026-05-05 — DBA Lead apontou que `"SQL Services Down"` reflecte melhor o modelo mental DBA. Verificação cross-product via `watcherdb-v5-specialist` confirmou que V6 nunca renomeou — V3.3 é que divergiu. Tier inversion per regra estabelecida 2026-04-28.

---

## FIND-20260505-106 — DPAPI blob em `servers.json` não é portável entre máquinas

- **Severity:** P1
- **Category:** reliability (deploy-risk)
- **Owner specialist:** watcherdb-v1-intel-specialist (cross-product) + watcherdb-deploy-architect (deploy)
- **Evidence:** `WATCHERDB_V3.3/services/secrets.py:90-99` usa `win32crypt.CryptUnprotectData` SEM flag `CRYPTPROTECT_LOCAL_MACHINE` → DPAPI **user-scope binding**. Apenas a conta Windows que correu `tools/encrypt_secret.py` originalmente consegue decryptar o blob `encrypted:gAAAAA...` em `config/servers.json`. Se `servers.json` for copiado de DEV (encriptado pela conta `TAPNET\dev_user`) para PROD (a correr como `CLIENTDOMAIN\svc_watcherdb`), os blobs ficam **indecifráveis** em produção. O service inicia mas não consegue conectar a nenhuma BD. Mesmo padrão aplica-se a V5/V5.5/V6 — todos partilham `services/secrets.py` (per docstring `:43-49`).
- **Recommendation:**
  1. Adicionar aviso explícito em `deploy/INSTALL_FLOW_V0.2.md` e `deploy/install_orchestrator.py` (Fase 4 farm_inventory_parser.py step) que após copiar `servers.json` para máquina de destino, é OBRIGATÓRIO re-encriptar via `tools/encrypt_secret.py` correndo como o service account de destino.
  2. Idealmente: adicionar smoke test no installer que invoca `services.secrets._get_master_key()` + tenta decrypt do primeiro blob — fail-fast se DPAPI não bater (em vez de descobrir só ao primeiro pedido de conexão SQL).
  3. Considerar usar `CRYPTPROTECT_LOCAL_MACHINE` em vez de user-scope — trade-off entre portabilidade dentro da máquina vs blast radius (qualquer user na máquina pode decryptar). Decisão de produto.
- **Status:** open
- **Created:** 2026-05-05
- **Updated:** 2026-05-05
- **Discovery context:** descoberto durante sessão V3.3 2026-05-05 a tentar decifrar password do `sql_monitoring`. V1 specialist emitiu como PROACTIVE FINDING. Caso TAP DEV não tem este problema porque service account == DBA Lead's domain account, mas em deploys cliente é cenário esperado.

---

## FIND-20260505-107 — V1 collector tem fallback silencioso quando decrypt falha (gera falsos `sql_down`)

- **Severity:** P1
- **Category:** data-integrity (false-positive em monitoring)
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** `WATCHERDB INTELLIGENCE V1/services/collector_service/collectors/collect_server_ping.py:323-327` — quando `EncryptionManager.decrypt()` falha, o V1 collector **usa o valor raw como password** (i.e., tenta autenticar com o token encriptado `gAAAAA...` como se fosse plaintext). Resultado: SQL auth falha mas o collector regista apenas `WARNING "Could not decrypt password, using raw"` em vez de error visível. O resultado em runtime é evento `sql_down` em `KPI_MSSQL_SERVER_OFFLINE_EVENTS` indistinguível de uma falha real de listener TCP — gera ruído em monitoring que parece problema de SQL Server quando na realidade é problema de decryption local do collector.
- **Recommendation:**
  1. Substituir fallback silencioso por **fail-fast**: se `EncryptionManager.decrypt()` falha, raise exception clara que para a colecta dessa instância e regista ERROR (não WARNING) no log + emite event de operational alert.
  2. Distinguir no `KPI_MSSQL_SERVER_OFFLINE_EVENTS` entre `sql_down` (listener TCP genuinamente falha) e `auth_fail` (credenciais inválidas) — diagnostic message diferente para o DBA.
  3. Health check do `.encryption_key`: collector na inicialização deve fazer round-trip encrypt→decrypt de uma string conhecida e fail-fast se não bater.
- **Status:** open
- **Created:** 2026-05-05
- **Updated:** 2026-05-05
- **Discovery context:** PROACTIVE FINDING emitido pelo V1 specialist durante sessão 2026-05-05. **Pode ser relevante para o caso SQLHDSQLT301_I01** (TCP timeout 15s repetitivo) — vale verificar se o `.encryption_key` do V1 collector central existe e está intacto, e se o WARNING "Could not decrypt password, using raw" aparece nos logs do collector. Se aparecer, o "TCP timeout" é falso e o problema é na chave Fernet, não na rede / listener.
---

## FIND-20260506-001 — Modal "SQL Não Respondeu" click → alert "Servidor não encontrado"

- **Severity:** P1
- **Category:** ux
- **Owner specialist:** orchestrator (descoberto durante triage 2026-05-06 manhã)
- **Evidence:**
  - Browser: `http://10.88.8.8:8433/watcherdb` → KPI "SQL Não Respondeu" → modal "SQL Não Respondeu (collector central)" → click instância `SQLHDSQLT301_I01` → alert: `Servidor "SQLHDSQLT301\I01" não encontrado na lista de servidores. Tente buscar manualmente na barra de pesquisa.`
  - Card mostra: `server_name=SQLHDSQLT301_I01`, `event_count=1`, `diagnosis=sql_down`, `diagnosis_desc="SQL Nao Respondeu (collector central)"`, `ping_ok=1`
  - Backend KPI lê BD `WatcherDB_Intelligence` direta (mostra correctamente)
  - Frontend lookup em `allServers` (de `/api/v3/servers`) falha apesar de tentativas em 5 formatos
- **Hipóteses descartadas durante triage:**
  - ❌ NÃO é filtering bug `enabled=null` no API (re-validado: 84 entries têm key 'enabled' MISSING, não null; `dict.get('enabled', True)` retorna default True; SQLHDSQLT301_I01 passa filtro)
  - ❌ NÃO foi causado por commits sprint 2026-04-28 a 2026-05-06 (FIND-004 fix foi noutro KPI: blocked-sessions)
- **Hipóteses pendentes (debug DevTools needed):**
  - Modal "SQL Não Respondeu" usa handler diferente de `selectInstanceFromModal` (ex.: `openTransactionLogQuery` que tem mesmo alert string em linha 40966)?
  - `data-instance-name` HTML attribute encoding mismatch entre render e click?
  - API response cache stale vs servers.json actual?
  - kpiType `server-offline` vs `instance-availability` em modal renderer cause divergência de path?
- **Recommendation:** debug com browser DevTools (F12 console) durante click, capturar logs `[DBG] Buscando servidor`, `[DBG] Servidores disponíveis (primeiros 5)`, etc. Specialist `watcherdb-frontend-specialist` + `watcherdb-v33-specialist` em paralelo (Pattern #7).
- **Root cause (descoberto 2026-05-06 tarde, sem DevTools):** `kpiCards['server-offline'][:30316-30365]` declara `customModal: true` + `customClick: async (instance) => { showServerOfflineDetails(instance); }` mas grep no template confirma **zero call sites** para `customClick`/`customModal` — propriedades em **dead code**. Click handler do generic renderer (`templates/watcherdb_portal.html:33878`) chama directamente `selectInstanceFromModal(this.dataset.instanceName, this.dataset.kpiType, ...)` independentemente do KPI. Lookup contra `allServers` cache (populado por `/api/v3/servers`) falha quando o cache está dessincronizado em relação ao state real de `servers.json`. Padrão idêntico em `tempdb-critical:30287-30291` e `tempdb-warning:30307-30311` (`customClick: openTempDBDiagnostics`) — também afectados. Intent original do dev (modal dedicado por KPI com timeline collector) foi perdido em refactor.
- **Resolution (2026-05-06):** delegação cirúrgica em `selectInstanceFromModal` — antes do lookup genérico, verifica `kpiCards[kpiType]?.customClick` e delega se existir. Try/catch para fallback transparente. Patch aplicado em `templates/watcherdb_portal.html:41067-41085` (19 linhas inseridas, cirúrgico, 1 ponto de mudança vs 13 onclicks). Smoke test 3 cenários:
  - **Cenário A** (bug case, server-offline): **PASS** — modal `serverOfflineModal` abre com timeline collector
  - **Cenário B** (não-regressão, disk-file-system): **PASS** — comportamento inalterado, lookup + SQL Diagnostics
  - **Cenário C** (tempdb-critical): **N/A** (zero instâncias TempDB críticas no momento; lógica idêntica a A — confiança transferida)
- **Status:** RESOLVED (2026-05-06 tarde)
- **Created:** 2026-05-06
- **Updated:** 2026-05-06
- **Workaround actual:** user usa "barra de pesquisa" para abrir SQL Diagnostics manualmente (degradação graceful — handler já dá hint).

---

## FIND-20260506-101 — Phase 0 Collector Health UX nunca commitado em V3.3 (tier-inversion backlog)

- **Severity:** P1
- **Category:** tiering / regression-risk
- **Owner specialist:** watcherdb-v33-specialist (Wave 0 KB bootstrap inventario)
- **Evidence:**
  - `git log -S "_collDelayCell"` em V3.3 = **zero matches**
  - Sprint Phase 0 (FIND-20260505-001 documentado P1 tier-inversion) tem 4 mudancas spec'd: coluna "Atraso", QUIET helpers, modal info 7 estados, CHANGELOG_JOBS_COLETA refresh
  - V5/V5.5/V6 receberam (memorias `session_20260504_collector_health_ux.md` + `session_20260505_v33_phase0_checkpoint.md`)
  - V3.3 **nao** recebeu — tier-inversion ativa (V3.3 < V5.5 < V6 em Collector Health UX)
  - `templates/watcherdb_portal.html:47916` ainda mostra "Proximo" coluna em vez de "Atraso"
  - Wave 0 V3.3 specialist confirmou Phase 0 spec completo em finding mas zero implementation
- **Impact**:
  - Tier-inversion regra (memory `feedback_tier_inversion_rule.md`): V6 >= V5.5 >= V5 >= V3.3 sempre. V3.3 sem Phase 0 = inversao detectada.
  - Cliente V3.3 Std le "Proximo: 81d" para collectors QUIET (UX confusion FIND-20260504-001 P2)
  - Risco "outro tier implementar primeiro" (memory): se V6 advance Phase 1 + V3.3 ainda em pre-Phase 0, gap aumenta
- **Recommendation**: sprint coordenado V3.3 retrofit Phase 0 — 4 mudancas (coluna Atraso, QUIET helpers, modal info 7 estados, CHANGELOG refresh). Estimado ~4h. Ordem 0-3 da spec FIND-20260505-001 seccao 4.
- **Status:** open (DETECTED ha 1 dia, sprint nao autorizado ainda)
- **Created:** 2026-05-06
- **Updated:** 2026-05-06
- **Handoff:** `watcherdb-v33-specialist` (impl Phase 0 V3.3), `watcherdb-frontend-specialist` (visual review pos-impl), `watcherdb-customer-success-persona` (validar UX cliente Std nao degradada)
- **Tags:** #tier-inversion #regression-risk #phase0-retrofit #wave0-finding

---

## FIND-20260506-102 — 3 Windows services com PythonClass apontando para C:\BKP PC TAP\* (security drift cross-cutting)

- **Severity:** P1
- **Category:** security / regression-risk (cross-cutting V1+V3.3+V6)
- **Owner specialist:** watcherdb-deploy-architect (Wave 0 KB bootstrap inventario)
- **Evidence:**
  - `HKLM:\SYSTEM\CurrentControlSet\Services\WatcherDBSSIS\PythonClass` aponta para `C:\BKP PC TAP - 21012026\...\WATCHERPKG\watcherdb_ssis_service`
  - `HKLM:\SYSTEM\CurrentControlSet\Services\WatcherDBWebService\PythonClass` (V3.0 DEV legacy) aponta para `C:\BKP PC TAP - 21012026\...\WATCHERDB_DEV\services\web_service\service`
  - `HKLM:\SYSTEM\CurrentControlSet\Services\WatcherDBV5WebService\PythonClass` aponta para `C:\BKP PC TAP - 21012026\...\WATCHERDB_V5\services\web_service\service`
  - Estado actual: todos Stopped/Disabled. Mas registo activo no SCM permite startup acidental (boot loop, GPO push, admin script).
  - Lesson historica: FIND-20260423-001 (V1 collector path drift) — service registado em BKP path estava a correr codigo de janeiro nao actualizado durante semanas. Sprint resolved 30/04. Risco que estes 3 reg ainda activos repitam o padrao.
- **Impact**:
  - Security: se startup acidental, services correm codigo nao versionado de jan-2026 (binarios desconhecidos, sem audit trail)
  - Compliance: viola SOC 2 CC8.1 (change management) — software em prod nao tracked em git
  - Regression-risk: BKP path nao tem update path; bugs corrigidos em 2026 nao chegam la
- **Recommendation**: `sc.exe delete WatcherDBSSIS && sc.exe delete WatcherDBWebService && sc.exe delete WatcherDBV5WebService` (3 commands manuais, requer admin elevation, nao reversivel sem reinstall). Validar antes que nenhum dos 3 services tem utilidade funcional actual (`Get-Service Watcher* | ? Status -eq 'Running'` mostra so V33+Collector+V6+Hybrid).
- **Status:** open
- **Created:** 2026-05-06
- **Updated:** 2026-05-06
- **Handoff:** `watcherdb-deploy-architect` (action lead), `watcherdb-security-auditor` (compliance angle SOC 2 / ISO 27001), `watcherdb-hacker-team-specialist` (verificar se BKP path tem credentials encriptadas exploraveis se startup acidental)
- **Cross-link:** memoria `session_20260430_v1_collector_sprint.md` (precedent FIND-20260423-001 V1 collector resolved); este finding e cleanup of legacy entries antes que repitam o padrao
- **Tags:** #security #cleanup #bkp-path #cross-cutting #wave0-finding

---

- **Cross-link:** sessão diagnostics 2026-05-06 (este finding é P1 ux residual; não bloqueia banking compliance posture mas afecta workflow incident triage do DBA).

---

## FIND-20260507-101 — V1 collector driver legacy + dynamic ports + Encrypt=Optional incompat = silent KPI gap em ~33 instâncias PRD

- **Severity:** P1
- **Category:** reliability / regression-risk (cross-cutting V1 → V3.3 + V5/V5.5/V6 Pro consumers)
- **Owner specialist:** watcherdb-v1-intel-specialist (causa raiz) + watcherdb-deploy-architect (driver inventory)
- **Evidence:**
  - `services/collector_service/config/servers.json` (e mirror `config/servers.json`) tinha 96 entries com `"driver": "SQL Server"` (legacy MDAC, descontinuado em SQL Server 2014)
  - Driver legacy + SQL Server 2019 RTM FCI + porta TCP dinâmica = TCP fail em 1433. SQL Browser (UDP 1434) entre collector e SQL Servers funciona — confirmado experimentalmente (UDP query devolveu `tcp;58449` para SQLIDSPRD03 e `tcp;60874` para SQLIJSPRD05)
  - `collectors.log` mostrou `[SQL_DOWN_SKIP]` cíclico para 29 instâncias PRD entre 2026-01 e 2026-05-08; KPI `BACKUPS_STG` distinct_instances passou de 24 → 41 após fix
  - DBA reportou explicitamente "não vejo nem no módulo backup da instância nem nos KPIs de backups" para `SQLIDSPRD03\I01` (catalisador da investigação)
  - `async_server_collector.py` esquecido em fix paridade prévia (sync `server_collector.py` já tinha `Encrypt=Optional` desde fix de SQLHDSPRD405_I01) — causa parcial latente meses
  - `Encrypt=Optional` é INVÁLIDO em ODBC Driver 17 (apenas driver 18+); causou regressão pós-deploy do batch driver swap até hotfix `Encrypt=no`
- **Resolution applied:**
  - Commit `5f84805`: driver swap 96 entries `SQL Server → ODBC Driver 17 for SQL Server` em ambos servers.json + paridade Encrypt+TrustServerCertificate em async_server_collector.py + pin port 58449 SQLIDSPRD03 (defensa em profundidade) + pyodbc.Error promoted WARNING→ERROR em base_collector.py
  - Commit `f922f6e`: hotfix `Encrypt=Optional → Encrypt=no` em sync + async (driver 17 incompat resolvido)
  - 27 das 29 instâncias afectadas voltaram a recolher (93% sucesso)
- **Outliers conhecidos (resolved separadamente):**
  - `SQLHDSPRD502_I01`: SQL Server 2008 R2 SP3 (10.50.6000.34) — out-of-support desde Jul 2019; TLS handshake fail com driver 17 (prelogin response timeout). Marcado `enabled: false` em servers.json (este commit). Re-enable requer DBA action: patch SQL 2008 R2 para TLS 1.2 (KB-3144114) ou migração.
  - `SQLSAGEPRD03_I01`: alterna entre `[SQL_DOWN]` (TCP timeout 15s) e `[SQL_DOWN_SKIP]` (availability fresh). Manual ODBC connect com sql_monitoring funciona OK. Suspeita: backup query > 30s timeout numa instância com load alto OU MAX_CONCURRENT 50 a saturar pool. Investigação aberta — sub-tarefa.
- **Recommendation (going-forward):**
  - **Imediato (este commit):** documentação em `feedback_collector_parity.md` (memory) e `project_v1_driver_dynamic_ports.md` (memory)
  - **Curto prazo:** refactor `_build_conn_str()` partilhado entre `server_collector.py` (sync) e `async_server_collector.py` (async) — eliminar a classe inteira de bug paridade
  - **Médio prazo:** DBA team configurar **portas TCP estáticas** em todas as instâncias PRD monitoradas via SQL Server Configuration Manager (best practice banking-grade — elimina dependência runtime de SQL Browser UDP 1434)
  - **Validação contínua:** errors.log agora captura `[DB_ERROR]` (pyodbc.Error promoted); criar alerta operacional se contagem `[DB_ERROR]` > N por hora
- **Status:** resolved (driver swap + Encrypt=no fix em produção; outlier SQL 2008 R2 disabled; outlier SQLSAGEPRD03 sub-task)
- **Created:** 2026-05-07
- **Updated:** 2026-05-08
- **Cross-link:** memory `project_v1_driver_dynamic_ports.md`, `feedback_collector_parity.md`. Push remoto pendente devido a `git push` HTTP 500 / SSL handshake fail (problema separado, sessão dedicada — relacionado com pack 2.93 GiB de binários ainda tracked apesar de `.gitignore` em commit b9e4ca4).
- **Tags:** #reliability #cross-cutting #collector-network #dynamic-ports #driver-modernization #sync-async-parity

---

## FIND-20260508-101 — Repo monolítico inflated 9.4 GiB (.git) / 2.94 GiB pack / 316 commits ahead = git push HTTP 500 / SSL handshake fail

- **Severity:** P1 (governance / disaster recovery — fix funcional fica só local até resolução)
- **Category:** docs / regression-risk / cross-cutting
- **Owner specialist:** watcherdb-deploy-architect (lead) + qualquer dev em commits
- **Evidence:**
  - `git count-objects -vH`: count 337, size 5.89 GiB, in-pack 6710, packs 1, size-pack 2.94 GiB, garbage 2 (515.82 MiB)
  - `du -sh .git`: 9.4 GiB
  - `git status -sb`: `## main...origin/main [ahead 316]` — 316 commits sem push
  - Repo root é `C:/Users/ue_e-snetto/Documents/projetosPython` (cobre WATCHERDB_V3.3 + V3.2 + V5 + V6 + V1 Intelligence + watcherdb-council + outros)
  - `git push` falha com HTTP 500 (pack > 2 GiB) ou `schannel SSL/TLS handshake fail` (pode ser timeout do load balancer GitHub durante upload de 2.93 GiB)
  - `b9e4ca4 chore(gitignore): block large binary artifacts (gguf, exe, datasets)` — adiciona patterns ao .gitignore mas NÃO remove ficheiros já tracked do histórico
- **Impact:**
  - **Dois commits do FIND-20260507-101 (5f84805 + f922f6e) não estão pushed** — fix funcional em produção mas zero backup remoto. Crash do disco local = perde fix
  - DR: branch local é única cópia
  - Compliance: SOC 2 CC8.1 change management exige source-controlled remoto
  - Onboarding: novos devs não conseguem clonar (timeout / 2 GB limit)
- **Hipóteses de causa raiz:**
  - Binários grandes (.gguf modelo LLM, .exe PyArmor builds, .jsonl/.parquet datasets) tracked em commits passados; apesar de removidos do working tree em commits posteriores, ficam no histórico (git mantém até `filter-repo`)
  - Provável `__pycache__/`, `venv/` ou `node_modules/` tracked em algum commit antigo (pre-`.gitignore`)
- **Recommendation (ordem de execução):**
  1. **Imediato (hoje):** identificar os top 20 blobs maiores no histórico:
     `git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '/^blob/' | sort -k3 -nr | head -20`
  2. **Backup antes de filter-repo:** `Copy-Item -Recurse .git .git.backup-pre-filter`
  3. **Coordenar com equipa**: comunicar windows de freeze (~30 min). Todos pull o último estado.
  4. **Filter:** `pip install git-filter-repo` + `git filter-repo --strip-blobs-bigger-than 100M --invert-paths --path '*.gguf' --path '*.exe' --path '*.jsonl'` (ajustar paths conforme step 1)
  5. **Force push:** `git push origin main --force-with-lease`
  6. **Equipa re-clona** (não é possível pull simples após history rewrite)
  7. **Add CI guard:** GitHub Action que rejecta PRs com `git ls-files | xargs du | sort -rn | head -1` > 50 MB
- **Status:** open
- **Created:** 2026-05-08
- **Updated:** 2026-05-08
- **Cross-link:** FIND-20260507-101 (driver fix bloqueado a chegar ao remote por este finding); commit b9e4ca4 (`.gitignore` parcial fix going-forward)
- **Tags:** #governance #git-hygiene #disaster-recovery #cross-cutting #blocking-deploy

---

## FIND-20260528-101 — API keys DeepSeek em plaintext em ~/.claude/settings.json

- **Severity:** P1 (CVSS 3.1 = 8.2 HIGH per `watcherdb-security-auditor` parecer 2026-05-28)
- **Category:** security
- **Owner specialist:** watcherdb-security-auditor (parecer formal entregue)
- **Evidence:** `C:\Users\ue_e-snetto\.claude\settings.json` linhas 60, 72, 78, 85, 91, 126, 130 contêm 2 DeepSeek API keys embebidas em comandos PowerShell aprovados (`$env:DEEPSEEK_API_KEY="sk-fe...e20"` 2x + `$env:DEEPSEEK_API_KEY="sk-fb...1f5"` 6x). Harness do Claude Code persiste comando exacto como permissão hyper-específica.
- **CWE/CVSS:** CWE-312 (Cleartext Storage) primary + CWE-522 + CWE-256. CVSS 3.1 vector `AV:L/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:N` = 8.2 HIGH
- **STRIDE:** Information Disclosure (primary) + Tampering (eval dataset poisoning via leaked LLM key) + Elevation of Privilege + Repudiation
- **Compliance:** SOC 2 CC6.1/CC6.7/CC7.2 FAIL · ISO 27001 A.9.4.3/A.10.1.1/A.10.1.2 FAIL · GDPR Art. 32 partial (ver FIND-20260528-104) · DORA Art. 9 gap em DBA workstation
- **Aggravating factors:** (1) OneDrive sync amplification (path `~/.claude/` em user profile sync-target); (2) malware/infostealer targeting AppData; (3) compound exposure (LLM API + app passwords simultâneos — ver FIND-20260528-102)
- **Recommendation:** (1) **rotacionar AMBAS keys no platform.deepseek.com IMEDIATAMENTE** -- as keys actuais são burned; (2) gerar nova key; (3) armazenar em **Windows Credential Manager** (Option B recomendada vs DPAPI fallback), retrieval pattern `$env:DEEPSEEK_API_KEY=(Get-StoredCredential -Target "deepseek-api" -AsPlainText)`; (4) cleanup manual das 7+ allow entries afectadas em `settings.json`; (5) validar JSON pós-cleanup com `python -m json.tool`
- **Status:** open
- **Created:** 2026-05-28
- **Updated:** 2026-05-28
- **Scope:** Global Claude Code config (afecta TODAS sessões cross-projecto)
- **Discovery:** sessão V3.3 2026-05-28 durante setup Tier 1 (verificação `settings.json` para hook plan-mode confirmation)
- **Effort:** ~45min imediato (rotation + cleanup + storage); ~3.5h total com process control
- **Cross-link:** FIND-20260528-102 (portal passwords mesmo ficheiro) · FIND-20260528-103 (hook disabled = enforcement gap raiz) · FIND-20260528-104 (eval pipeline GDPR exposure secundária)
- **Tags:** #security #credentials #ai-pipeline #compliance #cross-cutting #urgent

---

## FIND-20260528-102 — WatcherDB portal passwords em plaintext em ~/.claude/settings.json

- **Severity:** P1 (CVSS 3.1 = 7.8 HIGH per `watcherdb-security-auditor` parecer 2026-05-28)
- **Category:** security
- **Owner specialist:** watcherdb-security-auditor (proactive discovery durante audit FIND-101)
- **Evidence:** `C:\Users\ue_e-snetto\.claude\settings.json` linhas 75-76 contêm `"password":"watcher2024"` e `"password":"admin123"` em JSON body de comandos `Invoke-WebRequest` para `http://localhost:8660/api/auth/login` (account `salomao`)
- **CWE/CVSS:** CWE-798 (Hard-Coded Credentials) primary + CWE-256 + CWE-522. CVSS 3.1 vector `AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:L` = 7.8 HIGH
- **Risk modifier:** **LOW se** V6 service bound só a localhost (confirmado nos comandos) E passwords não reusadas em outros sistemas. **HIGH se** password reuse em sistemas network-accessible ou `admin123` é default em outras instalações WatcherDB
- **Recommendation:** (1) confirmar V6 localhost-only binding; (2) assess password reuse cross-system; (3) rotacionar se qualquer dúvida; (4) NUNCA password em comando inline -- usar token-based auth (já existe pattern `.runtime_test_token` em uso) ou Credential Manager
- **Status:** open
- **Created:** 2026-05-28
- **Updated:** 2026-05-28
- **Cross-link:** FIND-20260528-101 (mesma raíz harness behavior) · FIND-20260528-103 (mesmo gap de detection)
- **Tags:** #security #credentials #portal-auth #password-reuse

---

## FIND-20260528-103 — advisor_mode.py é no-op + disableAllHooks=true (duplo bypass enforcement)

- **Severity:** P2 (mas contributing factor directo a FIND-101 e FIND-102 -- escalation para P1 se findings 101/102 recorrentes)
- **Category:** reliability + security (governance gap)
- **Owner specialist:** watcherdb-security-auditor (proactive discovery)
- **Evidence:** `C:\Users\ue_e-snetto\.claude\hooks\advisor_mode.py` contém apenas `sys.exit(0)` com comentário "disabled by orchestrator on user request 2026-04-29". Adicionalmente, `~/.claude/settings.json` tem `"disableAllHooks": true` no top-level (bypass secundário independente do hook próprio)
- **Impact:** CLAUDE.md REGRA DE OURO (modo consultor) depende de hook para enforcement automático. Com ambos bypasses activos, todas as guardrails são manuais (user lê e decide cada tool call proposto). Sistema fica em postura de segurança permanentemente reduzida. Foi o gap directo que permitiu FIND-101 e FIND-102 (secrets persistidos sem detection)
- **Recommendation:** (1) entender razão histórica do disable 2026-04-29 antes de reactivar (se foi performance, fazer hook lightweight; se foi bugs, debug + fix primeiro); (2) reactivar `advisor_mode.py` com lógica enhanced -- secret-pattern scan (regex `sk-[a-f0-9]{32}`, `ghp_[a-zA-Z0-9]{36}`, `AKIA[0-9A-Z]{16}`, etc.) que bloqueia commands com secrets inline; (3) remover `disableAllHooks: true` do `settings.json`; (4) timeline definida de re-enablement como sprint item
- **Status:** open
- **Created:** 2026-05-28
- **Updated:** 2026-05-28
- **Effort:** ~2h (debug + enhanced implementation + testing)
- **Cross-link:** FIND-20260528-101 (root cause de detection gap) · FIND-20260528-102 (idem)
- **Tags:** #security #governance #hooks #enforcement-gap #process-control

---

## FIND-20260528-104 — Eval golden set potencialmente com SQL metadata real enviada a DeepSeek sem DPA

- **Severity:** P3 (escalation para P1 se golden set confirmadamente contém PII / banking data)
- **Category:** privacy + compliance
- **Owner specialist:** watcherdb-security-auditor (proactive discovery)
- **Evidence:** `~/.claude/settings.json` allow entries referenciam `data/eval/golden_set_external_eval_dba_personas2_v1.jsonl` e `data/eval/golden_subset_sprint16_verify_28q.jsonl` como input a chamadas DeepSeek judge (`--judge deepseek` em `scripts/eval/run_v6_eval.py`). Se estes JSONL contêm hostnames reais SQL Server, database names, schema info de clientes monitorados -> data transmitida a API third-party
- **Compliance gap:** GDPR Art. 28 requer DPA (Data Processing Agreement) com sub-processor antes de processar PII via API externa. Não há evidência documental de DPA com DeepSeek no contexto WatcherDB. Sector banking: DORA Art. 9 ICT supply chain risk management requer due diligence de third-party processors
- **Risk modifier:** **LOW se** golden set é 100% sintético/anonimizado. **HIGH se** contém qualquer real data de clientes (banking/healthcare/insurance que o WatcherDB monitora)
- **Recommendation:** (1) audit data classification dos 2 ficheiros JSONL (synthetic vs real customer data); (2) se real -> sanitization imediata + documentar DPA com DeepSeek OU substituir judge backend por LLM self-hosted (Ollama local); (3) policy documented sobre o que pode/não pode ir para LLM externo via eval pipeline; (4) se substituição não viável imediatamente, gate eval externa atrás de flag `ALLOW_EXTERNAL_LLM_EVAL=false` por defeito
- **Status:** open
- **Created:** 2026-05-28
- **Updated:** 2026-05-28
- **Cross-link:** FIND-20260528-101 (mesma key leak permitiria attacker reconstruir prompts já enviados via DeepSeek API logs)

---

## FIND-20260529-101 — Backup Policy Drift Detection (roadmap)

- **Severity:** P2
- **Category:** opportunity
- **Owner specialist:** watcherdb-v33-specialist (com handoff watcherdb-v1-intel-specialist + watcherdb-deploy-architect)
- **Evidence:** Proposta DBA cliente 2026-05-29 durante sessão Wave M.3. Industry standard (Redgate SQL Monitor, SolarWinds DPA, Quest Spotlight) tem detecção fraca de config drift — gap real. Discovery técnico inicial validado em SQLHDSTST505\I01 (DIAG-DT): Default Trace enabled, 20d retention real, 100 MB rotativo, captura LoginName+ObjectName via EventClass 164 (Object:Altered).
- **Recommendation:** Iniciar Wave S+2.a (V1 collector novo + 2 tabelas POLICY_SNAPSHOT_STG + POLICY_CHANGES_STG com hash SHA256 + JSON diff) após Wave M.3 V3.3 fechada e validada em produção. Tier Std entrega 80% value; Pro upsell para compliance SOX/PCI/HIPAA.
- **Status:** open
- **Created:** 2026-05-29
- **Updated:** 2026-05-29

### Detalhe

Detectar e auditar mudanças em políticas de backup ao longo do tempo. Ambientes regulados (banking/healthcare/seguros) sofrem 80% incidentes backup por config drift silencioso (DBA novo aplicou template, quick-fix virou permanente, multi-DBA team sem hand-off).

**Scope proposto — Wave S+2 multi-sub-wave** (sequência natural após S+1 baseline engine, alinhado com `project_smart_defaults_initiative`):

- **S+2.a** — V1 collector + 2 tabelas (POLICY_SNAPSHOT_STG BLUE/GREEN + POLICY_CHANGES_STG append-only 90d retention)
- **S+2.b** — V3.3 tile + modal "Backup Policy Changes (7d)" + i18n (pt-PT/pt-BR/en-US)
- **S+2.c** — Default Trace integration para "quem mudou" (best-effort, retention SQL Server-side variável)
- **S+2.d (Pro V5+)** — SQL Audit + AI cause hypothesis + SIEM forward (V6 Banking GA)

**Dimensões a monitorar:**
job enabled/disabled • schedule alterado (`sysschedules.modified_date`) • step command alterado (hash) • recovery_model mudou • AG backup_preference mudou • backup target • CHECKSUM enable/disable • retention • DB scope add/remove

**Tier:**
- Std (V3.3) — detection + Default Trace best-effort
- Pro (V5/V5.5) — SQL Audit + AI hypothesis
- Banking GA (V6) — immutable audit log + chain-of-custody + SIEM

**Pendente pré-design (actualizado 2026-05-29 após DIAG-DT em SQLHDSTST505\I01):**

- ✅ Default Trace status validado em TST: enabled=1, 20d 16h retention real, 100 MB rotativo, 110k eventos no buffer
- ⚠️ Validar Coverage_Minutes em sample PRD alto-volume — pior caso aceitável ≥60min (collector cadence 15min)
- ⚠️ **DESCOBERTA crítica:** filtro inicial proposto (`DatabaseName='msdb' OR ObjectName LIKE '%backup%'`) é amplo demais — em sample 10 rows retornou 8 noise interno (collectors V1 BLUE/GREEN swap a rebuild índices `IX_KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_*`) + 2 auto-stats. **Zero rows de policy change real.** Design S+2.c precisa:
  1. Whitelist específica de system tables msdb (sysjobs, sysjobsteps, sysschedules, sysjobschedules, sysjobservers, syscategories)
  2. Lista configurável de service accounts a excluir (per-cliente: TAP usa convenção `ua_<server>_ag`; outros clientes terão outras)
  3. Exclude pattern `_WA_Sys_*` (auto statistics)
  4. ALTER DATABASE detection via `ObjectName IS NULL + DatabaseName NOT IN system DBs`
  5. WatcherDB_Intelligence excluída do scope (auto-noise de collector próprio)
- Validar tier classification com `v33-feature-matrix-checker`
- Validar value proposition com `watcherdb-customer-success-persona` antes de comprometer scope

**Esforço estimado:** S+2.a+b+c = ~4-6 dias work (Std completo).

**Cross-link:** Wave M.3 session (2026-05-29) — sessão consultiva que produziu este finding após DBA cliente propor feature.

[WAIVER aplicado 2026-05-29 | regra: "AI não escreve ficheiros sem aprovação manual" | scope: append único entry FIND-20260529-101 a findings-inbox.md]
- **Tags:** #privacy #compliance #gdpr #ai-pipeline #third-party-risk

---

## FIND-20260529-102 — System DBs sem backup local em réplicas AG (gap operacional cliente)

- **Severity:** P1
- **Category:** compliance
- **Owner specialist:** watcherdb-customer-success-persona (conduzir comunicação ao DBA cliente) + watcherdb-v33-specialist (validar magnitude + propor view diagnóstica)
- **Evidence:** SMOKE A executado 2026-05-29 sobre WatcherDB_Intelligence retornou 20+ rows (top 20 visíveis) confirmando que múltiplas réplicas AG não têm backup local de master/model/msdb/DBA_RESOURCE_DB. Amostra confirmada: SQLHDSPRD408_I01 (master/model/msdb/DBA_RESOURCE_DB 1500-1860h), SQLRPAPRD02_I01 (970-1022h), SQLHDSPRD405_I01 (1737-1856h), SQLHDSPRD403_I01 (215-229h), SQLHDSPRD412_I01 (333h master), SQLHDSPRD201_I01 (232-256h). DIAG 3'.a confirmou par 411/412: 411 system DBs frescos (~14h), 412 stale (333-878h). Princípio confirmado pelo owner em sessão Wave M.3 (2026-05-29): system DBs (master/model/msdb/tempdb) e DBA_RESOURCE_DB são instance-local — conteúdo difere entre réplicas (logins, jobs, schedules) — logo cada nó AG precisa do seu backup próprio. Apenas user DBs membros do AG seguem padrão primary-only (ou conforme `automated_backup_preference`).
- **Recommendation:** Comunicar ao DBA cliente para configurar backup local de system DBs (master/model/msdb) + DBA_RESOURCE_DB em CADA réplica AG. Pré-requisito para compliance audit (SOX/PCI/HIPAA exigem evidence per-node). Em paralelo, V3.3 emitir view diagnóstica dedicada que liste instâncias AG sem backup local de system DBs — facilita follow-up DBA + serve como evidência ao cliente.
- **Status:** open
- **Created:** 2026-05-29
- **Updated:** 2026-05-29

### Detalhe

**Contexto histórico:** descoberto durante sessão Wave M.3 (2026-05-29) ao tentar criar filtro arquitectural para esconder system DBs delayed em nós AG (considerado FP estrutural). Owner corrigiu durante revisão: o "FP" é na realidade um gap operacional do cliente — DBA configurou backup de system DBs apenas no primary do AG. Wave M.3 v2 foi revertida em consequência. Esta finding regista o gap operacional real que estava mascarado.

**Princípio DBA aplicável (Microsoft + industry consensus):**
- master de 411 ≠ master de 412 — logins próprios, configurações server-level próprias
- msdb tem job history + schedule + backup history próprios por nó (não replicado entre réplicas AG)
- model varia conforme template aplicado por DBA local
- tempdb não precisa backup (recriado a cada start)
- DBA_RESOURCE_DB (custom TAP) — verificar se é instance-local com cliente

**Magnitude observada:**
- ~14 instâncias AG (estimativa do AUDIT-FAILED count SYSTEM_LIKE + AG_NODE = 14 distinct instances)
- 83 rows delayed (system DBs em nós AG) — 54 FULL + 18 DIFF + 11 LOG
- Spread temporal: max 2077h (~87 dias sem backup) em alguns casos extremos

**Risco em ambiente regulado:**
- Falha de master/msdb num nó secondary requer restore a partir do snapshot original — sem backup local = restore impossível, DBA tem de recriar instância do zero perdendo configurações
- Auditoria SOX Sec. 404 / PCI-DSS Req 9.5 / HIPAA Req 164.308(a)(7) — todas exigem **per-node** backup evidence
- ISO 27001 A.12.3.1 — backups de informação (system DBs contêm información de configuração security-relevant)

**Proposta de ferramenta de apoio (V3.3, Std-eligible):**
Criar view ou KPI tile dedicado `Backup AG System Gap` que liste:
- Instance (réplica AG)
- AgName (cluster)
- Database (system DB)
- Last_Backup_Date (NULL ou stale)
- Suggested action (configurar SQL Agent job local + maintenance plan)

Esta view serve como input ao DBA cliente para corrigir o gap nos ~14 nós identificados.

**Cross-link:** Wave M.3 session (2026-05-29) revertida — proposta original de hide-by-filter foi corrigida em runtime pelo owner. Princípio DBA captura encontra-se em proposta de memória `feedback_ag_system_db_backup_principle.md`.

[WAIVER aplicado 2026-05-29 | regra: "AI não escreve ficheiros sem aprovação manual" | scope: append FIND-20260529-102 + revert 4 patches Wave M.3 v2 (helpers.py + intelligence_kpis.py)]

### Update 2026-05-29 — generalização cross-client confirmada

Owner clarificou em sessão posterior que esta finding **NÃO é TAP-specific**. Qualquer cliente que use Always On Availability Groups e não configure backup per-node de system DBs (master/model/msdb) + DBs instance-local em cada réplica tem exactamente o mesmo gap operacional. A lista de ~14 instâncias citadas em "Magnitude observada" é evidence específica TAP, mas o **princípio é universal**:

> Em ambientes AG, system DBs e DBs instance-local são SEMPRE per-node (limitação SQL Server). Qualquer cliente que faça backup só num nó tem o gap, **independentemente da ferramenta de backup usada** (TSM/TDP, Commvault, NetBackup, Veeam, Rubrik, native `BACKUP DATABASE`, Maintenance Plans, Ola Hallengren, Idera SQL Safe, Redgate SQL Backup, custom PowerShell, etc).

**Detecção é agnóstica ao backup tool:** `msdb.dbo.backupset` é o groundtruth universal — qualquer backup tool regista entries lá. Wave M (2026-05-20) já implementa a infraestrutura correcta: distinção AG vs non-AG via `KPI_MSSQL_ALWAYSON_STATUS_STG` é **arquitectural**, não dependente de naming/tool/scheduler. WatcherDB classifica `412 master` como STANDALONE porque master não é AG member — e isso é correcto cross-client.

**Implicação para roadmap + posicionamento:** quando esta finding for actuada (comunicação ao DBA cliente para configurar backup local), a mensagem pode ser packaged como **differentiador competitivo WatcherDB**: detecção agnóstica ao backup tool. Outros monitoring tools (Redgate SQL Monitor, SolarWinds DPA, Quest Spotlight) que detectam só falhas TSM/Commvault não capturariam este gap porque dependem de integração tool-specific.

**Implicação técnica:** o "problema" original (412 system DBs delayed no portal) NÃO era FP do WatcherDB — era detecção correcta de gap operacional cliente. Reverter Wave M.3 v2 foi a decisão certa por mais este motivo (manter sinal real visível).

### Update 2026-05-29 — categorização 2A vs 2B-CONTINUOUS / 2B-INTERMITTENT (cluster AG TAP)

Após descoberta `SILENT_FAILURE_SUSPECTED` empírica em **2 servers** do cluster AG TAP (`B590B985-296A-4FD8-BE7F-349FF5874768`), refinamos a categorização do gap operacional:

| Categoria | Causa raiz | Exemplo cluster TAP | Detecção |
|---|---|---|---|
| **2A** | DBA não configurou job para system DBs em algum nó | (não confirmado neste cluster — jobs `_LOCAL` existem em 411 E 412) | sysjobhistory vazio + backupset vazio |
| **2B-CONTINUOUS** | Tool degraded prolongado, scope global | **SQLHDSPRD412** (secondary): 7d, TODOS 6 jobs falham, `ANS1235E (RC-1)` IBM Storage Protect fatal | sysjobhistory ✅ succeeded + backupset vazio + log file tool com erro fatal contínuo |
| **2B-INTERMITTENT** | Tool partial scope ou onset recente | **SQLHDSPRD411** (primary): 18h, só LOG backups falham; FULL/DIFF de 28/05 ainda passaram | sysjobhistory ✅ succeeded + backupset vazio só em janelas específicas + transição last_good→failed identificável |

**Implicação operacional:** a "magnitude observada ~14 instâncias" da finding original pode ser maioritariamente **2B-CONTINUOUS ou 2B-INTERMITTENT** — DBA assume cobertura porque `sysjobhistory` reporta succeeded. Sem WatcherDB ou outro tool agnóstico (FIND-104), permanece invisível.

**Acção sugerida:** correr a query `SILENT_FAILURE_SUSPECTED` (FIND-104 query embedded) em todos os ~14 servers do AUDIT-FAILED original para categorizar 2A vs 2B-CONTINUOUS vs 2B-INTERMITTENT per server. Resultado quanta-instâncias por categoria informa scope realista do gap real e prioriza tactical do roadmap.

**RPO impact diferenciado:**
- 2A: DBA fix simples (criar job)
- 2B-CONTINUOUS: incident reportável (sem backup há dias/semanas)
- 2B-INTERMITTENT: investigação root cause TSM-side / network / credentials degradação

**Cross-link:** [[FIND-20260529-104]] (silent failure detection — primary tool para reclassificar 2A→2B-*). Memory [[r14-silent-backup-failure]] reactivada com este pattern (V1 collector enhancement scope clarificado).

---

## FIND-20260529-103 — Backup Job Convention Auto-Detect (cross-client capability)

- **Severity:** P3 (downgrade 2026-05-29 — ver Update no fim)
- **Category:** opportunity
- **Owner specialist:** watcherdb-v33-specialist + watcherdb-v1-intel-specialist (collector V1) + watcherdb-customer-success-persona (validar generalização)
- **Evidence:** TAP usa sufixo `_LOCAL` (`DBA_FULL_BACKUP` vs `DBA_FULL_BACKUP_LOCAL`) para distinguir jobs invocados via TSM (sem sufixo, cobre DBs em AG) vs SQL Server Agent (com sufixo, cobre system DBs + DBs fora AG). Owner confirmou em sessão 2026-05-29 que padrão é provável cross-client — empresas com backup tools enterprise (IBM TSM/TDP, Commvault, NetBackup, Veeam, Rubrik) tipicamente seguem esta divisão arquitectural, convenções de naming variam mas o split é universal.
- **Recommendation:** Implementar S+2.e (sub-wave do Smart Defaults Initiative): collector V1 auto-detect convenção naming via inspecção `msdb.dbo.sysjobs.name` + cross-reference `backupset` → infere se cliente usa convenção sufixo + valida cobertura (system vs AG DBs). Tabela nova `KPI_MSSQL_BACKUP_JOB_CONVENTION_STG` com confidence score. KPI Backup Delayed refinado: distingue "job falhando" (tem job, não corre) vs "config gap" (não tem job para esses DBs).
- **Status:** open
- **Created:** 2026-05-29
- **Updated:** 2026-05-29

### Detalhe

**Padrão arquitectural cross-client** observado: empresas com backup tools enterprise separam SQL Server jobs em 2 categorias:
1. Jobs **externos** invocados pelo backup tool (TSM/TDP/Commvault/NetBackup/Veeam) → cobrem DBs em AG
2. Jobs **locais** invocados pelo SQL Server Agent → cobrem system DBs + DBs não-AG

Convenções naming variam per-cliente:
- TAP: sufixo `_LOCAL`
- Outros possíveis: `_NATIVE`, `_SQL`, `_LOCAL_ONLY`, `_SYSTEM`, `_TSM_EXCLUDED`
- Alguns clientes: sem convenção (jobs ad-hoc nomeados individualmente)

**Proposta tabela `KPI_MSSQL_BACKUP_JOB_CONVENTION_STG`** (V1, BLUE/GREEN ou snapshot):

```
Instance VARCHAR(64)
Convention_Type VARCHAR(32)  -- 'SUFFIX_LOCAL', 'SUFFIX_NATIVE', 'NONE', 'CUSTOM'
Local_Pattern VARCHAR(64)    -- exact LIKE pattern detectado
Remote_Pattern VARCHAR(64)   -- complementar
Local_Covers VARCHAR(128)    -- 'SYSTEM,NON_AG' | 'SYSTEM' | 'ALL_NON_AG' | etc.
Confidence VARCHAR(16)       -- HIGH (>=80% jobs match), MEDIUM (50-80%), LOW (<50%), NONE
Sample_Jobs NVARCHAR(MAX)    -- top 5 jobs per categoria (evidence)
Detected_TS DATETIME2
Update_TS DATETIME2
```

**Algoritmo auto-detect (Smart Defaults compliant):**

1. Para cada Instance, scan `sysjobs.name` por padrões sufixo repetidos (cardinalidade ≥3)
2. Cross-reference: para cada candidate pattern, identifica qual cobre system vs AG DBs (via `backupset` join `sysjobs`)
3. Score confidence baseado em cobertura clara
4. Confidence LOW/NONE → fallback comportamento Wave M actual

**Refinement KPI Backup Delayed** (futura Wave M.4 ou similar):

- Inst AG com Confidence≥MEDIUM e system DB delayed + tem job `_LOCAL` enabled → "**Job `DBA_FULL_BACKUP_LOCAL` está a falhar / não corre — investigar execução**"
- Inst AG com Confidence≥MEDIUM e system DB delayed + sem job `_LOCAL` → "**Config gap — falta job local para system DBs neste nó**"
- Inst AG com Confidence LOW → comportamento Wave M actual (sem refinement)

**Diferenciação competitiva:**
Redgate SQL Monitor, SolarWinds DPA, Quest Spotlight, Idera SQL DM NÃO fazem este nível de inferência. Insight directo + transparency (cliente vê o que WatcherDB inferiu sobre os seus jobs, pode auditar e corrigir se inferência falhou).

**Tier:** Std-eligible. Auto-detect não usa AI/ML — é statistical pattern matching.

**Cross-link:** [[FIND-20260529-101]] (S+2 roadmap parent — partilha collector V1 + tabelas snapshot), [[FIND-20260529-102]] (gap system DBs sem backup local — auto-detect refina detecção de ~14 instâncias afectadas em TAP).

**Esforço estimado:** ~2-3 dias work (collector V1 + tabela + consumer V3.3 refinement). Sub-wave paralela a S+2.a-d.

[WAIVER aplicado 2026-05-29 ~15:55 | regra: "AI não escreve ficheiros sem aprovação manual" | scope: append único FIND-20260529-103 a findings-inbox.md]

### Update 2026-05-29 — framing revisto após visão agnóstica do owner

Owner clarificou em sessão posterior (após 3 iterações de modelo): WatcherDB tem que estar preparado para **todo tipo de cliente com qualquer meio de se fazer backup**. Foundation cross-client é `msdb.dbo.backupset` directamente — qualquer ferramenta de backup (TSM/TDP, Commvault, NetBackup, Veeam, Rubrik, native `BACKUP DATABASE`, Maintenance Plans, Ola Hallengren, Idera SQL Safe, Redgate SQL Backup, custom PowerShell `Backup-SqlDatabase`, etc) regista entries lá.

**Re-classificação desta finding:**

- **Severity: P2 → P3** (downgrade de "roadmap normal" para "nice-to-have enhancement opcional")
- **NÃO é foundation** para KPI Backup Delayed funcionar agnostically — Wave M (2026-05-20) + `KPI_MSSQL_ALWAYSON_STATUS_STG` já cobre o core agnóstico
- **É enhancement para insights operacionais finos**: ex. "scheduler TSM parece desconfigurado em SQLHDSPRD408 — modo Local não executou há 7d", ou "este cliente usa Commvault, parece desligado da janela noturna"
- **Mais natural como Pro-tier feature (V5+)** — insight tool-specific complementa core KPI agnóstico do Std tier

**Recommendation revista:** considerar S+2.e como **Pro-tier (V5+) enhancement**, NÃO Std (V3.3) requirement. Std deve focar em foundation agnóstica:
- Wave M existente (backupset + ALWAYSON_STATUS_STG cross-reference)
- FIND-101 drift detection via backupset patterns over time
- FIND-102 per-node backup validation para system DBs em nós AG

Algoritmo auto-detect (4 camadas, Camada D anchor empírico via `sysjobhistory + backupset`) mantém-se conceitualmente válido — mas **desnecessário para core Std monitoring**. Implementação fica para wave futura no roadmap Pro-tier se cliente Pro pedir insights tool-specific.

**Cross-link adicional:** [[FIND-20260529-102]] update "generalização cross-client confirmada" — princípio agnóstico aplica-se a ambas findings.

[WAIVER aplicado 2026-05-29 ~16:10 | regra: "AI não escreve ficheiros sem aprovação manual" | scope: 3 edits coordenados findings-inbox.md (FIND-102 append cross-client note + FIND-103 severity P2->P3 + FIND-103 append framing revisto)]

---

## FIND-20260529-104 — Silent Backup Failure Detection (differentiator competitivo)

- **Severity:** P1
- **Category:** opportunity + reliability + compliance
- **Owner specialist:** watcherdb-v33-specialist + watcherdb-customer-success-persona (pitch packaging) + watcherdb-v1-intel-specialist (collector V1 enhancement) + watcherdb-marketing-strategist (competitive narrative)
- **Evidence:** Caso TAP 2026-05-29 cluster AG `B590B985-296A-4FD8-BE7F-349FF5874768` (2 servers, padrões distintos). **SQLHDSPRD412 (secondary):** 7d completos (22/05 21:00 → 29/05 15:45), TODOS 6 jobs `DBA_*_BACKUP[_LOCAL]` reportam ✅ "succeeded" + backupset vazio. Log file `BackupFull.LocalDBs.log` mostra `ANS1235E (RC-1) An unknown system error has occurred from which IBM Storage Protect cannot recover` + `Total SQL backups attempted: 0`. Pattern CONTINUOUS GLOBAL. **SQLHDSPRD411 (primary):** silent failure recente em LOG backups (28/05 21:45 → presente, ~18h); FULL/DIFF de 28/05 20:45-21:00 ainda `BACKUP_CONFIRMED` (5 entries). Pattern INTERMITTENT PARTIAL. RPO impact: NPSODBC (user DB do AG) sem LOG backup há ~18h. **Monitoring baseado em `sysjobhistory` (Redgate / SolarWinds / Quest / Idera / native SQL alerts) NÃO detecta estes casos. WatcherDB baseado em `backupset` agnóstico detecta arquitecturalmente** — ambos servers já flagged via Backup Delayed antes desta sessão.
- **Recommendation:** Capitalizar como differentiator competitivo packageable. KPI Backup Delayed Std já detecta arquitecturalmente (Wave M). Tornar mensagem mais explícita no UX: card/modal pode mostrar "silent failure suspected: SQL job succeeded but no backupset entry" quando pattern detectado. Sub-categoria de FIND-102 mas distinta: não é "DBA não configurou", é "DBA configurou mas tool falha silently". Cross-link [[r14-silent-backup-failure]] reactivada — V1 collector enhancement com scope clarificado (5 campos: Silent_Failure_Start_TS, Scope, Last_Good_Backup_TS, Pattern, Affected_Jobs).
- **Status:** open
- **Created:** 2026-05-29
- **Updated:** 2026-05-29

### Detalhe

**Pattern arquitectural cross-client** (qualquer backup tool):

```sql
-- Heurística silent backup failure detection (agnostic, qualquer backup tool)
-- Detecta: job SQL Agent reporta succeeded + backupset vazio na janela
-- temporal do job = silent failure confirmada arquitecturalmente
DECLARE @lookback_hours INT = 168;   -- 7d range default

;WITH backup_job_runs AS (
    SELECT
        j.name AS job_name,
        msdb.dbo.agent_datetime(h.run_date, h.run_time)                            AS run_start,
        DATEADD(SECOND,
                (h.run_duration/10000)*3600
              + ((h.run_duration%10000)/100)*60
              +  (h.run_duration%100),
                msdb.dbo.agent_datetime(h.run_date, h.run_time))                   AS run_end,
        h.run_status,
        h.message
    FROM msdb.dbo.sysjobs j
    INNER JOIN msdb.dbo.sysjobhistory h ON h.job_id = j.job_id
    WHERE h.step_id = 0                                  -- job-level outcome
      AND h.run_status = 1                               -- succeeded
      AND msdb.dbo.agent_datetime(h.run_date, h.run_time) >= DATEADD(HOUR, -@lookback_hours, GETDATE())
      AND UPPER(j.name) LIKE '%BACKUP%'                  -- backup-related jobs
)
SELECT
    r.job_name, r.run_start, r.run_end,
    DATEDIFF(SECOND, r.run_start, r.run_end)               AS run_duration_sec,
    (SELECT COUNT(*) FROM msdb.dbo.backupset bs
     WHERE bs.backup_start_date  >= r.run_start
       AND bs.backup_finish_date <= DATEADD(HOUR, 1, r.run_end)) AS backupset_entries_in_window,
    CASE
        WHEN (SELECT COUNT(*) FROM msdb.dbo.backupset bs
              WHERE bs.backup_start_date  >= r.run_start
                AND bs.backup_finish_date <= DATEADD(HOUR, 1, r.run_end)) = 0
        THEN 'SILENT_FAILURE_SUSPECTED'
        ELSE 'BACKUP_CONFIRMED'
    END                                                  AS Verdict,
    r.message                                            AS sql_agent_message
FROM backup_job_runs r
ORDER BY Verdict DESC, r.run_start DESC;
```

**Aplicável a qualquer cliente com qualquer ferramenta:**
TSM/TDP (`ANS*` codes — caso TAP), Commvault (`CV*` codes), NetBackup (`bp*` exit codes), Veeam (`VeeamException`), Maintenance Plans custom (típico `.cmd`/`.ps1` sem `exit /b %errorlevel%`), Ola Hallengren com `@ExecuteAsCommand` mal configurado, qualquer tool invocado via `xp_cmdshell` sem propagação errorlevel.

**Limitações conhecidas (caveats):**
- "Backup confirmed" garante apenas que ALGUMA DB foi backed up — não que TODAS as DBs esperadas foram (falso negativo: job multi-DB com falha parcial). Refinement Pro-tier requer parse de job step command para identify expected DBs per tool.
- Slack +1h na janela pode produzir falso positivo se backup terminar >1h após job exit (jobs longos com hand-off).
- `step_id=0` captura outcome do job inteiro, não por step individual — para granularidade per-step, query precisa ajuste.

**Cross-check framework (decisão de design):**

| Camada | Precisa cross-check com tool externa? |
|---|---|
| **Detection** (Std foundation) | **NÃO** — backupset ausente + sysjobhistory succeeded = silent failure confirmada arquitecturalmente |
| **Diagnose root cause** (Pro enhancement) | OPCIONAL — tool-specific integration (parse `dsmerror.log`, `tdpsqlc query tsm`, Commvault REST, NetBackup `bpdbjobs`, etc) |

**Recomendação cliente complementar (DBA-side fix):** editar `.cmd` files para incluir `exit /b %errorlevel%` no fim, garantindo que falha do `tdpsqlc` (ou outro tool) propaga ao `xp_cmdshell` → SQL Agent. Repõe `sysjobhistory` como source fiável. WatcherDB pode emitir runbook automatizado com fix template. Sem este fix, qualquer monitoring `sysjobhistory`-based fica cego.

**Differentiator competitivo:**
- Redgate SQL Monitor → não detecta (foca em `sysjobhistory`)
- SolarWinds DPA → não detecta
- Quest Spotlight → não detecta
- Idera SQL DM → não detecta
- WatcherDB → **detecta arquitecturalmente** sem precisar de cross-check tool-specific

Caso cluster AG TAP é prova empírica dupla — em 411 (primary), 8+ runs verdes mas LOG sem backup há 18h; em 412 (secondary), 100+ runs verdes em 7d sem backup nenhum. WatcherDB já estava a flagar via Backup Delayed. Pitch packageable: "vejam 8+ execuções verdes no vosso dashboard, e nós dissemos vai há semanas — e teríamos evitado RPO violation se tivessem visto antes".

**Padrão arquitectural a capturar no V1 collector enhancement (R+14 reactivada):**

| Campo | Tipo | Exemplo cluster TAP |
|---|---|---|
| Silent_Failure_Start_TS | DATETIME2 | 411 = 2026-05-28 21:45; 412 = 2026-05-22 21:00 |
| Silent_Failure_Scope | VARCHAR(32) | 'GLOBAL_INSTANCE' (412) / 'JOB_TYPE_LOG' (411) / 'JOB_INDIVIDUAL' |
| Last_Good_Backup_TS | DATETIME2 | 411 = 2026-05-28 21:00 (LOG); 412 = pré-22/05 |
| Pattern | VARCHAR(16) | 'CONTINUOUS' (412) / 'INTERMITTENT' (411) |
| Affected_Jobs | NVARCHAR(MAX) | JSON: ["DBA_LOG_BACKUP","DBA_LOG_BACKUP_LOCAL"] (411) / TODOS (412) |

**Cross-link:** [[FIND-20260529-102]] update categorização 2A/2B/2B-CONTINUOUS/2B-INTERMITTENT — silent failure é causa raiz primária do gap original. [[FIND-20260529-101]] (S+2 drift detection) pode incluir silent failure patterns como signal. [[FIND-20260529-103]] convention auto-detect (P3 opcional Pro-tier) — diagnose enrichment complementar. Memory [[r14-silent-backup-failure]] reactivada do DEFERRED após evidência cluster AG.

**Tier:** Std-eligible. Detection arquitectural sem AI/ML — pattern matching trivial. Diagnose enrichment per tool é Pro-tier (V5+).

**Esforço estimado:** Std detection já existe via Wave M (Backup Delayed). UX refinement (card/modal hint "silent failure suspected" + dedicated KPI tile) = ~1-2 dias. V1 collector enhancement com 5 campos = ~2h. Pro-tier diagnose enrichment por tool integrado = ~3-5 dias per tool.

[WAIVER aplicado 2026-05-29 ~17:00 | regra: "AI não escreve ficheiros sem aprovação manual" | scope: 2 edits coordenados findings-inbox.md (FIND-102 append categorização 2A/2B + FIND-104 append novo silent failure detection)]
---

## FIND-20260611-101 -- Dashboard payload 168MB: backup_status raw lists sem consumidor

- **Severity:** P1
- **Category:** performance
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** cache/dashboard_snapshot.json (167.8MB total; backup_status.instances=204.064 rows + no_checksum_instances=203.680 rows = 167.7MB). Frontend usa apenas counts/by_env (watcherdb_portal.html:30618-30792, 42070; grep no_checksum_instances no portal = 0 matches). Modais usam endpoints SQL dedicados ja agregados (intelligence_kpis.py:1398 backup-no-checksum GROUP BY -- mesmo problema 200k ja tinha sido corrigido no modal, mas payload do dashboard ficou). Serializacao JSON de 168MB por request (poller 30s x users) = CPU spiral; contribui para "signal timed out" alem do cold-cache (FIX SWR 2026-06-11).
- **Recommendation:** Drop raw lists do payload do dashboard (no_checksum_instances=[] + remover do agregado backward-compat instances); counts/by_env intactos. APLICADO 2026-06-11 em helpers.py (collect_backup_status). Follow-up opcional: agregar no_checksum no SQL (como o modal) para poupar tambem a transferencia DB->API de 203k rows por coleta.
- **Status:** fixed (pending validation pos-restart + propagacao V6)
- **Created:** 2026-06-11
- **Updated:** 2026-06-11

[WAIVER aplicado 2026-06-11 | regra: AI nao escreve ficheiros sem aprovacao manual | scope: fix helpers.py + FIND-101 append + .gitignore cache/]

---

## FIND-20260612-101 -- Card-vs-modal semantic drift: 10 divergencias nos KPIs do dashboard

- **Severity:** P1
- **Category:** ux
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** Auditoria 2026-06-12 (3 levantamentos: KPI_METADATA portal 29 cards x colectores helpers.py x branches instances/{kpi_type}). Caso reportado pelo user: card Backup Log Failed=54 (unresolved-only Wave R+13, ceiling 14d STG) vs modal=12 (janela 24h Wave O, sem unresolved). Padrao: waves R+13/R+11.3/D evoluiram cards, modais ficaram com semantica legacy. Divergencias: (1) backup-log-failed janela+unresolved; (2) backup-failed 7d sem unresolved; (3) backup-no-checksum modal 7d vs card sem janela; (4) deadlocks card=SUM eventos+Is_Available vs modal=instancias sem filtro; (5) memory-critical modal sem exclusao offline (card exclui); (6) disk-latency idem; (7) processes-alarm card State IN (WARNING,CRITICAL) vs modal Count>0; (8) blocked-users card 15min SQL vs modal 5min Python; (9) transaction-logs-warning card exclui instancias com critical + sem freshness vs modal todas+24h (mesmo risco disk-fs-warning); (10) instance-availability-off card incrementado por service_status coupling vs modal so Ping_OK=0. Subtilezas: always-on exemption adaptativa so no card; server-offline DET dedupe vs GROUPED; detail/filegroup-usage usa Percent_Used raw nao-MAXSIZE-aware. Lateral: _build_jobs_conn_str usa Trusted_Connection=yes (viola Regra de Ouro #2 -- finding proprio recomendado); FRESHNESS capacity=1440 vs comentarios "60 min"; error-log fallback remove janela silenciosamente; view canonical KPI_MSSQL_DEADLOCKS_AGG_VIEW sem colunas State/Severity/Last_Deadlock que helper pede (drift schema).
- **Recommendation:** Alinhar modais a semantica dos cards (precedente Wave M.2 backup-delayed). P1 (trio backup + deadlocks) APLICADO 2026-06-12 Wave W (intelligence_kpis.py + portal titulos "(Unresolved)"). P2 restantes (itens 5-10 + subtilezas) em wave follow-up W+1. Validacao pos-restart: abrir os 4 modais e comparar com cards.
- **Status:** partially-fixed (P1 shipped Wave W, pending validation; P2 open)
- **Created:** 2026-06-12
- **Updated:** 2026-06-12

[WAIVER aplicado 2026-06-12 | regra: AI nao escreve ficheiros sem aprovacao manual | scope: Wave W bundle 7 ficheiros]

---

## FIND-20260612-102 -- Modal "Gaps em Backup LOG" partido silenciosamente desde 2026-04-21 (Msg 207 mascarado como verde)

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** modules/monitoring/queries.py BACKUP_LOG_GAPS_ANALYSIS: ORDER BY final referenciava fg.LastLogBackupTime -- coluna INEXISTENTE na CTE FinalGaps (real: LogBackupTime; LastLogBackup e so alias de output). Introduzido em d1e645e (2026-04-21). Msg 207 em TODAS as execucoes -> endpoint /api/queries/backup-gaps-log 500. Frontend (watcherdb_portal.html ~19303) fazia res.json() SEM res.ok check -> gaps=[] -> modal verde "Nenhum gap significativo encontrado" durante ~7 semanas num surface RPO-critical. Descoberto pelo user 2026-06-12: KPI Backup Delayed acusava LOG gap 2h26 (SQLHDSQLT103_I01/TDH_MDS) e drill dizia "sem gaps". Bonus: Severity CASE usava GapHours raw (NULL para gap aberto) -> gaps abertos caiam sempre em LOW.
- **Recommendation:** APLICADO 2026-06-12: (a) ORDER BY corrigido fg.LogBackupTime; (b) res.ok check com throw -> catch renderiza erro vermelho; (c) Severity CASE usa EffectiveGapHours. Pendente: audit das queries irmas (BACKUP_GAPS_SUMMARY/STATISTICS/FULL/DIFF) + scan de error-masking noutros fetches (agent em curso). Padrao a institucionalizar: NUNCA res.json() sem res.ok em data-fetches; estado vazio != estado de erro. Relacionado: divergencia semantica KPI (1h/2h) vs drill (2h/6h/12h) fica para Wave W+1 (FIND-20260612-101 P2).
- **Status:** fixed (pending validation pos-restart + audit alargado + propagacao V6)
- **Created:** 2026-06-12
- **Updated:** 2026-06-12

[WAIVER aplicado 2026-06-12 | regra: AI nao escreve ficheiros sem aprovacao manual | scope: fix gaps LOG + FIND-102]

---

## FIND-20260612-103 -- Audit "partidos silenciosamente": +2 queries 100% broken, 1 suspeita, 8 falso-OK frontend

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** Audit sistematico 2026-06-12 (sequela do FIND-20260612-102): 55 queries SQLQueries analisadas + ~140 call-sites .json() no portal. QUERIES PARTIDAS 100% (verificadas por leitura directa): (1) DEADLOCKS_ANALYSIS queries.py:721-726 -- UNION ALL orfao apos bloco IF/ELSE END sem SELECT seguinte, so comentarios + ORDER BY; erro de sintaxe; endpoint /api/queries/deadlocks 500 sempre (falha VISIVEL -- SQL Diagnostics verifica response.ok). (2) BACKUP_HISTORY_ANALYSIS queries.py:1983 -- CASE Recommendation referencia LogBackupIssue que e alias do MESMO SELECT (linha 1937), nao coluna da CTE BackupInfo; Msg 207; endpoint /api/queries/backup-history-analysis 500 sempre (visivel). SUSPEITA: SERVER_PARTITIONS queries.py:3044 -- subquery auto-referente Instance=Instance sempre true, usa MAX(Collection_Time) GLOBAL em vez de per-instance; particoes desaparecem silenciosamente se coleccao do servidor for mais antiga que o maximo global. FALSO-OK FRONTEND (padrao FIND-102 noutros sitios, .json() sem res.ok): TDE tab portal:17570 (PIOR -- 500 mostra "TDE nao activo / 0 dbs encriptadas", surface compliance); familia disk-space 21356/21428/21547/21599/21652 (overflow preditivo, disk warning/critical, filegroups -- 0 alertas num erro); disk-files 44072 ("Nenhum arquivo encontrado"); gaps-statistics 19337 (painel stats omitido). Parciais: server-offline history 24642-24649, AG events 27143, backup patterns 18285, LIVE channels 44351. ~45 call-sites tratam erro correctamente.
- **Recommendation:** Wave W+1: (a) fix DEADLOCKS_ANALYSIS (remover UNION ALL orfao, ORDER BY para dentro dos branches); (b) fix BACKUP_HISTORY_ANALYSIS (inline da condicao LOG_BLOCKED_BY no CASE Recommendation); (c) res.ok checks nos 8 falso-OK comecando por TDE; (d) avaliar SERVER_PARTITIONS correlacao per-instance. Institucionalizar: nunca .json() sem res.ok; estado vazio requer distincao de estado de erro.
  APLICADO 2026-06-12 Wave W+1 (validado por sql-deep-reviewer): (a)+(b)+(c 8/8)+(d com upgrade -- janela 10min ancorada no MAX per-instance + ROW_NUMBER dedupe, porque o collector V1 insere row-a-row com GETDATE() por statement, equality estrita devolveria 1 particao). Restam parciais leves (server-offline history 24642, AG events 27143, patterns 18285, LIVE channels 44351) + follow-ups: XE timestamp UTC vs GETDATE() local no filtro 24h deadlocks; collector V1 estampar 1 Collection_Time por batch (handoff watcherdb-v1-intel-specialist, infra partilhada).
- **Status:** mostly-fixed (P1 shipped Wave W+1, pending validation; parciais leves + follow-ups V1 open)
- **Created:** 2026-06-12
- **Updated:** 2026-06-12

---

## FIND-20260612-104 -- Tier creep pre-existente: 6 routes predictive-alerts Pro-only activos em watcherdb_main.py

- **Severity:** P1
- **Category:** tiering
- **Owner specialist:** v33-feature-matrix-checker
- **Evidence:** Detectado pelo tier check do Wave W (PASS para o changeset; este e gap anterior). watcherdb_main.py:5238-5681 -- @app.get /api/monitoring/space/server/{server_id}/predictive-alerts + debug + ping + test-simple + test-query + debug-v2 (6 endpoints) activos com import dinamico de PredictiveAlertsEngine (modules/monitoring/predictive_alerts_debug.py). O cleanup FIND-014-B (commit 5441c80) comentou os decorators em watcherdb_intelligence.py mas estes routes ficaram. Predictive alerts e Pro-only per docs/FEATURE_MATRIX.md:114-116.
- **Recommendation:** Comentar/remover os 6 routes em watcherdb_main.py a semelhanca do FIND-014-B em watcherdb_intelligence.py. Verificar que o portal Std nao chama predictive-alerts (modal preditivo overflow em portal:21356 chama /api/monitoring/space/server/ -- confirmar se e o endpoint base Std ou o predictive Pro).
  APLICADO 2026-06-12: 6 decorators comentados estilo FIND-014-B (funcoes preservadas para paridade V6+ Pro). Verificado pre-aplicacao: portal so chama predictive-alerts em loadPredictiveAlerts/renderPredictiveAlertsPanel que ja tem early-return FIND-014-B (portal:26266-26270, 26301-26304) -- dead code, sem caller real. Modal preditivo overflow (21356) usa o endpoint BASE /api/monitoring/space/server (Std), nao o predictive.
- **Status:** fixed (pending validation pos-restart)
- **Created:** 2026-06-12
- **Updated:** 2026-06-12

[WAIVER aplicado 2026-06-12 | regra: AI nao escreve ficheiros sem aprovacao manual | scope: FIND-103 + FIND-104 append]

---

## FIND-20260729-101 -- Verde falso: card reporta 100% disponibilidade sobre recolha truncada (44 de 107 instancias)

- **Severity:** P0
- **Category:** coverage
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** Incidente DNS 2026-07-29. Portal as 11:22 mostrou `44 INSTANCIAS / 100% DISPONIBILIDADE / 0 Offline` quando o dataset activo continha 44 das 107 instancias (baseline das 10:05 no mesmo dia: 107 instancias, 51 offline, 52.3%). **Zero indicacao de recolha incompleta** -- as 63 instancias em falta nao aparecem como offline nem como nao-medidas: desaparecem da conta e a percentagem e recalculada sobre o que sobrou. Causa a montante: collectors falharam em cascata durante degradacao do `Dnscache` local e o conjunto parcial ficou como dataset activo.
- **Recommendation:** Card de disponibilidade tem de exibir denominador e distinguir "medido e OK" de "nao medido", reutilizando o padrao `MEASURABLE`/`NOT_MEASURABLE` ja validado no KPI Integridade. Registar em `WAVE_COBERTURA_SPEC_2026-07-28.md` como **5a instancia observada** -- e a mais grave das cinco por ser a unica silenciosa (o falso OFFLINE grita; o verde falso nao). Cross-ref: [[FIND-20260729-102]].
- **Status:** open
- **Created:** 2026-07-29
- **Updated:** 2026-07-29

---

## FIND-20260729-102 -- Filtro anti-falso-positivo depende do pipeline que acabou de falhar (fail-open)

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** `services/collector_service/collectors/collect_server_ping.py:86-95` e `:706-759`. O supressor de falsos positivos de porta dinamica cruza com `KPI_MSSQL_INST_AVAILABILITY_STG`; se a instancia tem registo recente, o falhanco no TCP 1433 e ignorado (`servers.json` tem `port=1433` placeholder em todas as instancias). Apos qualquer interrupcao esses dados estao velhos, o filtro **abre** e produz uma salva de falsos `SQL_DOWN`. Medido a 2026-07-29 -- 13:34:49 `[server_ping_PRD] Done: 42 online, 38 sql_down, 0 sql_down_skipped` com sufixo `(no recent availability)` em cada linha; 13:37:51 recuperado `0 sql_down, 38 sql_resolved, 38 sql_down_skipped`. Janela de falso positivo ~3 min por incidente.
- **Recommendation:** Fail-safe em vez de fail-open -- sem availability recente, classificar como `UNKNOWN`/`NOT_MEASURABLE` em vez de `SQL_DOWN` (o produto ja tem o vocabulario). Correccao estrutural preferivel: consumir a porta aprendida da Wave A (`WDB_INSTANCE_TCP_PORT`) em vez do placeholder 1433, o que elimina a dependencia em vez de a mitigar -- alinha com o item 3 da Prioridade 2 do prompt pos-Wave-A.
- **Status:** open
- **Created:** 2026-07-29
- **Updated:** 2026-07-29

---

## FIND-20260729-103 -- Wave A `ip_rescue` nao cobre `OATXP01`: SQL_DOWN reportado com 1433 aberto

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** 2026-07-29 13:54:53 e 13:59:57 -- `[SQL_DOWN] OATXP01 - host up, TCP 1433 fail: TCP timeout (15.0s) (no recent availability)`. Teste manual da **mesma maquina, no mesmo periodo**: `172.17.192.149` ICMP Success 20ms, **TCP 1433 ABERTO**, UDP 1434 sem resposta (instancia default sem SQL Browser -- normal e esperado). Nao pertence a classe dynamic-port: essa foi integralmente apanhada no mesmo ciclo (41 `sql_down_skipped`). O caminho `ip_rescued` da Wave A salvou **41 de 42** instancias PRD e falhou apenas nesta. Suspeita por confirmar: `OATXP01` nao tem sufixo `_I01` como as restantes e o casamento em `collect_server_ping.py:587-591` (`s.get("host") != host`) pode nao resolver para ids de instancia default.
- **Recommendation:** Confirmar o casamento de id no caminho de rescue para instancias default (sem sufixo de instancia) e cobrir com teste de regressao. Nota: a Wave A esta a funcionar -- isto e uma lacuna de cobertura da feature, nao uma regressao.
- **Status:** open
- **Created:** 2026-07-29
- **Updated:** 2026-07-29

---

## FIND-20260729-104 -- Contraste ilegivel no tema claro em 3 componentes (WCAG 2.1 AA)

- **Severity:** P1
- **Category:** accessibility
- **Owner specialist:** watcherdb-frontend-specialist
- **Evidence:** Screenshots do owner, 2026-07-29, tema **claro** (tema escuro nao afectado). (a) Aba **Disk**, painel "Alertas Inteligentes" em `SQLIDSPRD03\I01`: titulo e corpo dos 4 alertas em ambar sobre fundo ambar e vermelho sobre fundo vermelho -- texto praticamente invisivel, incluindo o alerta CRITICO. (b) Aba **Security**: labels dos cards de topo (`Passed`, `Failed`, `Warnings`, `Critical`, `High`) em tom claro sobre fundo claro -- os numeros leem-se, os labels nao. (c) Caixa **"Recomendacao:"** dentro dos checks de Security: fundo navy escuro com texto escuro. Ironia relevante: (b) e (c) estao no modulo Security, que a `WAVE_COBERTURA_SPEC` elege como **referencia de qualidade** do produto.
- **Evidence (caso d, adicionado 2026-07-29):** Modal `DB Disk File System - Critico`, painel expansivel **"Detalhe completo do registo"** -- fundo cinzento-escuro com texto esbatido por cima (labels `Drive Count`, `Total MB`, `Free MB`, `Min Percent Free`...) no tema claro. **Quarto componente com o mesmo defeito no mesmo dia** (Disk alertas, Security cards, Security caixa Recomendacao, e agora este modal): confirma que o padrao e sistemico, nao pontual -- a correccao deve ser uma varredura, nao 4 remendos.
- **Recommendation:** Auditar os tokens de cor destes componentes. Requisito: 4.5:1 para texto normal, 3:1 para texto grande. Varrer os 3 temas (Claro / Escuro / Alto Contraste) e nao so o par que originou o report.
  **CAUSA-RAIZ CONFIRMADA 2026-07-29** (caso b, cards Security) -- `templates/watcherdb_portal.html:19049-19070`: os labels tem cor fixa em hex pastel **inline** (`#6ee7b7` passed, `#fca5a5` failed, `#fcd34d` warnings, `#fda4af` critical, `#fdba74` high) sobre fundos `linear-gradient` translucidos a ~20% de alpha (`#10b98133`, `#dc262633`...). Pastel foi escolhido para fundo escuro; no tema claro o fundo resolve para quase-branco e o label desaparece. **Sendo estilo inline, nenhuma variavel de tema o consegue sobrepor** -- a correccao obriga a mexer neste markup, nao chega adicionar override CSS. Verificar se os casos (a) Alertas Inteligentes do Disk e (c) caixa "Recomendacao" partilham o mesmo padrao de hex inline.
- **Status:** open
- **Created:** 2026-07-29
- **Updated:** 2026-07-29

---

## FIND-20260729-105 -- Aba Disk engole falhas de sub-fetch e apresenta zeros como "sem problemas"

- **Severity:** P1
- **Category:** coverage
- **Owner specialist:** watcherdb-frontend-specialist
- **Evidence:** `templates/watcherdb_portal.html:9332-9362` -- `loadDiskAnalysisForTab` faz tres sub-fetches (I/O, log space, historico de disco) e cada um tem o comentario literal **`pode falhar silenciosamente`**, com `try/catch` que so escreve `debugLog` e segue. Consequencia em `renderDiskAnalysis:10175-10176`: `const ioCriticals = window.diskIOData.filter(d => d.Severity === 'CRITICAL').length` -- com `diskIOData = []` por falha de fetch, o resultado e **0**, indistinguivel de "zero problemas de I/O medidos". O mesmo vale para `logSpaceData` (a seccao simplesmente nao e renderizada, sem aviso) e `historyData` (graficos de tendencia desaparecem). O utilizador ve uma aba Disk aparentemente completa e saudavel.
- **Recommendation:** Distinguir `[]` de "nao obtido". Minimo: flag por sub-fetch (`ioOk`, `logSpaceOk`, `historyOk`) e, quando falso, render de estado explicito em vez de zero/omissao -- reutilizar o padrao ja implementado no modulo **Services** (`portal:31672-31689`: `N/A`, `-/-`, mensagem e causas provaveis), que e a referencia interna para este caso. Detectado durante o passo 0 da Wave Cobertura; e a 3a instancia de producao do mesmo padrao no mesmo dia, com [[FIND-20260729-101]] (dashboard 100% sobre 41% do parque) e [[FIND-20260729-102]] (filtro anti-FP fail-open). Motivou a inversao de eixo registada em `docs/context/WAVE_COBERTURA_SPEC_2026-07-28.md` §4.4.
- **Status:** open
- **Created:** 2026-07-29
- **Updated:** 2026-07-29

---

## FIND-20260729-106 -- `Avg Livre` e media nao ponderada e contradiz o veredicto no mesmo card

- **Severity:** P1
- **Category:** ux
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** Modal `DB Disk File System - Critico`, instancia `SQLHDSPRD405_I01` (2026-07-29). O campo e `AVG(Percent_Free)` -- media aritmetica **simples** das percentagens por drive, sem ponderacao pelo tamanho do volume. Origem confirmada em `WATCHERDB INTELLIGENCE V1/database/QUERIES_KPIS_DISPONIVEIS.sql:635` e `api/routers/intelligence_kpis.py:1153`. Numeros reais do registo: Drive Count 3, Total 2.841.545,88 MB, Free 631.426,42 MB, Min_Percent_Free 7,35, Avg_Percent_Free 51,206666. **Free/Total = 22,2%** -- coerente com o proprio card (`Livre: 616,6 GB / 2774,9 GB` = 22,2%) e **em contradiccao directa com o `Avg Livre: 51,2%` exibido na mesma linha**. A media simples da o mesmo peso a um volume de 2 TB e a um de 100 GB, sobrestimando a folga em mais do dobro. Efeito observado: o owner questionou a classificacao CRITICAL ("muito espaco livre para ser critico") -- o veredicto estava certo (dispara em Min_Percent_Free 7,3% < Crit 10%), mas os dois numeros em destaque no card sugerem folga confortavel. **O card induz o utilizador a duvidar do proprio alerta.**
- **Recommendation:** **Remover** o `Avg Livre` -- nao e resgatavel: ponderado passaria a 22,2%, identico ao `Livre: X / Y GB` ja exibido (redundante); nao ponderado e enganador. No lugar, mostrar **qual** e a drive critica e quanto lhe resta (ex: `F:\ 147 GB livres de 2,0 TB, 7,3%`), aplicando a regra do owner de 2026-07-27 de nomes accionaveis em vez de numeros soltos. Fundamento tecnico a registar na doc: espaco livre **nao e fungivel entre volumes** -- o SQL Server nao usa folga da drive G para um ficheiro que vive na drive F, e por isso o agregado nunca deve competir em destaque com o minimo. **Propagacao V6:** o mesmo `AVG(Percent_Free)` existe em `WATCHERDB_V6/api/routers/intelligence_kpis.py:2883` -- o fix tem de ir aos dois.
- **Status:** open
- **Created:** 2026-07-29
- **Updated:** 2026-07-29

---

## FIND-20260729-107 -- Doc do KPI Backups desactualizada pela separacao de 28/07, e `is_damaged` sem ambito declarado

- **Severity:** P1
- **Category:** docs
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** A 2026-07-28 o `is_damaged` foi separado do `no_checksum` no card (`portal:33986-33994`), mas a documentacao nao acompanhou. **Tres sitios errados hoje:** (1) `portal:38846` -- descricao de "Backups sem Checksum" continua a dizer `"...sem WITH CHECKSUM nos ultimos 7 dias, ou com backupset marcado como danificado"`; (2) `portal:38857` -- condicao de alerta repete `"sem checksum ou backupset danificado"`; (3) `portal:38661` -- descricao de "Falhas de Backup" remete `"nem backups sem checksum ou danificados (ver Backups sem Checksum)"`, ponteiro que deixou de ser valido. **E nao existe entrada de menu para "Backup danificado"** -- o menu tem 5 entradas de backup e a linha nova nao esta em nenhuma. Nao e so uma lacuna: sao duas descricoes que afirmam algo **falso** e um ponteiro partido -- pior do que ausencia, porque um DBA decide com confianca sobre informacao errada. **Segundo defeito, semantico:** `backupset.is_damaged=1` exige `BACKUP WITH CHECKSUM` (deteccao) **e** `WITH CONTINUE_AFTER_ERROR` (para nao falhar) -- duas flags de intencao oposta. Sem CHECKSUM o backup nao valida paginas e a corrupcao passa em silencio. Logo `is_damaged=0` **nao significa backups sao**: significa que nada foi apanhado onde a deteccao se aplica, e com 1153 bases sem checksum a maioria do parque esta fora de alcance. Bola verde sobre populacao nao medida = mesmo padrao de [[FIND-20260729-101]].
- **Recommendation:** Decidido com o owner 2026-07-29, em tres partes. (1) **Tab Backups**: par completo por servidor -- `N bases sem checksum, das quais X com backupset danificado`. E' onde a populacao vive e onde o DBA age; fecha tambem o item 4 da Prioridade 2 do prompt pos-Wave-A. (2) **Card da frota**: linha "Backup danificado" renderiza **so quando > 0** (`portal:33990`, trocar `_advRow(...)` por `(cond ? _advRow(...) : '')`). Zero nao vira verde -- desaparece. Segue o mesmo principio ja aplicado ao drill em `portal:33989` (`"preferivel nao ter clique a ter um clique que mostra outra coisa"`). (3) **Docs**: corrigir os 3 sitios e criar entrada propria para "Backup danificado", explicitando a pre-condicao do CHECKSUM. **Criterio geral extraido** (aplicar no Lote 1 da auditoria): esconder o zero quando a medicao so cobre um subconjunto; manter o zero quando a populacao foi toda medida (ex: "Full falhou: 0" e informacao genuina). **Causa da lacuna de auditoria:** o audit de 2026-07-28 deu `29/29 documentados, 0 orfaos` porque comparou **KPIs registados** com o menu; "Backup danificado" e uma **linha de card**, fora desse universo por construccao. Inferencia por confirmar no Lote 1.
- **Status:** open
- **Created:** 2026-07-29
- **Updated:** 2026-07-29

---

## FIND-20260729-108 -- Um numero visivel pode existir sem identidade de KPI, e nesse caso perde doc, drill, ajuda e link de tab de uma so vez

- **Severity:** P1
- **Category:** coverage
- **Owner specialist:** watcherdb-frontend-specialist
- **Evidence:** Lote 1 da auditoria de documentacao, 2026-07-29. **Tudo o que um numero do dashboard tem depende de ele ser um KPI registado em `KPI_METADATA`** (`portal:32156`, 34 ids). **CORRIGIDO 2026-07-29 (erro do primeiro registo):** sao **cinco** mapas independentes, nao quatro, e a documentacao **nao** vive no `KPI_METADATA` -- e registo proprio. Todos chaveados pelo mesmo id e mantidos a mao: (1) `KPI_METADATA` (`portal:32156`) -- `key`/`title`/`subtitle`/`getValue`, alimenta *tiles* e modais; (2) **registo de documentacao** (`portal:38657+`) -- `category`/`description`/`howItWorks`/`thresholds`/`tables`/`i18n`, alimenta o menu "Documentacao dos KPIs"; (3) mapa de texto de ajuda `PORQUE IMPORTA` / `O QUE FAZER` (`portal:~34804`), usado pelo `showCardHelp` (71 call-sites); (4) mapa de destino de tab (`portal:~34782`, ex. `'backup-jobs-disabled': 'tab:backup'`); (5) chave de drill, 5.º argumento do `_advRow` (`portal:33819` -> `showProblematicInstances`). O erro reforca a propria finding: **cinco registos com ids sobrepostos e zero verificacao entre eles sao dificeis de manter em cabeca, e foi por isso que a doc do `no_checksum` ficou a mentir durante um dia inteiro.** **`_advRow` nao tem argumento de documentacao nenhum** -- a correspondencia entre as ~32 linhas de card e as 34 entradas de doc e implicita, por nome, e nada a verifica. **Caso confirmado:** `Backup danificado` (`portal:33990`) nao existe em `KPI_METADATA` -- nao e um KPI, e uma linha de card. Resultado: sem documentacao, sem drill (5.º arg vazio), sem ajuda, sem destino de tab. Nao ha nada no codigo que sinalize a ausencia. **Confirma a causa da lacuna de auditoria:** o audit de 2026-07-28 deu `29/29 documentados, 0 orfaos` porque iterou `KPI_METADATA`; uma linha sem identidade de KPI e invisivel a esse metodo por construccao -- a auditoria nao podia falhar, e tambem nao podia encontrar nada.
- **Nota de metodo (erro apanhado e corrigido durante a propria auditoria):** um primeiro cruzamento sugeria ~8 "documentacoes sem numero" (`backup-jobs-disabled`, `jobs-failed`, `jobs-collisions`, `transaction-logs-warning`, 3x `db-availability-*`). **Falso** -- essas entradas renderizam como *tiles* de KPI, nao como linhas de `_advRow`; superficie diferente, nao orfas. Igualmente, um cruzamento das chaves de drill contra os ids de doc produzia ~10 falsos positivos (`always-on` vs `always-on-unhealthy`, `tempdb-status-critical` vs `tempdb-critical`, `integrity-p1/p3/p4` vs `integrity`) -- espacos de chaves distintos, comparacao invalida. Registado porque a proxima auditoria vai tropecar nos mesmos dois sitios.
- **Recommendation:** A correccao duravel nao e tapar os orfaos de hoje -- sem acoplamento, voltam a aparecer na proxima alteracao. Duas vias, preferir a primeira: (1) **`_advRow` passa a exigir chave de KPI/documentacao** e falha de forma visivel quando nao resolve (ex. render de badge de aviso em DEV, ou consola). Barato -- um argumento e uma verificacao -- e converte um problema recorrente em algo que o codigo impede. (2) Em alternativa, exigir que toda a linha visivel tenha entrada em `KPI_METADATA`, o que daria a `is_damaged` doc, drill, ajuda e tab de uma vez. **Orfaos reais a tratar entretanto:** `Backup danificado` (ver [[FIND-20260729-107]]), `Servicos em baixo` (drill `sql-services-down` sem entrada correspondente -- confirmar), `Latencia aviso` (abre a documentacao do *critico*, `disk-latency-critical`; nao existe entrada de warning). **Colapsos N:1 a avaliar:** 3 linhas de backup (`Full`/`Diff`/`Outros falhou`) partilham `backup-failed`; 4 linhas de Integridade (P1/P3/P4/nao-mensuravel) partilham `integrity`.
- **Achado colateral util:** a Integridade ja distingue medicao de ausencia **ao nivel da linha** -- `igNA ? 'N/D' : valor` (`portal:34027-34033`). Terceira referencia interna do produto, com o modulo Services (`portal:31672-31689`) e o KPI de Integridade. A Wave Cobertura tem tres modelos internos e nao precisa de inventar nenhum. Igualmente, o padrao `cond ? _advRow(...) : ''` (linha so quando > 0) **ja existe** em `portal:33983` e `portal:34033` -- e precedente estabelecido, nao tecnica nova.
- **Status:** open
- **Created:** 2026-07-29
- **Updated:** 2026-07-29

[WAIVER aplicado 2026-07-29 14:20 | regra: escrita de AI restrita a docs/context/ e .claude/ | scope: append de FIND-20260729-101..108 em findings-inbox.md (raiz), com GO explicito do owner ("faca as 3 coisas" + "GO" x5 + "siga a sua recomendacao" x2)]

---

## FIND-20260729-109 -- KPIs irmaos do card Backups contam unidades diferentes

- **Severity:** P1
- **Category:** ux
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** `Diff falhou: 7` no card correspondia a **1 job, 2 instancias, 10 noites** -- nao a 7 bases de dados. O KPI `falhou` conta **eventos**; o `sem checksum` conta **entidades deduplicadas** por (Instancia, Base) e diz isso na propria documentacao. Dois numeros lado a lado, unidades diferentes, nada que o indique. Agravado por `collect_server_ping.py:1450` (*"Conservativo: Database NULL ou type OTHER nao filtram"*): as 7 linhas tinham `Database` vazio, logo nunca podem ser marcadas como recuperadas e acumulam ate a retencao de 14 dias da STG. **O numero cresce com a duracao da avaria, nao com a sua amplitude** -- indistinguivel de 7 bases partidas.
- **Recommendation:** deduplicar por (Instancia, Job) ou declarar a unidade no card. Para linhas sem `Database`, contar a ocorrencia uma vez e mostrar a duracao (*"falha desde 17/07"*) em vez de repetir a contagem por noite.
- **Status:** open
- **Created:** 2026-07-30
- **Updated:** 2026-07-30

---

## FIND-20260729-110 -- KPIs de LOG ignoram o modelo de recuperacao

- **Severity:** P1
- **Category:** coverage
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** os limiares de atraso de LOG sao warning 1h / critical 2h (`api/routers/intelligence/helpers.py:1308`). Uma base em SIMPLE **nao pode** ter backup de log (Msg 4208) e vai a CRITICO em duas horas. Zero referencias a modelo de recuperacao em toda a arvore `api/routers/intelligence/`. O collector **ja recolhe** o dado: `recovery_model_desc AS RecoveryModel` em `collect_kpi.py:315`. **Caso de producao imediato:** a `WatcherDB_Intelligence` passou a SIMPLE a 2026-07-29 por decisao do owner; tinha 477 backups de log em 20 dias.
- **Recommendation:** excluir bases em SIMPLE dos KPIs de LOG, ou classifica-las como `NOT_MEASURABLE`. Para SIMPLE, "sem backup de log" nao e atraso: e **nao aplicavel**. O dado ja existe, so nao e consultado.
- **Status:** open
- **Created:** 2026-07-30
- **Updated:** 2026-07-30

---

## FIND-20260729-111 -- `Full falhou` e cego a backups externos e apresenta o vazio como saude

- **Severity:** P0
- **Category:** coverage
- **Owner specialist:** watcherdb-customer-success-persona
- **Evidence:** o KPI conta falhas de jobs do SQL Agent. A frota faz backup por **TSM/TDP**, e parte da cadeia e agendada do lado do TSM -- nao passa pelo Agent. Onde passa (`CmdExec`), o Agent so ve o exit code do `cmd.exe`, nao o resultado do TSM. Resultado medido a 2026-07-30: `SQLHDSPRD405`, `SQLHDSPRD201` e `SQLHDSPRD408` (**26 bases**) sem full **nem** diferencial ha mais de um mes, e o card a mostrar **`Full falhou: 0`**. Tecnicamente correcto -- nao ha job a falhar -- e operacionalmente a tranquilizar. O sinal existe no `Backups em Atraso: 623`, diluido e com o mesmo peso visual que o zero verde. **Assimetria a explorar:** `msdb.dbo.backupset` regista qualquer backup independentemente do motor; `sysjobhistory` so regista o que passa pelo Agent -- foi pelo `backupset` que se descobriram os 38 dias, nunca pelo historico de jobs.
- **Recommendation:** hierarquizar. Primario e universal: tempo desde o ultimo backup bem-sucedido (`backupset`). Secundario e dependente de regime: falhas de jobs, com o regime declarado. Deteccao **por instancia** -- a frota e mista (ha servidores com os jobs `_LOCAL` nativos activos e o TSM desligado). O `_source_label` do `DatabaseBackupPatternAnalysis` ja classifica em sysjobs / historico R+8 / **inferido** e despeja-o num `logger.info`: e o detector de regime, ja construido, que nunca chega a API. **Decisao do owner 2026-07-30:** o WatcherDB **adapta a monitorizacao** ao regime do cliente; **nao** passa a fazer backups.
- **Status:** open
- **Created:** 2026-07-30
- **Updated:** 2026-07-30

---

## FIND-20260729-112 -- `HasSchedule` verificava existencia, nao actividade

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** `collect_agent_jobs.py:91` fazia `EXISTS(sysjobschedules)` sem verificar `sysschedules.enabled`. `scripts/collectors/collect_backup_jobs_disabled.py:87` filtrava so por `sj.enabled = 0`. Um job activo com todos os agendamentos desligados passava entre **os tres** KPIs de backup em simultaneo: nao conta como desactivado (`enabled=1`), nao conta como falha (nunca executa, logo nao ha execucoes para falhar), e `HasSchedule` dava 1 porque a linha do agendamento existe. Caso real: `DBA_FULL_BACKUP` em `SQLMDMQLT03_I01`, `DBA_FULL_BACKUP_SCHEDULE` com `enabled=0`, semanal ao Domingo -- sem correr desde 21/06 e invisivel durante 5 semanas.
- **Recommendation:** aplicado. Ambas as queries passam a exigir `sysschedules.enabled = 1`. Validado no caso real antes/depois (`HasSchedule` ANTES=1, DEPOIS=0) e por `ast.parse` nos dois ficheiros.
- **Nota de processo:** mudanca em infra partilhada V1 **sem gate** do `watcherdb-v1-intel-specialist`, que tem direito de veto. Pedir parecer a posteriori -- nem que seja para confirmar que nenhum consumidor do `HasSchedule` depende da semantica antiga (verificado em V3.3; **por verificar no V6**).
- **Status:** fixed (commit `7e9c0fd`), pendente de validacao pos-ciclo
- **Created:** 2026-07-30
- **Updated:** 2026-07-30

---

## FIND-20260729-113 -- O KPI de jobs desactivados conta o par intencional TSM/LOCAL como problema

- **Severity:** P1
- **Category:** ux
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** cada instancia tem **dois conjuntos** de jobs de backup -- TSM e `_LOCAL` (mais variantes tipo `_TAP_ORS`) -- e um deles esta sempre desligado, de proposito. Confirmado em dois servidores com a configuracao **invertida** entre si: em `SQLMDMQLT03_I01` os TSM estao activos e os `_LOCAL` desligados; noutra instancia e ao contrario. Apos o fix `7e9c0fd`, o KPI passa a marcar **6 jobs em `SQLMDMQLT03_I01`: 1 problema real e 5 de ruido estrutural (83%)**. O ruido e **anterior** ao fix; o fix acrescenta o sinal certo a um sitio onde ele fica enterrado.
- **Recommendation:** criterio sem configuracao -- **um job desactivado cujo irmao de mesmo nome-base esta activo e alternativa intencional, nao esquecimento** (`DBA_FULL_BACKUP` vs `DBA_FULL_BACKUP_LOCAL`). Filtrar o par antes de contar. Mesma familia do `sem checksum` com 1153 a dominar o card, ja removido a 28/07. **Distinguir as duas causas na modal** (job desactivado vs sem agendamento) exige coluna nova na `KPI_MSSQL_BACKUP_JOBS_DISABLED_STG` -- esquema partilhado, com canonical e as 5 superficies atras; lote proprio.
- **Status:** open
- **Created:** 2026-07-30
- **Updated:** 2026-07-30

[WAIVER aplicado 2026-07-30 | regra: escrita de AI restrita a docs/context/ e .claude/ | scope: append de FIND-20260729-109..113 em findings-inbox.md (raiz), com GO explicito do owner ("siga a sua recomendacao")]

---

## FIND-20260803-101 -- TempDB KPI a zero: coluna fantasma no backend + FILEPROPERTY fora de contexto no colector

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist (colector) + watcherdb-v33-specialist (backend)
- **Evidence:** dupla falha independente, cada uma suficiente para o zero permanente. (1) V3.3 `api/routers/intelligence/helpers.py` e `intelligence_kpis.py` liam `Usage_Percent` -- coluna que NUNCA existiu na `KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW` (nome real: `Percent_Used`); todas as linhas eram ignoradas, contador ficava 0 mesmo com tempdb a 100%. (2) V1 `scripts/collectors/collect_tempdb_usage.py` usava `FILEPROPERTY(name,'SpaceUsed')` fora do contexto do tempdb -> NULL -> `fillna(0)`: `Used_MB`/`Free_MB`/`Percent_Used` = 0.00 nas 63 instancias (validado na BD: BLUE/GREEN PRD/QA/TST todos max_pct=0.00, dados frescos). Decomposicao (`sys.dm_db_file_space_usage` sem prefixo) media a DB corrente, nao o tempdb.
- **Recommendation:** aplicado. Backend le `Percent_Used` (fallback legado) + mapeia `Total_Size_MB`/`Free_MB` -> `*_gb`; colector reescrito com `tempdb.sys.dm_db_file_space_usage` e Used = Total - unallocated (compativel SQL 2005+). Validado por dry-run TST: valores reais (ex.: SQLMDMDEV05 39.26%, SQLHDSTST023 21.09%). Sem DDL -- canonical intacto.
- **Nota de processo:** mudanca em colector V1 partilhado; parecer do `watcherdb-v1-intel-specialist` a posteriori (mesma nota do FIND-20260729-112).
- **Status:** fixed (commit nesta sessao), pendente de validacao pos-ciclo do colector
- **Created:** 2026-08-03
- **Updated:** 2026-08-03

---

## FIND-20260803-102 -- Disk latency estruturalmente a zero: amostra unica de contadores WMI formatados

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** `watcherdb_intelligence/os_performance.py:512` (`_collect_disk_wmi_sync`) faz UMA query a `Win32_PerfFormattedData_PerfDisk_LogicalDisk`; contadores Avg/rate exigem duas amostras -- numa unica, devolvem 0. Resultado na BD: `Avg_Read/Write_Latency_MS` = 0.00 nas 517 linhas / 76 hosts do `KPI_OS_DISK_PERF_STG` (dado fresco de hoje). O card "Saude do Disco -> Latencia critica/aviso" nunca dispara com carga real; os spikes no HIST (4000-58000 ms em Mai-Jul) sao artefactos da mesma amostragem, nao latencia real. CPU/memoria do mesmo modulo usam o mesmo padrao (rever no mesmo lote).
- **Recommendation:** duas amostras raw (`Win32_PerfRawData_PerfDisk_LogicalDisk`) com formulas PERF_AVERAGE_TIMER (N2-N1)/F/(B2-B1), ou `Get-Counter` remoto com SampleInterval. Alternativa mais barata: latencia por drive via DMV SQL `sys.dm_io_virtual_file_stats` (cobre so ficheiros SQL, mas e o que interessa ao DBA). Decisao de design + gate do specialist V1 antes de implementar.
- **Resolucao:** gate `watcherdb-v1-intel-specialist` executado (2026-08-03): GO Opcao A (2 amostras raw, 1s) e VETO a DMV como substituto 1:1 (deixaria NULL as colunas OS-only usadas pela correlacao memoria-paging-disco em V3.3+V6). Aplicado em `os_performance.py` `_collect_disk_wmi_sync` (commit `baa4cb3`), zero DDL, contract intacto. Dry-run TST: latencias 0.96-3.42ms, IOPS/disk time/queue reais. Condicao V6 pendente: validar `data/eval/golden_self_knowledge_v1.jsonl` Q037 (se codifica 0.00 como esperado, corrigir fixture) — esta' no lote de propagacao.
- **Status:** fixed (commit `baa4cb3`), pendente de validacao pos-ciclo do WatcherDBCollector
- **Created:** 2026-08-03
- **Updated:** 2026-08-03

---

## FIND-20260803-103 -- wmi.WMI(computer=host) sem timeout nas 3 coletas OS

- **Severity:** P2
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** `watcherdb_intelligence/os_performance.py:358,435,507` — as chamadas WMI de CPU/Memory/Disk nao tem timeout explicito; um host pendurado segura a thread do pool ate ao timeout DCOM por omissao (longo). O fix do FIND-102 duplica a exposicao por host (2 amostras). Achado proactivo do gate de 2026-08-03.
- **Recommendation:** timeout explicito na ligacao WMI (ou watchdog na thread) num lote proprio.
- **Status:** open
- **Created:** 2026-08-03
- **Updated:** 2026-08-03

---

## FIND-20260803-104 -- KPI_MSSQL_FILE_IO_STG coletada ha meses e sem nenhum consumidor

- **Severity:** P2
- **Category:** opportunity
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** `scripts/collectors/collect_file_io.py` (V1) coleta `sys.dm_io_virtual_file_stats` + `master_files` de 5 em 5 min, BLUE/GREEN, grant ja dado — e zero hits em V3.3 `api/`, `services/`, `templates/`. Latencia por FICHEIRO SQL ja existe na BD, gratis. PoC de 2 samples com delta validado a 2026-08-03 (drive L: 4.01ms write em janela de 10s). Achado proactivo do gate FIND-102.
- **Recommendation:** wave futura: rollup por drive como sinal complementar "ficheiros SQL" ao lado do sinal OS (nao substituto — cumulativa desde restart dilui picos). Candidato a drill do card Saude do Disco.
- **Status:** open
- **Created:** 2026-08-03
- **Updated:** 2026-08-03

---

## FIND-20260803-105 -- Mirroring KPI a zero estrutural: DET_VIEW com binding error desde a Wave C

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** `KPI_MSSQL_MIRRORING_STATUS_DET_VIEW` seleciona `Env` da `KPI_MSSQL_MIRRORING_STATUS_ACTIVE`, mas a _ACTIVE regenerada na Wave C (31/07, commit `9a39aaf`) faz `SELECT d.*` das fisicas por ambiente, que NAO tem coluna Env -> binding error 4413 em qualquer SELECT. O backend engole (`raise_on_error=False`) e "Mirroring nao saudavel" mostra 0 desde 31/07, com mirroring real na frota. Descoberto na auditoria rotulo-vs-unidade de 03/08. Varredura completa as 146 views: e' a UNICA com binding partido (14 `vw_*`/`v_*` dao erro 208 = grant em falta para sql_monitoring, nao binding — observacao, nao bug).
- **Recommendation:** aplicado no canonical (`SECTION16_MIRRORING_STATUS.sql` 16.5 reescrita: Env via JOIN `KPI_MSSQL_INST_ENVS`, semantica da view viva preservada) + AVISO na 16.6 (variante DB_AVAILABILITY desatualizada, nao executar sem reconciliar). DDL `CREATE OR ALTER` entregue ao owner em bloco (execucao manual SSMS). Follow-up: sweep pos-Wave-C devia incluir teste de binding a todas as views, nao so as _ACTIVE.
- **Status:** fixed (DDL aplicado pelo owner em SSMS 2026-08-03 ~15h; validado: view compila, 110 DBs espelhadas todas SYNCHRONIZED, 0 issues legitimo)
- **Created:** 2026-08-03
- **Updated:** 2026-08-03

---

## FIND-20260803-106 -- Unidades e frescura dos KPIs: fase 2 (decisoes de produto pendentes)

- **Severity:** P2
- **Category:** ux
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** auditoria 03/08 rotulo-vs-unidade. Fase 1 aplicada (rotulos honestos + count_by_env dos deadlocks corrigido). Pendentes que exigem decisao do owner: (a) trocar valor de instancias->itens em "Instancias c/ discos criticos" (drives via critical_items_total, ja existe) e "Instancias c/ t-log critico" (databases via critical_items_total) — mudaria numeros visiveis e divergiria do tile Por Categoria, como ja acontece nos filegroups; (b) processos: sem guarda de frescura (colector parado congela o numero em silencio) e amostragem snapshot 5min (picos entre ciclos invisiveis); (c) blocked_users count global = DISTINCT users mas count_by_env conta linhas instancia-user; (d) service_status tem services_down_total (servicos) disponivel mas sem *_by_env.
- **Status:** open
- **Created:** 2026-08-03
- **Updated:** 2026-08-03

---

## FIND-20260803-107 -- Alterar Senha partida para todos: modal sem campo Senha Actual

- **Severity:** P1
- **Category:** ux
- **Owner specialist:** watcherdb-frontend-specialist
- **Evidence:** backend `/api/auth/change-password` exige `current_password` (auth_compat.py:365, verificacao bcrypt em :374), mas a modal `changePasswordModal` so tinha campos Nova/Confirmar e o submit enviava apenas `new_password` -- resultado: "Password actual obrigatoria" sempre, sem campo onde a escrever. A troca de senha via portal NUNCA funcionou nesta versao da modal, para todos os users. Descoberto quando o owner tentou trocar a senha apos reset (03/08).
- **Recommendation:** aplicado. Campo Senha Actual adicionado (autocomplete=current-password, focus inicial), validacao client-side e payload com current_password. Grep V6: mesma modal provavel (comentario "igual ao V6" no auth do portal) -- incluido no lote de propagacao.
- **Status:** fixed (commit nesta sessao), pendente validacao do owner no browser
- **Created:** 2026-08-03
- **Updated:** 2026-08-03

---

## FIND-20260804-101 -- Manual do cliente prometia ecra de thresholds inexistente com defaults errados

- **Severity:** P1
- **Category:** docs
- **Owner specialist:** docs-writer
- **Evidence:** `docs/guides/MANUAL_SIMPLIFICADO_PT.md:106-122` dizia "ajusta-los em Control -> Configuracoes -> Thresholds" (ecra que nao existia) e listava valores que nao batem com o codigo (CPU 70/85 vs 95 real; backup FULL 24/48h vs 120/168h; memoria/disco/tlog/deadlocks sem correspondencia). Achado do `challenger` no painel de 2026-08-04.
- **Recommendation:** aplicado na Fase 0 — tabela reescrita com os defaults REAIS (fonte: api/kpi_thresholds_registry.py) e o ecra passou a existir de verdade: "Configuracoes -> Thresholds em vigor" (read-only, alimentado por /api/intelligence-kpis/thresholds).
- **Status:** fixed (commits da Fase 0, 2026-08-04)
- **Created:** 2026-08-04
- **Updated:** 2026-08-04

---

## FIND-20260804-102 -- GRANT drift na WDB_KPI_MUTE: canonical so da SELECT mas a app escreve

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** achado do gate V1 (painel thresholds 2026-08-04): `INSTALACAO_COMPLETA_UNIFICADA.sql:~2011` tem apenas `GRANT SELECT ON dbo.WDB_KPI_MUTE TO sql_monitoring`, mas `api/routers/kpi_mute.py:139-181` faz MERGE/DELETE com essa login. Ou existe grant fora-de-banda na BD viva (schema drift, mesma classe do gap R+10/Wave U) ou o mute esta partido em fresh install.
- **Recommendation:** verificar na BD viva (query pronta em DESIGN_THRESHOLDS_CLIENTE_2026-08-04.md 5.1 — pendente por rede instavel a 04/08 de manha); corrigir canonical + excepcao Rule #8 datada no mesmo commit. Pre-requisito antes de replicar o padrao de escrita na futura WDB_KPI_THRESHOLDS (Fase 1).
- **Resolucao (04/08 tarde):** verificado na BD viva — a escrita "funciona" porque `sql_monitoring` e' membro de **db_owner + db_datareader + db_datawriter** (ver FIND-20260804-104). O grant granular do canonical e' irrelevante enquanto o db_owner existir; o fix real e' o da 104 (separacao de identidades), nao um GRANT pontual.
- **Status:** root-cause found — absorvido pelo FIND-20260804-104
- **Created:** 2026-08-04
- **Updated:** 2026-08-04

---

## FIND-20260804-103 -- TempDB com duas verdades: view Status usa 70/85/95, backend usa 60/80

- **Severity:** P2
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** sweep das definicoes das views (04/08): `KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW` calcula coluna `Status` com ATTENTION>=70 / WARNING>=85 / CRITICAL>=95, enquanto o backend V3.3 (registry: tempdb_usage) classifica warning>=60 / critical>=80. O card V3.3 usa o backend; qualquer consumidor da coluna Status da view (V5/V6/relatorios) ve outra verdade. Valores reais das restantes views tambem confirmados e espelhados no registry: deadlocks 10/20, tlog 85/95, disco por tiers Percent_Free (C: especial).
- **Recommendation:** reconciliar num lote proprio (decidir a verdade unica e alinhar view OU backend; view e' partilhada -> gate V1). Registry ja documenta o drift na entry tempdb_usage.
- **Status:** open
- **Created:** 2026-08-04
- **Updated:** 2026-08-04

---

## FIND-20260804-104 -- sql_monitoring e' db_owner da WatcherDB_Intelligence (viola Regra de Ouro #2)

- **Severity:** P1
- **Category:** security
- **Owner specialist:** watcherdb-security-auditor (+ watcherdb-v1-intel-specialist, veto infra)
- **Evidence:** verificado na BD viva a 04/08 (`sys.database_role_members`): `sql_monitoring` e' membro de **db_owner, db_datareader, db_datawriter**. `fn_my_permissions` confirma ALTER/CONTROL/DELETE/INSERT/TAKE OWNERSHIP em objectos. A conta "SELECT-only" do CLAUDE.md pode na pratica dropar tabelas. E' por isto que kpi_mute.py, WatcherDB_Users, tribunal etc. escrevem sem grants granulares — os GRANTs do canonical sao teatro enquanto o db_owner existir. Num audit banking isto e' finding de primeira pagina.
- **Recommendation:** wave propria de SEPARACAO DE IDENTIDADES (nao mexer ad-hoc — os colectores V1 escrevem nas STG com esta mesma login; revogar db_owner as cegas para a colecta toda): (1) inventariar TODAS as escritas legitimas por componente; (2) desenhar logins separados (colector-writer, portal-app com grants minimos, sql_monitoring leitura pura); (3) aplicar com rollback testado. Dispatch sugerido: watcherdb-security-auditor + v1-intel em paralelo. Ate la, F1 dos thresholds NAO deve nascer em cima deste modelo sem o nomear.
- **DECISAO DO OWNER (04/08):** o db_owner de sql_monitoring e' **INTENCIONAL** e mantem-se **ate ao fim do desenvolvimento da aplicacao** (facilita o trabalho de dev sem atrito de permissoes). Nao e' descuido — e' trade-off consciente. A wave fica **DESENHADA E DIFERIDA** para a fase de hardening pre-producao/pre-1o-cliente. Design completo (4 pareceres convergentes, 6 fases, rollback por fase, cross-produto V6) em `docs/context/DESIGN_SEPARACAO_IDENTIDADES_2026-08-04.md`, pronto a executar quando a app fechar. Ate la: qualquer feature nova (ex.: F1 thresholds) assume este modelo sem o combater; escritas ad-hoc com sql_monitoring sao aceitaveis no periodo de dev.
- **Status:** deferred (owner decision — executar no hardening pre-producao)
- **Created:** 2026-08-04
- **Updated:** 2026-08-04

---

## FIND-20260804-105 -- Contador de Avisos do Resumo Executivo ignorava o filtro de ambiente

- **Severity:** P1
- **Category:** ux
- **Owner specialist:** watcherdb-frontend-specialist
- **Evidence:** owner reportou (04/08): ao seleccionar um ambiente (ex. QLT), os Criticos e Instancias filtravam mas os **Avisos** mantinham o total global (1.371). Causa: em `_repFilData` e `_repTopCards` o `critOf(g)` usava `_kpiGroupCritEnv` (respeita envSel) mas o warn usava `_kpiGroupWarn(g, data)` (sempre global) — faltava a variante por-ambiente do warn, simetrica a `_kpiGroupCritEnv`.
- **Recommendation:** aplicado. Nova funcao `_kpiGroupWarnEnv` (espelho de `_kpiGroupCritEnv` sobre `g.warn`) + `warnOf(g)` nos dois sitios do dashboard. Limitacao inicial (integrity-p4 sem by_env) RESOLVIDA no FIND-106/opcao A (backend passou a expor p4_by_env).
- **Status:** fixed (commit nesta sessao), pendente validacao do owner no browser
- **Created:** 2026-08-04
- **Updated:** 2026-08-04

---

## FIND-20260804-106 -- Disponibilidade mostra 100% com coleta PARADA: falso "tudo bem" por staleness

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** owner questionou (04/08 ~15h50) porque o card de Disponibilidade nao acusava instancias em falta. Verificado na BD: `KPI_MSSQL_INST_AVAILABILITY_ACTIVE` tem 47 instancias, TODAS Is_Available=1 (0 offline), mas a ultima coleta por ambiente esta ATRASADA: **PRD 41 instancias -> ultima coleta ha 50 min; TST ha 46 min; QLT ha 15 min**. So as 5 QLT dentro da janela de frescura. O card mostra 100% online porque usa o ULTIMO VALOR CONHECIDO (Is_Available=1) sem sinalizar staleness — se uma instancia PRD caisse agora, o card nao saberia por ~50 min. Explica a oscilacao do contador de instancias que o owner viu (62->44). NAO estao offline; a COLETA de availability e' que esta parada/atrasada.
- **Contexto provavel:** a rede mudou hoje (portal migrou de 10.88.15.254 para 10.88.0.201; VPN a trocar de endereco). Os ciclos de availability por ambiente (run_availability_PRD/QA/TST) podem estar a falhar a ligacao pos-mudanca de IP — mesma classe das waves de resiliencia de rede de 28/07.
- **CAUSA-RAIZ CONFIRMADA (04/08 16h):** a availability e' coletada pelo servico `WatcherDBCollector` (config.yaml: inst_availability por ambiente, cadencia 2/3/5 min PRD/QA/TST). O servico estava DEGRADADO: uptime ~22h (ultimo start 03/08 18:26, nao reiniciou hoje — Event Log), ~2GB RAM, e processos python filhos PRESOS. O `cleanup_stuck_python.ps1` confirmou: PID 28668 e 36036 travados ha **1398/1399 min (~23h)** desde 03/08 16:53, + 41416 (390min) + 35740 (464min). Ciclos de coleta emperrados nos zumbi -> availability parou de correr apesar do servico "Running". TempDB/latencia ficaram frescos hoje porque correm por TASKS separadas, nao pelo servico. Nada offline — coleta emperrada.
- **Resolucao (04/08 16:13, owner):** `cleanup_stuck_python.ps1` (4 processos mortos) + `Restart-Service WatcherDBCollector`. Validacao da recuperacao da cadencia em curso (poll da frescura por ambiente).
- **Follow-up (parte de PRODUTO, aberto):** o card de Disponibilidade DEVIA sinalizar staleness (selo "dados de ha Xmin" ou excluir stale da contagem de online) em vez de 100% do ultimo valor — falso positivo mascara indisponibilidade real. Sem isto, um servico emperrado volta a dar falso tudo-bem. Cruzar com a regra server-offline-vs-event. Lote proprio (frontend).
- **Follow-up (INFRA, aberto):** servico a emperrar com python zumbi e' recorrente (o cleanup existe por isso). Considerar watchdog que reinicia o servico se a frescura da availability passar N min — auto-cura em vez de deteccao manual.
- **NOTA de honestidade:** a AI afirmou antes "as instancias TST estao offline" SEM verificar — errado. O card 0-offline denunciou a afirmacao. Licao: nao inferir estado de coleta de contagens; verificar frescura na BD.
- **RESOLUCAO CONFIRMADA (04/08 16:51):** todos os ambientes recuperaram a cadencia apos o restart — PRD 41inst/1min, QLT 15inst/2min, TST 6inst/2min. O PRD demorou ~30min (recuperou 16:45/16:50) porque o ciclo tem 42 servidores + timeouts (ver sub-achado). O poll parou cedo (16:22) e por isso nao apanhou a recuperacao de PRD.
- **SUB-ACHADO / CAUSA DA RECORRENCIA (novo finding candidato):** o log inst_availability mostra 4 servidores PRD que atrasam TODO o ciclo, cada um bloqueando 60s: `SQLIDSPRD03_I01` (TIMEOUT, e' o mesmo com P1 corrupcao), `SQLMDMPRD02_I01` (TIMEOUT), `SQLHDSGENPRD02_I01` (TIMEOUT), `OATXP01` (DB_ERROR 42S22 — erro de query, SQL antigo). Estes 60s×N por ciclo sao a raiz provavel de o servico emperrar ao longo de horas (ciclos acumulam -> python zumbi). Restart cura o sintoma; enquanto estes 4 fizerem timeout, volta. Investigar: rede/porta/firewall dos 3 timeouts (agravado pela mudanca de IP de hoje?); OATXP01 erro de query e' compat SQL antigo.
- **Status:** FIXED (restart, owner) — availability fresca em todos os ambientes. 2 follow-ups abertos: (produto) card sinalizar staleness; (infra) watchdog auto-reinicio + investigar os 4 servidores PRD lentos.
- **Created:** 2026-08-04
- **Updated:** 2026-08-04

---

## FIND-20260804-107 -- Baseline: guard incremental de 25h com cadencia diaria recalcula em dias alternados

- **Severity:** P3
- **Category:** correctness
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** achado no gate v1-intel da migracao do baseline para SQL Agent job (04/08). `usp_compute_kpi_baseline` (`CREATE_USP_COMPUTE_KPI_BASELINE_WAVE_V.sql:81-83` e `114-116`) exclui do recompute qualquer instancia com `Last_Computed >= DATEADD(HOUR, -25, @window_end)`. Com o job a correr diario (agora 04:00), no dia N+1 o `Last_Computed` tem 24h < guard de 25h -> instancia excluida (no-op); no dia N+2 tem 48h > 25h -> recomputa. Padrao alterna: recalcula de 2 em 2 dias, nao diariamente. Contradiz a decisao de design D2 ("Daily incremental"). Provado em vivo 04/08: 1o disparo do job (17:03, ~5h apos compute manual das 11:45) foi no-op OK; so com `@Force_Full=1` forcado o `Last_Computed` saltou.
- **Impacto:** dados NAO corrompem (quando corre e' full 30d recompute, nao parcial). MAS: assim que o indicador de frescura do portal for ligado (o `BASELINE_COMPUTE_DEPLOY.md:136` documenta um alerta a `DATEADD(HOUR,-28,...)`), dispararia FALSO em ~metade dos dias, porque o baseline legitimamente tem ate 48h. Latente ate' esse indicador existir (Fase 2 portal, ainda nao ligado).
- **Recommendation:** fast-follow ANTES de ligar qualquer indicador de frescura de baseline no portal. Baixar o guard para <24h (ex. `DATEADD(HOUR, -20, @window_end)`, ~4h de folga para atraso do Agent sem cair no ciclo alternado) OU trocar por comparacao por dia de calendario (`CAST(Last_Computed AS DATE) < CAST(@window_end AS DATE)`). E' mudanca a proc (nao ao job) -> gate v1-intel + teste antes de aplicar. NAO aplicado nesta sessao (fora do scope da migracao do job).
- **Status:** open (fast-follow)
- **Created:** 2026-08-04
- **Updated:** 2026-08-04

---

## FIND-20260804-108 -- collector_service: poller do "Run now" liga a BD por Trusted_Connection (viola Regra de Ouro #2)

- **Severity:** P1
- **Category:** security
- **Owner specialist:** watcherdb-deploy-architect (achado no gate da Frente 2) + watcherdb-security-auditor (cruza com FIND-20260804-104)
- **Evidence:** `WATCHERDB INTELLIGENCE V1/services/collector_service/service.py:519-527` — o `_start_manual_run_poller` (thread que le `dbo.collector_run_requests` a cada 10s para o botao "Run now" do portal) tem a connection string HARDCODED: `SERVER=SQLHDSTST505\I01; Trusted_Connection=yes`. Verificado no codigo (linhas 521-527). Confirmado por grep que `service.py` NAO importa `ServerManager` (zero ocorrencias) -- esta e' a unica via de ligacao do servico que ignora o `sql_monitoring`. Liga a BD pela identidade Windows do servico (hoje provavelmente LocalSystem ou a sessao do dev com acesso acidental), nao por sql_monitoring. TRIPLO problema: (1) viola Regra de Ouro #2 (Windows Auth a tocar na BD); (2) liga por nome de instancia -> sujeito ao 08001 do SQL Browser/firewall (mesma fragilidade do baseline); (3) BLOQUEIA a Frente 2 -- dar ao servico uma conta AD dedicada faria o poller ligar-se com um domain user NOMEADO na connection string, pior que hoje.
- **Recommendation:** substituir a connection string hardcoded por uma construida via `ServerManager().get_master_server()` (UID=sql_monitoring), mesmo default de config que os collectors irmaos (nao escolhe entre as 2 copias de servers.json). NUANCE: o poller faz UPDATE em collector_run_requests (RUNNING/DONE/FAILED), nao so SELECT -> so funciona porque sql_monitoring E' db_owner hoje (FIND-20260804-104, decisao consciente ate hardening); e' CONSISTENTE com base_collector.store() (que ja escreve via sql_monitoring). Quando FIND-104 separar identidades, o poller pertence ao login watcherdb_collector (escrita), nao ao sql_monitoring-leitura. Nao usei override ip,porta (mantem consistencia com os irmaos; a fragilidade nome-instancia/Browser e' service-wide, resolve-se com a porta estatica / servers.json para todos de uma vez).
- **Fix aplicado e PROVADO:** service.py:519-537 (poller_loop) reescrito com ServerManager()+sql_monitoring + guard use_windows_auth. Compila (py_compile OK). Committado a6d5dcc. Restart-Service feito 04/08; service.log mostra `[POLLER] ... (10s interval, sql_monitoring)` 2x (19:15, 19:26) -- a linha so imprime apos ServerManager()/conn_str terem sucesso; errors.log SEM erros de poller/ligacao desde o restart (o except escreveria a cada 10s se pyodbc.connect falhasse). Poller a ligar via sql_monitoring, Trusted_Connection eliminado. NB: 2 arranques em 11 min = provavel crash nativo 0xc0000005 (FIND-20260702-001), nao o poller (imprimiu sucesso nas 2 vezes).
- **Status:** FIXED (committado a6d5dcc, provado ao vivo)

---

## FIND-20260805-109 -- Canonical NAO cria as tabelas base _STG_BLUE/_GREEN de varios KPIs core: fresh install nao recolhe Backups/TLOG/ErrorLog/BackupExec

- **Severity:** P1 (critical p/ deployment de cliente novo)
- **Category:** data-integrity
- **Owner specialist:** watcherdb-v1-intel-specialist (achado ao mapear a Fase 3 dos indices, 2026-08-05)
- **Evidence:** `INSTALACAO_COMPLETA_UNIFICADA.sql` NAO contem `CREATE` das tabelas base `_STG_BLUE`/`_STG_GREEN` para: `KPI_MSSQL_BACKUPS_STG`, `TLOG_USAGE_STG`, `ERRORLOG_STG`, `BACKUP_EXEC_FAILURES_STG`, `BACKUP_JOBS_DISABLED_STG`, `FG_USAGE_STG`, `BLOCKED_SESSIONS_STG`. Essas base BLUE/GREEN so existem em scripts standalone NUNCA mergeados: `SETUP_BLUE_GREEN_COMPLETO.sql` (BACKUPS :196-201, TLOG :540-545) e `CREATE_BACKUP_HEALTH_STG_TABLES.sql` (:76,125,207,242). O collector escreve sempre em `_BLUE_<ENV>` via `fn_get_kpi_collection_target_env` (base_collector.py:427-439); sem a base, o `usp_setup_environment_tables` faz no-op (IF NOT EXISTS RETURN) e as `_env` nunca nascem. Confirmado: `KPI_MSSQL_BACKUPS_STG_BLUE`/`TLOG_USAGE_STG_BLUE` ausentes do canonical (so as legadas sem sufixo em :908/:1221). Docs de ordem de instalacao (ESTRUTURA_PROJETO.md:274) so listam INSTALACAO + POPULAR_INST_ENVS — os standalone nao estao na ordem.
- **Impacto:** um fresh install a partir SO do canonical (o que um cliente novo recebe) **nao recolhe** varias KPIs core (Backups, TLOG Usage, ErrorLog, Backup Exec/Jobs Failures, FileGroup Usage, Blocked Sessions). O ambiente vivo actual funciona porque as tabelas foram criadas fora-de-banda pelos standalone algures. Precede e e' maior que a limpeza de indices.
- **Recommendation:** wave propria, PRIORITARIA sobre a Fase 3 dos indices. Portar as linhas de CREATE base BLUE/GREEN dos standalone (SETUP_BLUE_GREEN_COMPLETO + CREATE_BACKUP_HEALTH_STG_TABLES) para o canonical, seguindo o padrao ja usado na SECCAO 22.8b (que fechou o mesmo gap para 8 familias). VETO do v1-intel: NAO fechar a parte de indices de BACKUPS/TLOG (Q3) sem primeiro resolver esta ausencia — mascararia o gap maior atras de um diff cosmetico.
- **Status:** open (scope CORRIGIDO 2026-08-06, ver abaixo)
- **Created:** 2026-08-05
- **Updated:** 2026-08-06
- **CORRECÇÃO 2026-08-06 (gate v1-intel ao patch):** o scope de 7 famílias estava SOBRE-estimado. Das 7, **5 (BACKUPS, TLOG, ERRORLOG, FG_USAGE, BLOCKED_SESSIONS) JÁ ESTÃO cobertas** pelo canonical: o loop genérico `@2201-2246` cria os `_BLUE/_GREEN`, os callers `@2620` chamam a proc, e a Wave C (`:16436`) particiona o ACTIVE por ambiente. O gap GENUÍNO é só **2 famílias — BACKUP_EXEC_FAILURES + BACKUP_JOBS_DISABLED** (o `EXEC usp_setup_environment_tables` foi adicionado 30/07 mas as `_BLUE/_GREEN` fonte nunca foram criadas em canonical; comentário `:2633-2637`). Severity efectiva P2, não P1. Patch corrigido: `PATCH_BLOCO_A_FRESH_INSTALL_BASE_TABLES_2026-08-06.sql` (Bloco A = 2 famílias verbatim sem view; Bloco B = registar nas listas usp_create_active_view/usp_create_stg_alias). GAP SEPARADO MAIOR surfaçado: `usp_create_stg_alias` faz SKIP quando a legada ainda é tabela física (~12-14 famílias) — liga ao finding PROCESSES/DISK_USAGE de 04/08, Opção 1 Python-side, fora deste scope. VERIFICAR: GRANT ALTER só no nome legado (:6764), não nas físicas `_BLUE_PRD/QA/TST`.

---

## FIND-20260805-110 -- 5 KPIs com view a ler tabela sem sufixo de ambiente enquanto o collector escreve _BLUE_<ENV>: fresh install deixa-os a falhar

- **Severity:** P2 (high)
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** `INSTALACAO_COMPLETA_UNIFICADA.sql:12117-12166` — as views de `FILE_IO`, `WAIT_STATS`, `INDEX_USAGE`, `WORKER_THREADS`, `AG_QUEUE_SIZES` leem a tabela `_BLUE`/`_GREEN` SEM sufixo de ambiente, mas o collector escreve sempre em `_BLUE_<ENV>` (fn_get_kpi_collection_target_env, base_collector.py:427-439). O mesmo gap foi fechado para PERF_COUNTERS/PERF_COUNTERS_DETAIL em 22/07 (:12090-12111 com comentario a admitir o drift) mas NUNCA estendido a estas 5. Alem disso, nao ha ponto no canonical que crie as variantes `_BLUE_<ENV>` destas 5 (nem via proc — nao estao nos callers — nem inline com sufixo).
- **Impacto:** fresh install deixa estes 5 collectors a falhar TRUNCATE/INSERT em tabela inexistente todos os ciclos; e as views leriam a base molde vazia. Mesma classe do gap das "8 familias" (:12546) e do FIND-109.
- **Recommendation:** juntar a wave do FIND-109 (reparacao de fresh install). Estender o padrao _env que ja foi aplicado a PERF_COUNTERS.
- **Status:** open (P2, junto ao FIND-109)
- **Created:** 2026-08-05
- **Updated:** 2026-08-05
- **Created:** 2026-08-04
- **Updated:** 2026-08-04

---

## FIND-20260806-114 -- Backups de AG: primario nao recolhido, secundario fossilizado, cadeia partida invisivel

- **Severity:** P1
- **Category:** coverage
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** `SQLHDSPRD214_I01` (PRD, primario do AG SQLAGSPRD213) tem ZERO linhas em `dbo.KPI_MSSQL_BACKUPS_STG`; o par `SQLHDSPRD213_I01` (secundario) tem 37 linhas mas com `Last_Backup_Date` congelado em 2026-05-24/26 (~72 dias, msdb fossilizado pos-failover). `DBADashDB` so' existe no 214 (config/servers.json, databases[] descobertas 2026-08-06T06:52). Reportado por DBA da equipa via Teams (2026-08-06, query "Backups major 7 days"): DBA_POC, DBADashDB e MAP_SampleDB com Full=31 dias / Diff=1 dia -- cadeia de restauro partida. Card do portal mostrava `Full falhou=0` (semanticamente correcto: nao ha falha de job, ha' ausencia de job) e `Em atraso=576` (sinal afogado em ruido). Cruzamento de 47 instancias sem qualquer linha de backup: 33 orfaos em INST_ENVS (nao estao em servers.json), 13 QLT sem ligacao (firewall UDP1434, ja diagnosticado 2026-08-05), 1 gap NOVO = o 214. Nota: Backup_Type usa convencao msdb D/I/L, nao FULL/DIFF/LOG.
- **Impacto:** o produto nao detectou uma base de producao sem backup full ha 31 dias com diffs a correr diariamente (cadeia inrestauravel). Foi um humano, com outra ferramenta, que apanhou. Para cliente banking e' exactamente a pergunta "como e que isto escapou". Escala potencial: se os 15 AGs da frota tiverem o mesmo padrao de recolha, metade da visibilidade de backups em AG e' cega ou fossilizada.
- **Recommendation:** (1) determinar porque o colector nao recolhe do primario do AG; (2) decidir de que no(s) recolher -- msdb e' per-instancia e apos failover o antigo primario fossiliza, logo recolher de um so' no da sempre vista parcial; (3) separar secundarios fossilizados dos 576 "em atraso" (ruido estrutural vs sinal); (4) avaliar KPI novo "cadeia partida" (full antigo + diff recente), que e' o sinal accionavel que faltou -- ver relacao com R+14 Silent Backup Failure (DEFERRED).
- **Status:** open (dispatch watcherdb-v1-intel-specialist 2026-08-06)
- **Created:** 2026-08-06
- **Updated:** 2026-08-06

---

## FIND-20260810-101 -- Drift canonical INSTALACAO vs views vivas: PROCESSES/TLOG/BACKUPS/DEADLOCKS instalavam definicoes diferentes das da frota

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** Provado na BD viva 2026-08-10 (owner, sys.sql_modules em SQLHDSTST505\I01): PROCESSES_AGG viva = 20/50 runnable + Runnable_Count (canonical dizia 500/1000 sessoes, sem a coluna); TLOG_AGG viva = 85/95 lendo _ACTIVE (canonical 70/90 lendo _STG); BACKUPS_AGG viva le _ACTIVE (canonical _STG); DEADLOCKS canonical tinha bloco morto sem [State]/Severity (superseded pela SECAO 18.2). Definicoes vivas coincidem com SPRINT5_FIX_ALL_VIEWS_NOLOCK.sql. Detectado pelos pareceres challenger + v1-intel-specialist na 2a ronda dos thresholds "camada de recolha".
- **Impacto:** fresh install / disaster recovery instalava thresholds e shapes diferentes dos que o codigo V3.3/V6 assume (V6 consome PROCESSES em 4 sitios, TLOG em 6, DEADLOCKS em 8). Sexta camada de "duas verdades" -- bloqueava qualquer configurabilidade futura de thresholds.
- **Recommendation:** APLICADO nesta wave: canonical V1 + copia V6 sincronizados (E1 in-place PROCESSES; SECAO 10.5 nova para TLOG/BACKUPS sobre _ACTIVE, porque CREATE VIEW nao tem deferred resolution e _ACTIVE nasce na SECAO 10; ponteiros nos stubs; DEADLOCKS: bloco morto removido no V1, substituido in-place no V6 que nao tinha a SECAO 18). PENDENTE owner: verificar TLOG_USAGE_DET_VIEW viva (suspeita HIGH: sem [Used%]/Available_GB, o report V6 fica silenciosamente vazio) e aplicar ALTER de aliases -- bloco em docs/context/WAVE_RECONCILIACAO_CANONICAL_2026-08-10.md.
- **Addendum 2026-08-11:** existe uma TERCEIRA copia do canonical em `WATCHERDB_V3.3/database/INSTALACAO_COMPLETA_UNIFICADA.sql` (snapshot de Abril, mtime 22/04) com o mesmo drift (PROCESSES 500/1000 linha 2951, TLOG 70/90 linha 3002). NAO foi sincronizada nesta wave: esta' globalmente stale desde Abril e corrigir so' 4 views dar-lhe-ia frescura falsa. Decisao pendente (v1-intel): apagar a copia (fonte unica = repo V1) ou refresca-la por inteiro.
- **Addendum 2026-08-11 (execucao owner):** a TLOG_USAGE_DET_VIEW NAO EXISTE na BD viva -- o SPRINT5 fez DROP e o CREATE falhou (Msg 207: Log_Size_MB/Log_Used_MB nao existem; schema real = Current_MB/Used_MB/Max_Available_MB). O report TLOG do V6 esta mudo porque o objecto falta. SECAO 10.5 dos dois canonicals corrigida para o schema real a 2026-08-11 (a primeira versao copiava o erro do SPRINT5). Pendente owner: PASSO 0-2 revistos no wave doc (sys.columns -> CREATE VIEW -> verificar).
- **Addendum 2026-08-11 (fecho BD viva):** owner executou o plano completo: PASSO 0 confirmou schema real (7 colunas, Current_MB/Used_MB), CREATE VIEW aplicado, PASSO 2 devolve dados vivos (top 5 tudo CRITICAL: MSS10_QLT_* a 99.4-99.7% no SQLHDSQLT301_I02; ctrlm_tap_report 99.12% no SQLHDSPRD405_I01 PRD; RequestManagerSystem 98.51% no TST023). Canonical == BD viva para as 4 views TLOG/BACKUPS + PROCESSES + DEADLOCKS. Report TLOG do V6 cura-se no proximo ciclo sem mudanca de codigo.
- **Status:** open so' para a copia V3.3/database (decisao apagar vs refrescar); resto RESOLVIDO 2026-08-11
- **Created:** 2026-08-10
- **Updated:** 2026-08-11

---

## FIND-20260811-101 -- Card Offline vs modal Instances Off: mesma view, momentos diferentes, sem honestidade temporal (2 vs 6)

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** Screenshot owner 2026-08-11: card DISPONIBILIDADE Offline=2, modal Instances Off=6 (PRD 4, QLT 1, DEV 1). Ambos leem KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WHERE Ping_OK=0, MAS em momentos diferentes: o card usa off_count do payload do relatorio (helpers.py:1154-1160, calculado no ciclo de refresh) e a modal faz query VIVA ao abrir (intelligence_kpis.py:1459-1472). A view e' volatil por desenho (so eventos nao-resolvidos dos ultimos 15 min, excluindo servidores coletados ha <10 min) -- dois instantes dao contagens diferentes. Consistente com o screenshot: 2 servidores tem badge "4min" (acabados de entrar na janela). Factor secundario possivel: filtro de ambiente activo no relatorio (ev() soma so envs seleccionados via off_by_env).
- **Impacto:** par cartao/drill-down contradiz-se no mesmo ecra (regra R3 do handoff 08/08) sem nenhuma indicacao de que sao leituras de momentos diferentes. E' a mesma familia do FIND-106 (staleness invisivel). Mina confianca do DBA no produto.
- **Recommendation:** decidir 1 de 3 (consulta specialist antes): (a) modal consome o MESMO payload do card (par atomico; refresh conjunto), (b) card refetch ao abrir modal, (c) ambos mostram timestamp da leitura ("visto ha Xs") tornando a divergencia explicavel. Verificacao do owner: correr o SELECT da view e comparar com card+modal NO MESMO minuto; carregar Atualizar e reabrir modal -- devem convergir.
- **Status:** open
- **Created:** 2026-08-11
- **Updated:** 2026-08-11

---

## FIND-20260811-102 -- Drilldown Instances OK ainda classifica Env por LIKE no nome (violacao R2 corrigida no card a 07/08, mas nao no par)

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** api/routers/intelligence_kpis.py:1442-1447 -- ramo ok=true do kpi_type instance-availability usa CASE WHEN Instance LIKE '%PRD%'... (inclui '%DEV%' -> TST). O card foi corrigido a 2026-08-07 para INST_ENVS (helpers.py:1163-1182, comentario documenta 4 servidores mal classificados pelo LIKE); o drilldown do MESMO KPI ficou com o metodo velho. Chave aqui E' Instance, logo o padrao INST_ENVS aplica-se directamente (nao e' um dos 2 blocos Hostname/Server_Name do handoff paragrafo 5).
- **Impacto:** modal Instances OK mostra ambientes diferentes do card Por Ambiente para as mesmas instancias (SQLSCOMINSTP03/04, SCCM2012P01 somem em Undefined; SQLMDMDEV03 vai para TST em vez de QLT-frota real medida 07/08).
- **Recommendation:** substituir o CASE LIKE por LEFT JOIN KPI_MSSQL_INST_ENVS + ISNULL(Env,'Undefined') igual ao card (padrao ja validado). Incluir na proxima wave de paridade card-modal.
- **Status:** open -> fix aplicado 2026-08-11 (LEFT JOIN INST_ENVS no ramo ok=true, mesmo metodo do card). Aguarda browser test da modal Instances OK
- **Created:** 2026-08-11
- **Updated:** 2026-08-11

---

## FIND-20260811-103 -- Card "Instancias c/ servicos em baixo" cablado a fonte errada: conta por SERVICE_STATUS_AGG mas o clique abre SERVER_OFFLINE_GROUPED

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-frontend-specialist
- **Evidence:** templates/watcherdb_portal.html:34325 -- _advRow passa kpiType 'sql-services-down', cujo ramo (intelligence_kpis.py:2099-2138) le KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WHERE Diagnosis='sql_down'. O card conta por KPI_MSSQL_SERVICE_STATUS_AGG_VIEW (helpers.py:1754-1776). Views/collectors diferentes = numero e lista podem contradizer-se sempre. O endpoint da fonte certa ('service-status', intelligence_kpis.py:1423) existe e nunca e' chamado. Censo completo: docs/context/CENSO_PARIDADE_CARTAO_MODAL_2026-08-11.md
- **Recommendation:** trocar o 5o argumento do _advRow para 'service-status' (1 linha, batch B1 do censo). Browser test do par depois (regra browser-test-event-handlers).
- **Status:** open -> fix aplicado 2026-08-11 (kpiType service-status + mapeamento tab + renderer mostra Services_Down_List). Aguarda browser test
- **Created:** 2026-08-11
- **Updated:** 2026-08-11

---

## FIND-20260811-104 -- Linha "Drives c/ latencia em aviso" abre a modal dos CRITICOS

- **Severity:** P1
- **Category:** ux
- **Owner specialist:** watcherdb-frontend-specialist
- **Evidence:** templates/watcherdb_portal.html:34379 -- _advRow de aviso usa kpiType 'disk-latency-critical'; o ramo com is_critical=True (intelligence_kpis.py:2307-2382) filtra acima do threshold critico. DBA clica em "aviso" e ve 0 ou so criticos. O kpiType 'disk-latency-warning' existe (:2310) e nao e' usado nesta linha.
- **Recommendation:** trocar para 'disk-latency-warning' (1 linha, batch B1 do censo).
- **Status:** open -> fix aplicado 2026-08-11 (kpiType disk-latency-warning + titulo proprio). Aguarda browser test
- **Created:** 2026-08-11
- **Updated:** 2026-08-11

---

## FIND-20260811-105 -- Toast critico "Instancias Offline" da' HTTP 400 ao clicar (kpiType inexistente)

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-frontend-specialist
- **Evidence:** templates/watcherdb_portal.html:5948 -- TOAST_CRITICAL_CHECKS[0] usa kpiType 'instance-availability-off', que nao tem ramo no backend (so 'instance-availability'); onclick (6119-6123) chama showProblematicInstances e o endpoint devolve 400 (else raise HTTPException, intelligence_kpis.py:2425-2426). E' o toast mais urgente do produto (servidor caiu) e o clique parte.
- **Recommendation:** usar kpiType valido ('instance-availability') no toast (batch B6). Testar o clique no browser.
- **Status:** open -> fix aplicado 2026-08-11 (toast passa a instance-availability, mesmo caminho do card). Aguarda browser test
- **Created:** 2026-08-11
- **Updated:** 2026-08-11

---

## FIND-20260812-101 -- MSI: ServiceInstall num componente sem File keypath (rollback silencioso)

- **Severity:** P0
- **Category:** reliability
- **Owner specialist:** watcherdb-deploy-architect
- **Evidence:** deploy/msi/Product.wxs:148 tinha KeyPath="yes" no proprio Component (idioma "directory as keypath" do WiX v3). InstallServices deriva o ImagePath do KeyPath do componente que contem a linha ServiceInstall, logo o servico ficava registado a apontar para a PASTA INSTALLFOLDER. Lido das tabelas do .msi compilado (COM WindowsInstaller, read-only): Component.KeyPath vazio, Attributes=256. Com Vital=yes + ServiceControl Start=install Wait=yes, a falha revertia a transaccao inteira.
- **Recommendation:** XSLT no heat a excluir watcherdb.exe do harvest + File KeyPath=yes dentro do ServiceRegistrationComp.
- **Status:** FIXED 2026-08-12 (commit e726645). Provas no MSI reconstruido: BundleFiles sem watcherdb.exe, Component.KeyPath=watcherdb.exe, 1 unica linha na tabela File. Instalacao real validada ponta-a-ponta em SQLHDSPRD213.
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-102 -- MSI sem tabela Error: qualquer falha faz rollback mudo

- **Severity:** P1
- **Category:** ux
- **Owner specialist:** watcherdb-deploy-architect
- **Evidence:** _Tables do .msi nao continha Error. WixUI_Minimal sozinho nao a popula. O operador via "Rolling back action" sem uma palavra sobre a causa; no log so' aparecia "Note: 1: 2205 ... Table: Error", que passa por ruido de rotina.
- **Recommendation:** UIRef WixUI_ErrorProgressText a seguir ao WixUI_Minimal.
- **Status:** FIXED 2026-08-12 (commit e726645). Strings 1920/1923 confirmadas presentes no MSI reconstruido.
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-103 -- ACL do MSI nao acompanha troca da conta de servico pos-instalacao

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-deploy-architect
- **Evidence:** LockPermissions em DATAFOLDER SUBSTITUI a DACL e mata a heranca; e' aplicada a conta que estiver em SERVICEACCOUNT NO MOMENTO da instalacao. Owner trocou a conta no services.msc depois e o servico passou a morrer com PermissionError(13) e exit code 0 limpo. O comentario no .wxs afirmava que a conta "herda ACL via LogOnAsService" -- falso: e' user right de sessao, sem relacao com ACL NTFS. Nota operacional: icacls /grant so' na raiz nao chegou; foi preciso /T para alcancar os ficheiros ja' existentes.
- **Recommendation:** documentar no INSTALL_GUIDE que a conta se passa no msiexec (SERVICEACCOUNT=...) e nao se troca depois. A prazo, o dialogo de conta no instalador (ideia do owner) resolve na origem.
- **Status:** open (mitigado na VM com icacls /T; Permission SERVICEACCOUNT ja' entra no MSI desde e726645)
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-104 -- MSI nao cria regra de firewall (portal inacessivel de fora)

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-deploy-architect
- **Evidence:** deploy/install.ps1 (via ZIP) faz New-NetFirewallRule; o MSI nao faz nada. Na VM o servico escutava em 0.0.0.0:8433 e o health respondia localmente, mas o browser dava ERR_CONNECTION_TIMED_OUT. Interface DomainAuthenticated, logo a regra tem de cobrir o perfil Domain (ver memoria firewall-profile-interface).
- **Recommendation:** replicar a regra no MSI, ou documentar como passo pos-instalacao obrigatorio no INSTALL_GUIDE.
- **Status:** open (regra criada a mao na VM)
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-105 -- MSI nao regista EventLog sources

- **Severity:** P2
- **Category:** reliability
- **Owner specialist:** watcherdb-deploy-architect
- **Evidence:** install.ps1 faz New-EventLog para WatcherDB e WatcherDBWebServiceV33; o MSI nao. Os eventos aparecem com "The description for Event ID cannot be found" -- o texto ainda vem no corpo, mas a auditoria de licenca fica sem fonte registada.
- **Recommendation:** util:EventSource no Product.wxs, ou documentar.
- **Status:** open
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-106 -- Bundle leva inventario real do vendor (200 instancias + passwords Fernet)

- **Severity:** P0
- **Category:** privacy
- **Owner specialist:** python-packaging-architect
- **Evidence:** dist/watcherdb/_internal/config/ continha servers_27072026.json (564KB), servers.json.backup_pre_reencrypt (590KB), servers.json.backup_pre_sync (582KB) e servers.json.backup_pre_description_sync_20260429 (583KB) -- cerca de 200 entradas cada, com campos de password (prefixo gAAAAA = Fernet). A lista negra em deploy/watcherdb.spec filtrava por NOME EXACTO mais ".bak"/".backup": nenhuma das 4 variantes casa (".bak" nem e' subcadeia de ".backup"; "servers.json.backup_pre_X" nao termina em ".backup"). Atenuantes verificados: a chave Fernet NAO vai no bundle (so' ed25519_public.pem e cacert.pem) e os 4 ficheiros nao estao no git -- sao artefactos locais em config/.
- **Recommendation:** lista BRANCA por extensao no .spec (so .yaml/.yml/.sql/.template) mais gate de conteudo no build que falha se aparecer criptograma ou chave privada no bundle. Tirar os 4 ficheiros de config/ na maquina de build.
- **Status:** FIXED 2026-08-12 (.spec lista branca + verify_no_secrets_in_bundle no build.py). PENDENTE: rebuild com gate verde; limpar config/ na maquina de build. O MSI actual NAO e' distribuivel.
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-107 -- CSP: middleware duplicado esconde a politica real; portal sem um clique funcional no bundle

- **Severity:** P0
- **Category:** reliability
- **Owner specialist:** watcherdb-security-auditor
- **Evidence:** services/web_service/server.py:66 importa o app ja' com o middleware canonico (watcherdb/core/security_headers.py, adicionado em watcherdb_main:587) e a :81 acrescentava por cima o de services/web_service/security/headers.py. Escrever um header substitui, logo ganhava o permissivo em dev, enquanto o bundle (entra por watcherdb_main e nunca passa por server.py) servia o estrito. O estrito e' nonce-only, e nonce NAO se aplica a handlers nem a atributos style: 1034 handlers inline (778 onclick, 226 hover, 23 onchange, 17 oninput, 9 onkeydown, 1 onsubmit) e 6840 style= bloqueados -- 941 erros de consola, zero cliques, barras achatadas. Em vigor desde 2026-04-16 e nunca exercido ate' ao bundle. Explica retroactivamente as 2 anomalias sem causa-raiz da sessao do header (top-right empilhado, gradientes ausentes) que tinham sido atribuidas a cache/extensao/DPI.
- **Recommendation:** um so' middleware mais politica com separacao CSP3 elem/attr (unsafe-inline apenas para atributos, nonce mantido nos elementos), sem CDNs (o portal auto-hospeda /static/vendor/) e sem unsafe-eval (o unico eval do template usa catalogo estatico).
- **Status:** FIXED 2026-08-12 (server.py deixa de empilhar; nova politica em security_headers.py). DEBITO ASSUMIDO: o unsafe-inline de atributo sai quando a migracao de handlers estiver feita (plano de 5 fases no blackboard).
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-108 -- PyArmor BCC parte get_problematic_instances (todas as modais de instancias em 500)

- **Severity:** P0
- **Category:** reliability
- **Owner specialist:** python-packaging-architect
- **Evidence:** /api/intelligence-kpis/instances/{kpi_type} devolvia 500 com "SystemError: error return without exception set" em fastapi/routing.py:312 dependant.call -- antes de qualquer linha do corpo correr. Reproducao isolada (sem PyInstaller, BD mockada): 148 de 152 combinacoes kpi_type x all x ok falham no output BCC; 152 de 152 passam na fonte limpa; as 4 sobreviventes sao as de saida antecipada por HTTPException 400. Funcao com 1327 linhas, 115 ramos if, 810 constantes. Os 2 usos de locals() (:2468/:2472) sao gatilho real mas nao causa unica: corrigidos e recompilados, passa a UnboundLocalError num _var_var_150 sintetico do proprio compilador. NOTA: build.py --allow-unprotected nao servia de teste (so' actua no fallback para ficheiros que FALHAM a compilar; este compila com sucesso).
- **Recommendation:** curto prazo denylist do ficheiro no BCC mais remocao dos locals(); definitivo partir a funcao em cerca de 27 handlers pequenos -- funcoes pequenas nem qualificam para geracao BCC nativa.
- **Status:** FIXED 2026-08-12 (BCC_DENYLIST no build.py com segunda passagem sem bcc + sentinelas em vez de locals()). PENDENTE: rebuild e clicar na modal; wave de refactor da funcao.
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-109 -- JWT_SECRET_KEY ausente mata 4 routers em silencio

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** no arranque do bundle, 4 routers falham a carregar com ValueError "JWT_SECRET_KEY or WATCHERDB_JWT_SECRET must be set in production environment": Security Analysis, Windows Metrics, Alerts Unified e Admin Metrics. O servico arranca na mesma e gera chave efemera (tokens nao sobrevivem a restart). Nem o install.ps1 nem o MSI geram este segredo. Nada na UI diz ao utilizador que essas areas do produto nao existem.
- **Recommendation:** gerar na instalacao e guardar em ProgramData/secrets (e' para isso que existe), ou pedir no dialogo de primeira configuracao. Enquanto nao houver, o portal devia dizer que a area esta indisponivel por configuracao em falta em vez de a esconder.
- **Status:** open
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-110 -- Default de BD aponta para o nosso TST em maquina de cliente

- **Severity:** P1
- **Category:** privacy
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** arranque no bundle em SQLHDSPRD213: "IntelligenceConnectionPool initialized (server=SQLHDSTST505\I01, db=WatcherDB_Intelligence)" com WINDOWS_AUTH=True. Confirmado a correr com a conta de servico do cliente a tentar alcancar a instancia de testes do vendor.
- **Recommendation:** sem default de servidor; o instalador tem de perguntar a instancia. Ate' la', falhar explicito em vez de tentar ligar a um host do vendor.
- **Status:** open
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-111 -- SERVIDORES (0) com sessao valida: corrida de arranque e interceptor que apaga token

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-frontend-specialist
- **Evidence:** loadServers() (portal :5812, chamado por init() :5582 via DOMContentLoaded :46774) e' a PRIMEIRA chamada /api/* do ciclo de vida e nao coordena com checkAuthOnLoad() (DOMContentLoaded separado, :4964), logo apanha 401 em arranque a frio. Os 4 endpoints que devolvem 200 vem depois, de renderDashboardCards(). O caminho de restauro de sessao nunca re-chamava loadServers() (o de login manual ja' tinha guard). Colateral mais grave: o interceptor global (:4638) faz clearAuthData() e showLoginOverlay() em QUALQUER 401 /api/*, sem distinguir "sem sessao" de "falha transitoria" -- pode apagar um token valido. O 401 do middleware devolve detail sem success/error, caindo sempre em "Erro desconhecido".
- **Recommendation:** tratar 401 pre-sessao como estado normal em loadServers; re-chamar loadServers no restauro de sessao; rever o interceptor para nao limpar sessao em 401 transitorio.
- **Status:** FIXED PARCIAL 2026-08-12 (os 2 diffs de loadServers e checkAuthOnLoad aplicados). ABERTO: o interceptor global continua a limpar sessao em qualquer 401 -- precisa de decisao conjunta com o v33-specialist (auth_service + AuthEnforcementMiddleware).
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-112 -- BD: coluna local_password_hash ausente (auth em modo legacy, ruido por pedido)

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** service_stderr.log repete, em CADA pedido autenticado: "Invalid column name 'local_password_hash'" seguido de "caindo para schema legacy. Run database/12_ADD_LOCAL_PASSWORD_HASH.sql para activar dual auth". Dezenas de ocorrencias por minuto.
- **Recommendation:** correr 12_ADD_LOCAL_PASSWORD_HASH.sql na WatcherDB_Intelligence (DDL, portanto owner) e propagar ao canonical INSTALACAO_COMPLETA_UNIFICADA.sql no mesmo lote.
- **Status:** open (DDL pendente do owner)
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-113 -- BD: coluna Env ausente em KPI_MSSQL_MIRRORING_STATUS_ACTIVE

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** a query do dashboard agrupa por CASE WHEN Env IN (...) sobre dbo.KPI_MSSQL_MIRRORING_STATUS_ACTIVE e o SQL Server recusa com "Invalid column name 'Env'" (14 vezes por execucao). Presente tambem no log das 15:02, portanto nao e' regressao de hoje.
- **Recommendation:** decidir com o v1-intel-specialist se a coluna entra na view ou se a query passa a fazer JOIN a INST_ENVS (padrao ja' usado noutras modais desde o censo de 11/08).
- **Status:** open
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-114 -- Traceback do arranque perde-se exactamente quando ha problema de permissoes

- **Severity:** P2
- **Category:** reliability
- **Owner specialist:** watcherdb-deploy-architect
- **Evidence:** watcherdb_service.py:231 faz traceback.print_exc() para service_stderr.log e :234 manda apenas repr(exc) para o Event Log. A abertura desses ficheiros (:138-144) esta dentro de try/except OSError: pass -- e' a PRIMEIRA coisa a falhar quando a conta nao tem ACL. Resultado real: Event Log com "erro fatal no servidor: PermissionError(13, Access is denied)" e zero contexto, enquanto o ficheiro que teria o traceback ficou parado nas 15:02.
- **Recommendation:** mandar traceback.format_exc() para o LogErrorMsg -- o Event Log nao depende de ACL de ficheiro.
- **Status:** open
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-115 -- Heranca da ACL de ProgramData voltou: BUILTIN\Users le a pasta de dados

- **Severity:** P2
- **Category:** security
- **Owner specialist:** watcherdb-security-auditor
- **Evidence:** icacls C:\ProgramData\WatcherDB mostra agora entradas herdadas (I), incluindo BUILTIN\Users:(I)(OI)(CI)(RX) e Users com WD/AD/WEA/WA. A auditoria 2026-04-22 removeu deliberadamente o acesso de Users porque a pasta guarda license.dat e config com credenciais parciais. Uma leitura anterior no mesmo dia mostrava apenas 3 entradas sem heranca -- voltou durante a reinstalacao.
- **Recommendation:** confirmar se o MSI reaplica LockPermissions numa pasta ja' existente; se nao, icacls /inheritance:r no fluxo de instalacao ou passo documentado.
- **Status:** open
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260812-116 -- Duas funcoes irmas com o mesmo perfil de risco BCC por testar

- **Severity:** P2
- **Category:** coverage
- **Owner specialist:** python-packaging-architect
- **Evidence:** api/routers/queries/_diagnostics_legacy.py::diagnose_slow_query (1286 linhas, segunda maior funcao de api/) e api/routers/alwayson.py:757 (uso de locals() dentro de get_instance_by_ag_name) partilham o perfil que disparou o FIND-20260812-108. Nenhuma foi testada com o harness de reproducao.
- **Recommendation:** correr o mesmo harness antes do proximo release candidate. Se diagnose_slow_query tambem falhar, o gatilho e' tamanho de funcao e a mitigacao passa de tactica (denylist) a estrutural (refactor sistematico).
- **Status:** open
- **Created:** 2026-08-12
- **Updated:** 2026-08-12

---

## FIND-20260813-101 -- KPI_MSSQL_DATAFILES_STG ausente de KPI_STG_ACTIVE_TABLE no canonical (registo so existe fora-de-banda na BD viva)

- **Severity:** P1
- **Category:** data-integrity
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** achado do gate v1-intel na Fase 1.5 dos thresholds (2026-08-13): o collector collect_datafiles.py usa BaseCollector.store() generico (escreve _BLUE/_GREEN + usp_swap_kpi_stg_tables), mas KPI_MSSQL_DATAFILES_STG NAO consta de @tables_to_register em KPI_STG_ACTIVE_TABLE nem das listas usp_create_stg_alias/usp_create_active_view no canonical (INSTALACAO_COMPLETA_UNIFICADA.sql:1936-1958; declarada como tabela fisica simples :10909-10933) — ao contrario das outras 14 familias blue/green. Owner verificou na BD viva (SSMS 2026-08-13): o registo EXISTE (PRD/QA/TST, slots GREEN, swaps frescos 10:16-10:18, 2931 servidores PRD) — drift fora-de-banda, mesma classe do GRANT da WDB_KPI_MUTE (FIND-20260804-102).
- **Impacto:** fresh install a partir do canonical parte o swap blue/green desta familia (usp_swap RAISERROR "nao encontrado em KPI_STG_ACTIVE_TABLE", store() devolve False) — o ramo UNLIMITED disk-bound de filegroups (agora com threshold configuravel filegroup_unlimited_free_gb) ficaria sem dados frescos em cliente novo. Junta-se a familia FIND-20260805-109/110 (fresh install gaps).
- **Recommendation:** sincronizar o canonical (registar DATAFILES_STG em @tables_to_register + listas das procs de alias/view) no lote fresh-install do FIND-109/110; lado V1, veto v1-intel.
- **Status:** open
- **Created:** 2026-08-13
- **Updated:** 2026-08-13

---

## FIND-20260813-103 -- Blocos script sem nonce mortos pelo CSP estrito: Collectors/Mutes sem clique, help do Performance e anti-FOUC do tema

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-frontend-specialist (+ watcherdb-security-auditor, politica CSP)
- **Evidence:** owner reportou 13/08 "clicar em Collectors e em Mutes, nada acontece". Causa: 3 blocos `<script>` SEM nonce em templates/watcherdb_portal.html (linha 6 anti-FOUC tema; ~52351 PERF_HELP; ~53302 openCollectorsModal/openKpiMuteModal). Desde o lote CSP de 12/08 (server.py deixou de empilhar o middleware permissivo), o DEV serve a politica estrita `script-src 'self' 'nonce-…'` — blocos sem nonce sao bloqueados por inteiro, as funcoes nunca sao definidas e o onclick morre em ReferenceError silencioso (script-src-attr 'unsafe-inline' deixa o atributo correr, dai "nada acontece" sem alert). O 4o candidato (45808) e' falso positivo (string JS p/ janela de impressao).
- **Impacto:** admin sem acesso a Collector Health e KPI Mutes no dev/bundle; textos de ajuda "?" do Performance mudos; flash de tema no arranque. Mesma classe do incidente do bundle 12/08 — dev nunca percorria o caminho real do CSP ate ao lote.
- **Recommendation:** APLICADO 13/08 — nonce="{{ csp_nonce }}" nos 3 blocos. FOLLOW-UP: (a) V6 tem o mesmo padrao (analytics_dashboard.html 4 blocos sem atributos, space_dashboard.html 1 — verificado 13/08, incluido no handoff F15); (b) gate de release: grep por `<script>` sem nonce em todos os templates antes de fechar bundle.
- **Addendum 2026-08-14 (2a metade da mina):** o browser test do owner revelou a modal Collectors ABERTA mas SEM ESTILO — o CSP bloqueia `<style>` sem nonce tal como `<script>`. 9 blocos `<style>` sem nonce corrigidos: 2 page-level MORTOS (Performance module ~52261 — a tab Performance inteira estava sem CSS! — e collectors ~53209), 2 injectados via innerHTML (skeleton 6922, tempdb 42653), 4 em documentos popup/Blob que herdam o CSP do opener (relatorios jobs/tempdb/sqldiag + print) e o `<script>` da janela de impressao. Nonce do Jinja resolve todos (substituido no render, valido tambem em popups/blob por heranca de CSP). Gate de release deve cobrir `<style>` alem de `<script>`.
- **Status:** fixed no V3.3 (pendente browser test da 2a ronda); V6 open
- **Created:** 2026-08-13
- **Updated:** 2026-08-14

---

## FIND-20260813-102 -- Superficies do portal citam thresholds de filegroups hardcoded que a Fase 1.5 tornou configuraveis

- **Severity:** P2
- **Category:** ux
- **Owner specialist:** watcherdb-frontend-specialist
- **Evidence:** sweep do challenger no painel Fase 1.5 (2026-08-13): textos de ajuda do portal (~templates/watcherdb_portal.html:17929/17937 "< 2% Livre", "2-5% Livre"), strings i18n nos 3 locales (:38774-38842 "Percent_Used >= 98%", "95% <= ... < 98%"), labels/subtitulos de modais (:24481, :51694, :24236-24238) e classificacao JS client-side (:16451-16460 getEffectiveFreePercent < 2 / >= 2 && < 5; :24203-24212 fallback; :14959-14968 Space Health >= 95/>= 90 — este JA contradiz a regra oficial hoje). Com override do cliente (Fase 1.5, commit 091557a), o numero do card muda mas os textos ao lado continuam a citar os defaults antigos.
- **Recommendation:** wave de paridade de superficies: cada citacao hardcoded passa a dinamica (bootstrap /api/v1/kpi-thresholds + placeholder i18n) ou entra em lista de excepcoes justificada (candidato: modulo Space per-server se o owner o declarar modulo a parte). Minimo: help texts + i18n dos filtros.
- **Status:** open
- **Created:** 2026-08-13
- **Updated:** 2026-08-13

---

## FIND-20260817-101 -- Modulo Jobs a ZEROS desde 16/04: response_model + handler de ResponseValidationError engoliam o payload (FIXED nesta wave)

- **Severity:** P0
- **Category:** reliability
- **Owner specialist:** watcherdb-v33-specialist
- **Evidence:** stderr do servico 2026-08-17 09:41:07: "Jobs analysis completed for CAGENPRD06_I06: 11 total, 1 failed" seguido de "ResponseValidationError on /api/jobs/server/CAGENPRD06_I06 (response_model mismatch - ignored)" e HTTP 200. api/models.py:82 JobsAnalysisResponse exigia server_id sem extra=allow; services/web_service/server.py:183 devolvia 200 {success:true,warning} sem dados; /trends e /schedule-conflicts idem (faltava 'success'). 264 ocorrencias no log, 1a em 2026-04-16 (commit d1e645e). all_jobs vinha paginado mas o portal esperava array.
- **Impacto:** aba Jobs de TODAS as instancias a zeros 4 meses (Total Jobs 0, Analise de Manutencao NAO CONFIGURADO); aba Backup "Jobs de Backup Falhados" sempre 0 e "Colisoes de Schedule" sempre OK. Falhas de jobs de backup em PRD invisiveis. Owner apanhou no screenshot de 17/08.
- **Recommendation:** APLICADO (aguarda commit + Restart-Service): modelos com extra=allow + server_id/success opcionais; result com success/server_id; all_jobs array completo; handler devolve exc.body e loga ERROR com os campos (nunca mais zeros silenciosos); portal j.name->job_name. Follow-up: teste de contrato por endpoint com response_model (mock) para apanhar mismatch no CI.
- **Status:** fixed-pending-commit
- **Created:** 2026-08-17
- **Updated:** 2026-08-17

---

## FIND-20260817-102 -- KPI Backup Failed: filtro "unresolved" nunca dispara (Database NULL do V1) e Instance backslash vs underscore entre AGENT_JOBS_STG e EXEC_FAILURES

- **Severity:** P2
- **Category:** data-integrity
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** V1 collect_backup_failures.py:52 grava Database=NULL nas linhas sysjobhistory (fillna em :254); helpers.py:1440 e intelligence_kpis.py:1727 saltam a verificacao de recuperacao quando db_norm vazio -> semantica real do KPI = todas as falhas de job dos ultimos 7d (nao "nao recuperadas"), apesar do comentario Wave R+13. AGENT_JOBS_STG.Instance = @@SERVERNAME cru (collect_agent_jobs.py:51, sem BaseCollector.transform) vs EXEC_FAILURES underscore (base_collector.py:355-369).
- **Impacto:** KPI mostra falhas ja recuperadas; qualquer JOIN por Instance a AGENT_JOBS_STG sem normalizacao devolve NULL silenciosamente (a wave 17/08 normaliza no ON como mitigacao).
- **Recommendation:** V1 (handoff/veto): (a) preencher Database nas falhas sysjobhistory (parse do comando do step, como backup_gap_detector.py) para reactivar o "unresolved"; (b) alinhar AGENT_JOBS_STG.Instance ao padrao underscore ou documentar excepcao em intelligence_db_schema.md junto de FIND-20260506-001. Ate la, rotulos do KPI dizem a janela (feito 17/08).
- **Status:** open
- **Created:** 2026-08-17
- **Updated:** 2026-08-17

---

## FIND-20260817-103 -- Higiene menor apanhada na wave (nao bloqueante)

- **Severity:** P3
- **Category:** code-quality
- **Owner specialist:** watcherdb-frontend-specialist
- **Evidence:** (a) classify_backup_type por substring: DBA_CATALOG_BACKUP -> LOG (paridade KPI mantida, teste documenta); (b) api/connection_pool.py:672-700 comentario legado com nome de dominio do empregador (separacao de IP); (c) i18n key logs.loading em falta nos 3 locales (pre-existente); (d) testes de higiene TestLevel6 falham por artefactos build/dist, config/*.bak_2026* e logs na raiz (pre-existente); (e) escapeHtml em falta em allJobsRows/disabled/maintenance rows da aba Jobs (CORRIGIDO 17/08).
- **Recommendation:** limpar (b) e (c) num lote de higiene; (a) so se se aceitar mudar o classificador do KPI em conjunto (regex word-boundary + teste adversarial).
- **Status:** open
- **Created:** 2026-08-17
- **Updated:** 2026-08-17

---

## FIND-20260817-104 -- KPI "processos em alarme" (fila de CPU) estruturalmente a ZERO: collector grava status de SESSAO, view conta status de REQUEST

- **Severity:** P1
- **Category:** data-integrity
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** owner correu na BD viva (2026-08-17 16:08): KPI_MSSQL_PROCESSES_STG.Status = sleeping 4776 / running 204 / dormant 10 (zero 'runnable'/'suspended'); KPI_MSSQL_PROCESSES_AGG_VIEW.Runnable_Count = 0 em todas as instancias (top: SQLHDSPRD211_I01 615 sessoes). Causa: V1 scripts/collectors/collect_processes.py:33 grava `s.status` de sys.dm_exec_sessions (running/sleeping/dormant/preconnect); a view (V1 canonical :3536-3558) conta `p.Status = 'runnable'`/'suspended' — valores que so' existem em sys.dm_exec_requests.status. O backend V3.3 (helpers.py:1189-1207) usa raise_on_error=False -> zero silencioso.
- **Impacto:** KPI de pressao de CPU (fila RUNNABLE) nunca disparou desde que existe, em V3.3 e em qualquer tier que leia a mesma view; threshold processes_runnable (20/50) inutil. Bonus: canonical V3.3 (database/INSTALACAO_COMPLETA_UNIFICADA.sql:2944-2962) tem OUTRA definicao da view (Processes/State >=500/1000, sem Runnable_Count) — desactualizado face ao V1/BD viva.
- **Recommendation:** V1 (handoff em curso): QUERY do collector `s.status AS [Status]` -> `COALESCE(r.status, s.status) AS [Status]` (estado do request quando activo; senao da sessao). Sem DDL. Restart WatcherDBCollector. Verificar consumidores de Status (transform() do collector, DET_VIEW, modal). Sincronizar canonical V3.3 com a definicao V1 (5 surfaces). Rotulo do KPI ja' mudado para "Instancias c/ fila de CPU (runnable > N)" + help nos 3 idiomas (V3.3, 17/08).
- **Status:** FIXED 2026-08-17 (V1 commit 7635f7c, collector reiniciado; validado na BD viva 16:52 pelo owner: Status passou a incluir suspended=34/runnable=6, AGG_VIEW com Runnable_Count real por instancia — max 3, abaixo do threshold 20 = zero verdadeiro)
- **Created:** 2026-08-17
- **Updated:** 2026-08-17

---

## FIND-20260817-105 -- Canonical do V3.3 (database/INSTALACAO_COMPLETA_UNIFICADA.sql) congelado desde 22/04 e usado pelo fresh install (deploy/setup_database.ps1:122)

- **Severity:** P0 (bloqueante para 1o cliente se setup_database.ps1 for o caminho real de instalacao)
- **Category:** data-integrity
- **Owner specialist:** watcherdb-v1-intel-specialist + watcherdb-deploy-architect
- **Evidence:** achado do v1-intel no parecer FIND-104: WATCHERDB_V3.3/database/INSTALACAO_COMPLETA_UNIFICADA.sql tem 10.053 linhas (snapshot 22/04) vs canonical V1 de 13/08 (Seccao 10 _ACTIVE/Wave C, 19 resiliencia rede, 20 manutencao, baseline engine, WDB_KPI_MUTE, WDB_KPI_THRESHOLDS...). Exemplo concreto: KPI_MSSQL_PROCESSES_AGG_VIEW no V3.3 (:2944-2962) nao tem Runnable_Count; o backend V3.3 faz WHERE Runnable_Count > N -> "Invalid column name" mascarado por raise_on_error=False. A wave de reconciliacao 2026-08-10 sincronizou V1 e V6, NAO esta copia. deploy/setup_database.ps1:122 executa-a num fresh install.
- **Impacto:** cliente novo instalado por este script herda schema de Abril: KPIs a "sem dados" (processes), swap blue/green incompleto, tabelas de mute/thresholds ausentes (ja apanhado em incidentes anteriores).
- **Recommendation:** wave dedicada "reconciliacao canonical V3.3 <-> V1" antes do proximo onboarding: decidir se V3.3 mantem copia (sincronizada por script) ou aponta para o canonical V1 (single source); ate la, setup_database.ps1 deve usar o canonical V1. Registar em PLANO_WAVE_FRESH_INSTALL_REPAIR (ja existente, 2026-08-05).
- **Status:** open
- **Created:** 2026-08-17
- **Updated:** 2026-08-17

---

## FIND-20260818-101 -- Filtro por ambiente do dashboard KPIs: 6 cartoes ignoravam o filtro (by_env em falta / nome errado / n() em vez de ev())

- **Severity:** P2
- **Category:** correctness
- **Owner specialist:** watcherdb-v33-specialist (validado)
- **Evidence:** owner 2026-08-18: ao filtrar por ambiente, varios cartoes nao mudavam o valor. Causa: evN/ev(sec,field) (portal ~35201/35325) deriva X_count->X_by_env e cai SILENCIOSAMENTE para o total quando a chave nao existe. Auditoria (v33 confirmou os 21 _advRow): (a) backend so' tinha failed_by_env combinado, nao full/diff/other_failed_by_env; (b) filegroups/servicos/mirroring tinham o breakdown com OUTRO nome (critical_filegroups_by_env, by_env); (c) integridade P3/P4 usavam n(ig.pX_count) directo (backend ja tinha p3_by_env/p4_by_env desde 04/08 -- regressao de propagacao).
- **Impacto:** numero de monitorizacao errado sob filtro (mostra frota inteira quando o utilizador pediu 1 ambiente) -- classe grave num produto de monitorizacao.
- **Recommendation:** APLICADO. Backend (helpers.py, NAO partilhado com V5/V6): +full/diff/other_failed_by_env (acumulados no loop com env_key normalizado), aliases down_by_env/unhealthy_by_env/critical_items_total_by_env/warning_items_total_by_env. Frontend: integridade P3/P4 ev() em vez de n(); discos com cor condicional (proactive finding). Teste de contrato tests/unit/test_kpi_env_breakdown_20260818.py: todo ev() tem fonte no backend. Tambem: sincronizacao cards<->modais do filtro (kpiAdvToggleEnv -> window._kpiEnvFilter) e modal a aceitar multiplos ambientes (2026-08-18, mesmo lote). unmeasurable_by_env fica como gap documentado (card ja e' N/D honesto).
- **Status:** fixed-pending-commit
- **Created:** 2026-08-18
- **Updated:** 2026-08-18

---

## FIND-20260831-101 -- delayed_critical conta (Instance,Database,TIPO) -- sem dedupe por base no numero executivo

- **Status-update 2026-09-01:** FIXED-PENDING-VALIDATION — council R1 implementado (dedupe por base em backup_delayed_classes.py, executivo conta bases; detalhe por tipo preservado no modal). Valida no cutover.
- **Severity:** P2
- **Category:** opportunity
- **Owner specialist:** watcherdb-v33-specialist (+ challenger na decisao)
- **Evidence:** api/routers/intelligence/helpers.py:1751-1823 (classificacao por tipo, sem dedupe); painel Por Categoria soma delayed_critical_count (~353 em 31/08) via KPI_REPORT_GROUPS portal ~:34757
- **Recommendation:** Rever base de contagem (uma base com FULL+DIFF+LOG parados conta 3 criticos no Resumo Executivo); precedente Wave R+11.2 diz dedupe entity-pair primeiro, MAS mudar a base muda o numero executivo -- decidir com specialists/council em sessao propria, nao misturar com o fix de coerencia do tile (aplicado 2026-08-31).
- **Status:** open
- **Created:** 2026-08-31
- **Updated:** 2026-08-31

---

## FIND-20260831-102 -- Porta aprendida aponta ao vizinho: dados em dobro + 2 instancias sem monitorizacao silenciosa

- **Severity:** P1
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist
- **Evidence:** WDB_INSTANCE_TCP_PORT: SQLHDSQLT103_SQLIJSQLT03=55411 (real via SQL Browser: 50245; 55411 e' do I01) e SQLHDSQLT105_I03=62086 (real: 50245; 62086 e' do I07). Efeito: DB_AVAILABILITY com 14 rows/7 dbs no I01 e 10/5 no I07 (todas as KPIs por-DB desses hosts em dobro, ex. modal Backup Delayed com TDH_MDS 5x); SQLIJSQLT03 e I03 SEM monitorizacao real (os "dados deles" sao copia do vizinho). Auto-heal nao dispara: porta errada LIGA com sucesso (instancia errada) -- so re-aprende em falha.
- **Recommendation:** (1) corrigir as 2 rows do WDB_INSTANCE_TCP_PORT (owner, UPDATE); (2) defesa estrutural no collector: pos-connect assert SERVERPROPERTY('InstanceName') == instancia esperada, mismatch -> descartar+re-aprender+alertar (mata a classe inteira: porta stale, DNS, alias); familia FIND-20260507-001 (gap silencioso por porta dinamica).
- **Status:** open
- **Created:** 2026-08-31
- **Updated:** 2026-08-31

---

## FIND-20260831-103 -- DIFF delayed com FULL mais recente = ruido de chain-reset (69% dos DIFF criticos)

- **Status-update 2026-09-01:** FIXED-PENDING-VALIDATION — council R2/R3/R4 implementados (perdao limitado f15bfb8 + banda DIFF-parado + rota ag_system_gap com contador; fosseis absorvidos pelo dedupe, sem cap). Valida no cutover.
- **Severity:** P2
- **Category:** opportunity
- **Owner specialist:** watcherdb-v33-specialist (+ sql-deep-reviewer na semantica de restore)
- **Evidence:** vw_KPI_MSSQL_BACKUPS_AG_EFFECTIVE 31/08: 225 DIFF (type I) com Hours_Since_Backup > 30; 156 (69%) tem FULL (type D) com Last_Backup_Date POSTERIOR ao DIFF -- a chain recomecou e um DIFF anterior ao ultimo FULL e' inutil para restore (ex.: TAON DIFF 17/06 vs FULL 18/06). Investigacao veio de pergunta do owner sobre "delayed antigo com backup mais recente" (caso LOG dele estava correcto; o padrao real e' no DIFF).
- **Censo completo 31/08 (auditoria aos 387 delayed, warn+crit):** plumbing SAO (SIMPLE+LOG=0; State nao-ONLINE=0; mirroring=0; duplicados=0 pos-fix portas). Classes de ruido/degrade: (1) chain-reset DIFF = 157 (70% dos DIFF, ~40% do painel inteiro); (2) fosseis >60d sem o tipo = 21 (12 D + 4 I + 5 L; estrategia abandonou o tipo mas a historia do msdb mantem a expectativa -- ex. TAON, SQLHDSTST023 parado desde 30/06); (3) system DBs = 105/387 (27%): master/model/msdb com expectativas de DIFF (42) e LOG (14; ex. model em FULL recovery com log backup unico antigo -> delayed perpetuo de 1803h -- e' config smell REAL do servidor, mas o sitio dele talvez seja um KPI de config e nao o Delayed). So o filtro chain-reset baixaria o painel 387->230.
- **Corte do owner 01/09 (medido):** a hipotese "secundarias de AG a contar" foi DESMENTIDA para bases de AG (vw_AG_EFFECTIVE consolida bem: 131 linhas AG_CONSOLIDATED, mapeamento 100%, MAX entre nos) -- mas o sintoma e' real por OUTRA via: 103 das linhas delayed vivem em NOS de AG e sao as bases LOCAIS deles (9 distintas: model 36, msdb 25, DBA_RESOURCE_DB 23, master 10, restos 9) -- a estrategia de backup desses clusters cobre o AG via primaria e deixou as system DBs por-no sem rotina. NAO e' bug do produto: e' exposicao real por-no (failover deixa msdb/master do promovido sem backup) OU politica aceite -- decisao de council. Praticamente todo o cohort "system DBs" do item (3) e' este caso.
- **Recommendation:** Filtrar (ou reclassificar como aviso informativo) DIFF delayed quando existe FULL mais recente que o DIFF na mesma base. NAO aplica a LOG (chain de logs nao e' reposta pelo FULL) nem a FULL. Muda contagens do painel (~-156 criticos) -> decidir com specialists antes (mesma cautela do FIND-20260831-101, que ja cobre a granularidade por tipo; os dois podem fechar na mesma wave de signal-vs-noise do Backup Delayed).
- **Status:** open
- **Created:** 2026-08-31
- **Updated:** 2026-08-31

---

## FIND-20260831-104 -- Colheita do script MirrorRebuild Fase 0 (owner): 2 ideias de produto + runbook

- **Severity:** P2
- **Category:** opportunity
- **Owner specialist:** watcherdb-v33-specialist + watcherdb-v1-intel-specialist (cross-KPI) + core-librarian (ingestao)
- **Evidence:** Script T-SQL do owner (docs/context/SCRIPT_MIRROR_REBUILD_FASE0_2026-08-31.sql) - deteccao de mirrors SUSPENDED/DISCONNECTED com tabela de controle em msdb, analise de t-log (VLFs, historico de log backups, alvo 2x maior backup 30d), survey de shrink por drive, veredito RESUME-vs-REBUILD (fila > dados = REBUILD). VALIDADO ao vivo no incidente SharePoint: fila 101 GB vs dados 6,8 GB -> REBUILD (heuristica do script corrigiu a minha sugestao anterior de RESUME).
- **Recommendation:** (1) Veredito RESUME-vs-REBUILD no modal mirroring V3.3 - cross-KPI puro (fila ja recolhida hoje + Size_MB do DATAFILES), zero recolha nova, accionavel; (2) survey "t-log sobredimensionado" como Smart Defaults candidate (alvo 2x maior log backup 30d, piso 512MB; potencial por drive) - liga ao episodio t-logs 98-99% e ao Disk Space; tier a validar. O PACOTE em si (fases 1-6, escreve em msdb dos monitorizados) fica na pista de OPERADOR (runbook KB via core-librarian 5 gates), nunca no collector (sql_monitoring SELECT-only, Regra de Ouro #2). Notas tecnicas p/ produto: DBCC LOGINFO exige privilegios altos (usar sys.dm_db_log_info 2016+ com version-gate; frota tem 2005+).
- **Status:** open
- **Created:** 2026-08-31
- **Updated:** 2026-08-31

---

## FIND-20260901-101 -- Tokenizacao F4 incompleta: 4+ severity-ladders hardcoded sobrevivem porque o smoke so faz match de string exacta

- **Severity:** P2
- **Category:** reliability
- **Owner specialist:** watcherdb-frontend-specialist
- **Evidence:** Apanhado na consulta do fix da ladder :42976 (2026-09-01). O smoke test_no_severity_ladders_remain so procura a string exacta "=== 'CRITICAL' ? '#ef4444'"; formatos distintos passam: templates/watcherdb_portal.html:19218-19221 (if/else-if pressureColor), :25304-25310 (object map alertLevelColors com bg/border/text/icon), :47305-47313 (if/else-if em .style.color/.style.borderLeftColor), :51744 (ternario com hex diferentes #f87171/#fbbf24/#4ade80), :39019 e :38368/38474/38573 (hex de fundo misturados com sevColor tokenizado), :39310-40740 (array level/color de legenda -- menor prioridade, nao e' pintura runtime).
- **Recommendation:** (1) reforcar o smoke para regex generica (ex.: ===\s*'CRITICAL'[^;]{0,40}#[0-9a-fA-F]{3,6}); (2) mini-wave para tokenizar os 4+ sites runtime antes de declarar F4 realmente completo; high-contrast/dark dependem disto.
- **Status:** open
- **Created:** 2026-09-01
- **Updated:** 2026-09-01

---

## FIND-20260901-101 -- collect_backups sem filtro is_copy_only: FULL copy-only mascara schedule morto e concede perdao indevido

- **Severity:** P2
- **Category:** reliability
- **Owner specialist:** watcherdb-v1-intel-specialist (infra partilhada — veto dele)
- **Evidence:** Gate sql-deep-reviewer 01/09 (wave Delayed signal): grep completo ao repo V1 = ZERO ocorrencias de is_copy_only/is_snapshot. Um FULL copy-only (refresh DEV, snapshot VSS) entra na STG como FULL normal: (i) mantem o FULL "fresco" mascarando um schedule de FULL real morto — pre-existente a esta wave; (ii) com o perdao R2 novo, passa tambem a perdoar o DIFF (rigorosamente, copy-only NAO reinicia a base diferencial).
- **Recommendation:** filtrar is_copy_only = 0 (e avaliar is_snapshot) em collect_backups no V1 — mudanca de collector partilhado, wave propria com consulta ao v1-intel; nao bloqueia a wave Delayed (o buraco e' a montante e ja existia).
- **Status:** open
- **Created:** 2026-09-01
- **Updated:** 2026-09-01
