# Latest Release V3.3 — annotated by council (seed)

Release notes da janela 2026-04-21 → 2026-04-28 (Patch A/B/C/D + UX fixes), anotadas
pelo council durante bootstrap.

**Status:** SEED — primeira release notes anotada.
**HEAD analisado:** `691a529` (Patch D multi-domain LDAP).

**Owner:** `watcherdb-v33-specialist`
**Reviewers:** `watcherdb-deploy-architect`, `watcherdb-security-auditor`,
`watcherdb-customer-success-persona`

---

## Highlights

- **Multi-domain LDAP authentication (Patch D)** — V3.3 passa a suportar
  múltiplos domínios AD em paralelo. Crítico para clientes banking com
  floresta multi-tenant (subsidiárias, M&A IT integration ainda em curso)
- **Auth pipeline hardening (Patches A/B/C)** — URI sanitize, silent-fail
  remediation, startup diagnostic
- **UX improvements** — modal click handler normalizado, "SQL Services Down"
  renomeado para "SQL Não Respondeu", default landing = KPIs

## Commits anotados

### `691a529` — feat(V3.3/auth): multi-domain LDAP authentication (Patch D)

**Specialist owner:** `watcherdb-v33-specialist`

**O que mudou:** `_authenticate_ldap` em `api/routers/auth_compat.py` agora
itera lista `AD_DOMAINS` em vez de usar singulares. Refactor extrai
`_try_single_domain_bind(username, password, dom_cfg, connect_timeout)` —
recebe config dict por domínio (keys: domain, server, base_dn, [use_ssl]).

**Multi-domain logic:**

1. Lê `AD_DOMAINS` (preferred) ou fallback aos singulares se lista vazia
2. Username com domínio explícito (`user@dom.fqdn` ou `DOM\user`) → filtra
   lista para apenas esse domínio (match por FQDN ou NetBIOS short)
3. Username sem domínio → tenta todos em ordem
4. `connect_timeout` por domínio reduz para 5s quando iterando múltiplos
   (vs 10s single) — total wait bounded mesmo com 4-5 domínios

**Adiciona:** campo `ad_domain` ao `user_info` devolvido (rastreio de qual
domínio autenticou).

**Council notes:**
- ✅ Mantém URI sanitization do Patch A
- ✅ Mantém SIMPLE→NTLM fallback
- ⚠️ `[PROACTIVE FINDING] reliability` (low): único smoke test foi mock — falta
  validação contra AD real do cliente em UAT (recomendação para `qa-specialist`)
- ⚠️ `[PROACTIVE FINDING] docs` (low): `WatcherDB_System_Config.ad_domains` JSON
  schema não está documentado em `KNOWLEDGE_BASE_GUIDE.md` — adicionar em release+1

### `7c95c53` — fix(V3.3/auth): AD URI sanitization + create_user silent-fail + startup diag

**Specialist owner:** `watcherdb-v33-specialist`, reviewed by `watcherdb-security-auditor`

**O que mudou:** três fixes empacotados:

- **Patch A (URI sanitize):** `ldap://` ou `ldaps://` prefix retirado se user
  pôr na config (causa re-prefix double); trailing `/` retirado
- **Patch B (silent-fail):** `create_user` no fluxo de first-time AD login
  estava a apanhar `IntegrityError` e devolver 200 sem criar — agora propaga
  500 com log estruturado
- **Patch C (startup diag):** logger.info no startup com binding test resultado
  + count de domains configurados

**Council notes:**
- ✅ Reduz superfície de bugs reportados por DBAs cliente (silent-fail era P1)
- ⚠️ Patch C diag pode logar info sensível (`server` FQDN cliente). Não logar
  username/password — verificar logs em `.nestor/bulletin/inbox.md` (post hipotético
  para `security-auditor`)

### `49a21c0` — fix(V3.3): modal click handler — normalize instance-name to backslash on emit

**Specialist owner:** `watcherdb-frontend-specialist`

**O que mudou:** modal click handler em `templates/watcherdb_portal.html` linha ~33850
normaliza `instance-name` ao emitir evento (estava com `_` em vez de `\` em alguns
fluxos, quebrando filtro server-side).

**Council notes:**
- ✅ Resolve bug user-visible (DBA cliente abria modal e não via dados)
- ✅ Alinhado com gotcha conhecido (normalização de instance — ver `kpi_catalog_v33.md`)

### `9e967c6` — fix(V3.3 SQL): reconcile via INST_AVAILABILITY (COLLECTION_SERVER_DETAILS estava vazia)

### `33c2fed` — fix(V3.3 SQL): SQL Nao Respondeu — reconciliation com COLLECTION_SERVER_DETAILS

### `7a9355a` — fix(V3.3 UX): silenciar 401 burst pre-login + renomear "SQL Services Down" -> "SQL Nao Respondeu"

**Specialist owners:** `watcherdb-v33-specialist` (SQL fix) +
`watcherdb-customer-success-persona` (UX rename)

**O que mudou:** stack de 3 fixes ao card "SQL Não Respondeu":

1. Reconcile fonte primária trocada para `INST_AVAILABILITY` quando
   `COLLECTION_SERVER_DETAILS` está vazia (race condition em arranque)
2. Reconciliation full pass com `COLLECTION_SERVER_DETAILS`
3. Card renomeado para "SQL Não Respondeu" — "Down" sugeria service stopped
   (técnico-incorreto), "Não Respondeu" cobre TCP timeout / firewall / overload

**Council notes:**
- ✅ Customer success ganhou: nome ressoa melhor com narrativa DBA (TCP unreachable)
- ✅ Side-effect positivo: 401 burst pré-login silenciado (UX cleanup)

### `a215e10` — fix(V3.3 service): load_dotenv com path explicito

**Specialist owner:** `watcherdb-deploy-architect`

**O que mudou:** Windows Service tinha `cwd != project root` quando arrancado
via SCM. `load_dotenv` sem path explícito não encontrava `.env`. Fix passa
path absoluto.

**Council notes:**
- ✅ Era bug recurring em customer deploys; agora deploy-resilient

### `0f76a01` — fix(V3.3): hardware fingerprint via PowerShell + default landing = KPIs

**Specialist owner:** `watcherdb-deploy-architect` + `watcherdb-frontend-specialist`

**O que mudou:** hardware fingerprint (license enforcement) via PowerShell em
vez de WMI (mais robusto em Windows Server hardened); default landing page
SPA agora KPIs (era login flat).

## Tier check (todas as mudanças)

| Commit | Std/Pro? | Validation |
|---|---|---|
| 691a529 | Std | Auth é core monitoring — Std + Pro |
| 7c95c53 | Std | Idem |
| 49a21c0 | Std | UI core — Std + Pro |
| 9e967c6 | Std | KPI core — Std + Pro |
| 33c2fed | Std | KPI core — Std + Pro |
| 7a9355a | Std | UX core — Std + Pro |
| a215e10 | Std | Service infra — Std + Pro |
| 0f76a01 | Std | Service infra — Std + Pro |

✅ **Zero leaks Pro→Std** detectados nesta janela.

## Council notes — proactive findings emitidos durante annotation

```
[PROACTIVE FINDING]: reliability | api/routers/auth_compat.py:340-410 | low —
  Patch D multi-domain validado apenas com mock em CI. Recomenda smoke test em
  staging cliente (UAT) com 2+ domains antes de release notes irem para clientes.
  Owner: watcherdb-qa-specialist.

[PROACTIVE FINDING]: docs | knowledge_base/operations/seed/deploy_runbook_v33.md | low —
  Schema JSON de WatcherDB_System_Config.ad_domains não documentado. Adicionar
  em release+1. Owner: core-librarian + watcherdb-deploy-architect.

[PROACTIVE FINDING]: tiering | docs/FEATURE_MATRIX.md | medium —
  FEATURE_MATRIX.md ainda é STUB no projecto V3.3 (preencher na Fase 2 do
  bootstrap). Specialists não podem validar tier checks rigorosamente até
  ficheiro estar completo.
  Owner: watcherdb-v33-specialist.
```

## Next release window

- Validar Patch D em UAT cliente real com 2+ domínios
- Preencher `docs/FEATURE_MATRIX.md` (Fase 2 council bootstrap)
- Cross-link incidents (vazio agora — KB local seed)

## References

- Commits: `691a529`, `7c95c53`, `49a21c0`, `9e967c6`, `33c2fed`, `7a9355a`,
  `a215e10`, `0f76a01`
- `findings-inbox.md` (raiz V3.3) — findings emitidos
- `docs/changelog/CHANGELOG.md` — changelog formal cliente-facing (próxima entrada)
