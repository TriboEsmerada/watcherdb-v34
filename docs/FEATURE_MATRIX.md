# FEATURE_MATRIX — WatcherDB V3.3 Standard Edition (STUB)

**Status:** STUB — preencher com decisões de produto. Bootstrapped 2026-04-28
durante council bootstrap (Fase 2). Específico desta cópia local; ground truth
canónico cross-tier vive em `~/.nestor-library/watcherdb-family/feature_matrix.md`
(quando ingerido pelo `core-librarian`).

**Owner:** `watcherdb-v33-specialist` + `watcherdb-customer-success-persona`
**Reviewers:** todos os specialists

---

## 1. Propósito

Documento canónico que decide se uma feature é:

- **Std** — entra em V3.3 Standard Edition
- **Pro** — exclusiva V5/V5.5/V6 (out-of-scope deste projecto)
- **Std + Pro** — feature core partilhada entre tiers (com paridade ou variantes)

Specialists do council **citam este documento** em decisões de tiering.
Sem entrada explícita aqui = decisão escala ao DBA Lead / Customer Success.

## 2. Tier Decision Framework (4 perguntas)

Para qualquer feature nova:

1. **Core monitoring ou AI/advanced?**
   - Core monitoring (KPI base, dashboards visuais, alerting básico) → Std + Pro
   - AI/ML / advanced analytics → Pro-only

2. **Custo operacional significativo (GPU, models, vectors, LLM local)?**
   - Sim → Pro-only (preserva margem operacional Std)
   - Não → potencialmente ambos

3. **Valor marketing diferenciador (upsell driver)?**
   - Alto → Pro (protege pricing)
   - Baixo → Std + Pro

4. **Complexidade de manter em 2 editions?**
   - Alta → Pro-only (evita custo dual-team)
   - Baixa → Std + Pro

**Resposta consolidada:**

- 4× Std → Std-only
- 4× Pro → Pro-only
- Mix → escala ao DBA Lead

## 3. Features Std (presentes em V3.3) — STUB list

> **TODO:** preencher com lista canónica. Para já, lista derivada do código actual
> e KB seed `kpi_catalog_v33.md`.

### Core monitoring KPIs (cards do dashboard)

- Instance Availability
- DB Availability
- AlwaysOn Status (basic)
- Mirroring Status (DB Mirroring legado: state/safety/witness/filas + drill de
  diagnóstico com triagem determinística RESUME/REBUILD — heurística fila vs
  dados, não-AI; série 7d de filas p/ tendência. Waves 2026-08-31/09-01)
- Blocked Sessions / Blocked Users
- Long Locks
- Deadlocks (com pre-flight source check `step_6_source`)
- DB IO Stats
- Processes Alarm
- CPU Critical (≥ 95% sustentado)
- Memory Critical (≥ 99% com page faults)
- DB Disk File System
- Filegroup Usage
- DB Transaction Logs (TLOG usage; modal por base com último backup de log — 2026-09-02)
- Backup Status (schedule-based gap detection)
- Service Status
- Jobs Agent (basic)

### Performance Module

- 8 investigators (deadlocks, blocking, IO, CPU, memory, etc.)
- Engines: correlator, baseline, runbook, ticket_generator (ticket draft simples)
- Runbooks (8 markdown ready-to-use)

### Auth & RBAC

- AD/LDAP authentication (LDAPS default)
- Multi-domain LDAP (Patch D, commit `691a529`)
- JWT tokens (HS256, 8h + refresh 7d)
- `_require_admin` decorator (RBAC gate)
- Hybrid auth (AD + local DB fallback)

### Deploy & Operations

- Windows Service (porta 8433)
- TLS directo no servico (opcional via `.env` `WATCHERDB_TLS_CERT/KEY`; HSTS so' sobre https)
- `GET /api/version` (identidade do build: VERSION.txt / git sha) e `GET /healthz`
- Hardware fingerprint license enforcement (Ed25519)
- PyArmor Pro obfuscation (reg 11618)
- DPAPI / Fernet+DPAPI secrets
- `WatcherDB_Intelligence` BD partilhada (V1 collector upstream)
- DDL idempotente em `scripts/sql/performance_module_schema.sql`

### UX & i18n

- SPA `watcherdb_portal.html` (vanilla JS, Chart.js)
- Modal system com `data-admin-gated`
- PT (default), EN, ES — 3 línguas distintas (Portuguese, English, Spanish). Ground truth: `static/js/watcherdb_i18n_v2.js` SUPPORTED_LANGS. Ficheiros: `static/i18n/{pt,en,es}.json`.

### Thresholds configuráveis (Fase 1 — global-only)

- Registry central `api/kpi_thresholds_registry.py` (15 entradas, 13 configuráveis
  desde F1.5 2026-08-13) — fonte única para
  as camadas Python. KPIs cujo threshold vive em view SQL ou colector V1 ficam
  como espelho informativo (`configurable_f1: False`), NÃO editáveis.
- Override GLOBAL por KPI: tabela `dbo.WDB_KPI_THRESHOLDS` (`Scope_Type` sempre
  `'GLOBAL'` no build Std), CRUD admin-only em `api/routers/kpi_thresholds.py`,
  ecrã "Thresholds em vigor" nas Configurações. DDL:
  `WATCHERDB INTELLIGENCE V1/database/CREATE_WDB_KPI_THRESHOLDS.sql` (repo V1 —
  o schema partilhado pertence ao V1).
- Resolução com fallback total em `api/threshold_overrides.py` — tabela ausente,
  vazia ou em erro ⇒ defaults do registry (comportamento idêntico à Fase 0).
- Lista fechada: só entra em `configurable_f1` quem tem `source: 'backend'`.

#### 3.1 KPIs configuráveis (Std, âmbito GLOBAL)

Lista canónica = entradas de `api/kpi_thresholds_registry.py` com
`configurable_f1: True`. Não repetir os valores aqui — duplicá-los é exactamente
o drift que a Fase 0 existe para matar.

#### 3.2 Gate de entrada em configurable_f1

Nenhum KPI migra de espelho (`configurable_f1: False`) para configurável antes de:

  a. Capturar a definição viva via `sys.sql_modules` e substituir a definição no
     canonical pela real, no MESMO commit da mudança de tier.
  b. Teste anti-drift automático que compara colunas e CASE do canonical com a
     BD viva e falha o CI se divergirem.
  c. Smoke test de fresh install que prova que as colunas de que o Python depende
     (`State`, `Severity`, `Runnable_Count`, `Days_Since_CheckDB`, …) existem
     pós-instalação A PARTIR DO CANONICAL — não só na BD de produção já corrigida
     fora de banda.
  d. Paridade de superfícies: card, drill-down, textos de ajuda nas 3 línguas e
     módulo Performance concordam com o valor efectivo. Um controlo que muda o
     card mas não o modal é pior do que um controlo desactivado.

Justificação (auditoria do painel, 2026-08-04/05): existiam 6 valores concorrentes
para o transaction log e 4 para os deadlocks, e um fresh install a partir do
canonical produz 3 famílias de KPI vazias em silêncio. Sem estas 4 alíneas, cada
KPI novo configurável multiplica a inconsistência em vez de a conter.

## 4. Features Pro-only (NÃO entram em V3.3) — STUB list

> Lista derivada de comentários no código + `~/.claude/agents/watcherdb-v33-specialist.md`.

### 4.1 Features removidas do build V3.3 (Pro-only herdadas de V3.2 — cleanup 2026-05-05)

Estas features tinham código activo em V3.3 (herdado do fork file-system V3.2 → V3.3 sem cleanup) mas pertencem a tier Pro (V6+). Removidas do build V3.3 a 2026-05-05 após decisão DBA Lead "V3.3 = zero AI; só V6 tem AI" (ver memory `project_v33_zero_ai.md`).

| Feature | Decisão | Finding | Source mantido (paridade V6+) |
|---|---|---|---|
| DBA Copilot module (rule-based + LLM) | Pro-only | FIND-013-B | `api/routers/copilot.py`, registry entry comentada em `feature_registry.py:29` |
| Predictive Alerts (sklearn LinearRegression ML engine) | Pro-only | FIND-014-B | `modules/monitoring/predictive_alerts*.py`, 7 decorators `@app.get(...predictive-alerts*)` comentados em `watcherdb_intelligence.py` |
| sklearn dependency | Pro-only | FIND-014-B | Movida para `requirements-pro.txt` (não instalada em build V3.3) |

**Sweep recursiva pre-tag:** `v33-feature-matrix-checker` micro-agent corre antes de release com greps negativos:

```
ollama|rag_engine|knowledge_graph|qlora|shap|sklearn|copilot|predictive_alerts
```

Em V3.3 build paths esperado: **ZERO matches activos** (excepto comentários "removed — Pro-only" e source files com decorator comentado).



### AI/ML stack

- Ollama local LLM (codellama:7b, watcherdb-sql-v1 QLoRA-tuned)
- RAG engines (rag_engine, cognitive_rag, semantic_rag)
- Knowledge Graph (graph + vector hybrid)
- QLoRA training pipeline
- SHAP explainability
- 14 Expert Agents / Expert Swarm
- Autonomous Agent
- Cascade Intelligence
- Silent Degradation
- Incident Memory
- Shift Handover
- Anomaly Detection (ML-powered)
- Health Score Engine
- Capacity Planning
- SLA Calculator
- Insight Generator
- Recomendações AI
- Análise Causa Raiz AI
- Times / Newspaper

### Advanced analytics

- Risk Scores
- Latent Risk
- Executive Report
- Gravity Map
- Stress Test
- Instance Compare
- Baseline Compare advanced
- 2PC monitoring
- Cluster advanced

### Integrations

- SSIS Executions monitoring
- Tickets ITSM (avançado, non-trivial)
- Cloud monitoring

### UI premium

- Badges PRO, gradient, lock icons
- ~25 routers AI/ML experimentais

### Thresholds — âmbito e auditoria (Fase 2 / Fase 3)

- Override por ENV / INSTANCE / DATABASE com precedência
  (DATABASE > INSTANCE > ENV > GLOBAL > default). A camada de leitura em
  `api/threshold_overrides.py` já resolve estes âmbitos; falta a UI, que é Pro.
- Audit trail histórico das mudanças (quem, de quê, para quê, quando) —
  requisito banking que a Fase 1 não cobre. A tabela `WDB_KPI_THRESHOLDS_AUDIT`
  já existe no DDL; a escrita é Pro.
- Baseline engine a sugerir thresholds (Fase 3) — ver secção 5.
- Posicionamento: **Std — um limiar, toda a frota. Pro — um limiar por servidor,
  com histórico de auditoria.**

## 5. Features ambíguas (decisão pending)

> **TODO:** preencher quando casos surgem. Specialist sinaliza ao orquestrador
> que escala ao DBA Lead.

| Feature | Argumento Std | Argumento Pro | Decisão |
|---|---|---|---|
| Baseline engine a sugerir thresholds (Fase 3) | Roadmap original punha-o em S+1 (Std) | Analytics preditiva; alinha com Risk Scores / Latent Risk, já Pro | **NEEDS_DECISION — DBA Lead.** Bloqueado também por `collect_alwayson_status.py:52` (Commit_Diff_Secs hardcoded) |
| Thresholds por tier de drive (Sistema / TempDB-Log / Backup-Archive / Dados) | Subdivisão por tipo de recurso, não por âmbito organizacional; precedente `backup_delay_full/diff/log` já são 3 chaves Std | Granularidade que se aproxima de scoping | **PASS condicional** — 4 chaves flat no registry, sem UI dinâmica de escolha de drive |
| Tornar configuráveis os KPIs de camada de recolha (processos, t-log, deadlocks, CHECKDB) | Cobertura da mesma capacidade Std já aprovada | — | **Bloqueado pelo gate 3.2.** Deadlocks é o único candidato limpo (par simples, view já expõe `State` correcto) |

## 6. Anti-tier-creep checks

- **Proactive finding `tiering`** dispara se:
  - Código AI/ML detectado em V3.3 (módulo, router, dependency)
  - SPA mostra card / tab Pro-only
  - Texto "upgrade Pro" inline em UX (vs página dedicada commercial)
  - Endpoint AI experimental registado em `watcherdb_main.py` build Std
- **Sanity test:** `grep -ri "ollama\|rag_engine\|knowledge_graph\|qlora\|shap" V3.3/`
  → resultado deve ser zero (excepto comentários "removido — Pro-only")

## 7. Cross-product canon

Versão canónica cross-tier reside em `~/.nestor-library/watcherdb-family/feature_matrix.md`
(curated pelo `core-librarian` quando ingerido). Conflito **deste documento** vs canon
cross-tier:

- Para tier Std (V3.3) decisões: **este doc ganha**
- Para feature Pro classification: **canon cross-tier ganha**

## 8. Ciclo de vida da matriz

- **Update trigger:** feature nova proposta + após release tag (anotar features shipped)
- **Sign-off:** DBA Lead + Customer Success Persona (charter pode votar via bulletin)
- **Versioning:** este doc é append-only com revision history em footer

## 9. References

- `~/.claude/agents/watcherdb-v33-specialist.md` — cross-product version mantém lista canónica de Pro features (referência inicial)
- `knowledge_base/domain/seed/kpi_catalog_v33.md` — KPI catalog Std seed
- `docs/external/standard/PRODUCT_SHEET.md` — what we promise Std customers
- `docs/external/standard/PRICING_MODEL.md` — Std pricing tier
- `docs/PROACTIVE_COUNCIL.md` — gatilho 4 (feature ideation) usa este doc
- `docs/HANDOFF_CONTRACT.md` — formato brief para tier review

---

**Revision history:**

- v0.1 (2026-04-28) — STUB inicial (council bootstrap Fase 2). Listas Std e Pro
  derivadas do código actual + cross-product `watcherdb-v33-specialist` charter.
  Ambiguous list vazia. **Owner V33 specialist deve preencher revisão completa
  na Fase 4 do bootstrap.**
