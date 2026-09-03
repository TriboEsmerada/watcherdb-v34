# ADR-001 — Council Composition for WatcherDB V3.3 (Nestor Bootstrap)

- **Status:** Accepted
- **Date:** 2026-04-28
- **Owner specialist:** core-council-architect (proposto), orquestrador (decidiu)
- **Stakeholders consulted:** user (DBA Lead), todos os charters cross-product em `~/.claude/agents/`

## Context

V3.3 Standard Edition é produção shipped a clientes pagantes (mid-market, banking-grade
em alguns casos). Antes deste ADR, o trabalho técnico em V3.3 era assistido por:

1. **User-level agents** em `~/.claude/agents/` — 15 agents cross-product, scope amplo,
   incluindo `watcherdb-v33-specialist` v1.3 cross-product. Eficaz mas:
   - Charters mencionam V5/V5.5/V6 (out-of-scope para foco V3.3)
   - Ground truth ambígua entre projectos
   - KB referenciada está em `watcherdb-council/docs/` (projecto-mãe), não local
2. **Orquestrador main session** carregando context inteiro

Risco de continuar sem council project-local:

- **Context bloat** — orquestrador acumula history multi-projecto
- **Tier creep** — specialist cross-product pode aceitar features Pro em V3.3 por inércia
- **Knowledge boundary unclear** — qual KB local? qual canon central?
- **Bootstrap não-portable** — outros projectos da família WatcherDB (V5, V5.5, V6,
  V1, AoLado, Polo) precisam reproduzir manualmente

Decisão: **adoptar Nestor Council project-local** seguindo template canónico do
projecto-mãe `watcherdb-council` + `nestor-template/`.

## Decision

Criar council project-local em `WATCHERDB_V3.3/.claude/agents/` com:

### Core archetypes (fixos em qualquer projecto Nestor)

1. `core-council-architect` — meta-agent, propõe ajustes ao council periodicamente
2. `core-librarian` — gere DUAS bibliotecas (LOCAL `knowledge_base/` + CENTRAL
   `~/.nestor-library/`); 5 governance gates obrigatórios; único agent V3.3 com Write

### Domain specialists (7 — específicos a V3.3)

3. `watcherdb-v33-specialist` — Senior Backend Eng + DBA Domain Expert + Std/Pro Tier Curator
4. `watcherdb-frontend-specialist` — Frontend Eng + UX Designer + A11y Auditor + Design System
5. `watcherdb-deploy-architect` — Release Eng + Windows Sysadmin + AD/Security + DBA + SRE
6. `watcherdb-qa-specialist` — QA Eng + Test Architect + Release Gate Keeper (pattern dois olhares)
7. `watcherdb-security-auditor` — CISO + AppSec + Compliance + Red Team mindset (com WebSearch)
8. `watcherdb-customer-success-persona` — DBA Lead + Support Eng + Customer Advocate
9. `watcherdb-v1-intel-specialist` — Collector Eng + DBA shared + SRE (**veto power** em infra partilhada)

### Cross-product (referenciados, NÃO duplicados)

- `ai-systems-architect` (~/.claude/agents/) — raro em V3.3 (Std sem AI)
- `python-packaging-architect` (~/.claude/agents/) — coordenação com `deploy-architect`

### Micro-agents (Fase 3 — 6 agents single-task; 7.º adicionado 2026-09-03)

- `v33-feature-matrix-checker`
- `v33-changelog-assistant`
- `v33-port-collision-checker`
- `v33-i18n-coverage`
- `v33-i18n-linguist` (2026-09-03 — qualidade de tradução; par do coverage. Charter: core-council-architect)
- `v33-modal-auth-gate-checker`
- `v33-knowledge-base-curator`

## Rationale

### Porquê 7 domain specialists (não 5, não 12)?

- **5 specialists bons > 12 medíocres** (princípio Nestor)
- 7 cobre os 7 quadrantes principais de V3.3:
  1. **Backend / DBA** (`v33-specialist`)
  2. **Frontend / UX** (`frontend-specialist`)
  3. **Deploy / Ops** (`deploy-architect`)
  4. **Quality / Tests** (`qa-specialist`)
  5. **Security / Compliance** (`security-auditor`)
  6. **Customer voice** (`customer-success-persona`)
  7. **Shared infra (V1)** (`v1-intel-specialist` — veto power)
- Adicionar mais (ex.: `marketing-strategist`, `ai-systems-architect` project-local)
  é over-engineering para V3.3 Std (Std não tem AI; marketing é cross-product no
  projecto-mãe)

### Porquê project-local em vez de só user-level?

| Argumento | Project-local | User-level |
|---|---|---|
| Scope explícito (V3.3 only) | ✅ | ❌ (cross-product) |
| Ground truth `docs/FEATURE_MATRIX.md` (deste repo) | ✅ | ❌ (referencia council mãe) |
| Knowledge sources locais (`knowledge_base/`) | ✅ | ❌ |
| Bootstrap reproduzível em outros projectos família | ✅ | ❌ |
| Override automático user-level (precedência cwd) | ✅ | n/a |

### Porquê dual-library (local + central)?

Ver ADR-002 (decisão separada com rationale completo).

### Porquê pattern "dois olhares" no QA specialist?

Lesson learned em sessões prévias (ver `MEMORY.md/feedback_qa_dual_lens.md`): testes
tech PASS frequentemente passam por user-FAIL (mock divergente de prod, fixture
fraca). Veredicto MIN(tech, user) força que tests captem também a perspectiva
do DBA cliente.

### Porquê veto power para `v1-intel-specialist`?

V1 BD partilhada (`WatcherDB_Intelligence`) alimenta V3.3 + tiers Pro. DDL change
"isolada" em V3.3 que afecta V1 quebra clientes Pro silenciosamente. Veto previne
data corruption multi-tier (precedente: FIND-20260423-001).

## Alternatives considered

| Opção | Pros | Cons | Rejeitada porque |
|---|---|---|---|
| **Apenas user-level** (status quo) | Zero setup | Tier creep, ground truth ambígua | Risco de regressão Std-Pro |
| **5 specialists (drop frontend + customer-success)** | Mais leve | Frontend é V3.3-specific (vanilla JS, SPA grande); customer-success captura voice DBA não cobierta por outros | Underrepresentation de UX/voice |
| **12 specialists (adicionar marketing-strategist, ai-architect, hacker-team, etc.)** | Cobertura ampla | Over-engineering; cross-product existem em ~/.claude/agents/ | Dispatch overhead injustificado |
| **Apenas core archetypes (council-architect + librarian)** | Minimalista | Domínio V3.3 não coberto | Insuficiente para projecto produção |
| **7 specialists project-local + cross-product reference** | Best of both | Specialists têm de saber regras de scoping | **Aceite** — regra simples |

## Consequences

### Positive

- Specialists com scope V3.3 explícito → maior precisão em pareceres
- Dual-library com regras de precedência → retrieval predictable
- Bootstrap reproduzível → V5/V5.5/V6/V1/AoLado/Polo podem aplicar mesmo template
- Ground truth (`docs/FEATURE_MATRIX.md`) consolidado neste repo → versionado com
  o code que ele rege
- Veto power V1 specialist → data integrity multi-tier protegida

### Negative / Trade-offs

- 7 specialists project-local + 6 micro-agents = 13 ficheiros novos em `.claude/agents/`
- Manutenção: charter updates requerem coordenação (mas micro mudanças, não diárias)
- Dispatch paralelo (Pattern #7) pode custar 100k+ tokens em session sweep grande
  → mitigação: cap de findings por specialist (ver `PROACTIVE_COUNCIL.md`)

### Migration plan

- Fase 1 (DONE): core archetypes + v33-specialist + KB local seed
- Fase 2 (DONE neste ADR): 6 specialists + ADR-001 + FEATURE_MATRIX stub + PROACTIVE_COUNCIL
- Fase 3 (next): 6 micro-agents
- Fase 4 (next): KB hydrate + first proactive sweep + V33_PIPELINE_MAP.md

### Rollback

Se council project-local provar overhead > valor:

1. `rm -rf .claude/agents/` (volta a user-level only)
2. `rm -rf knowledge_base/` (cancela KB local)
3. `rm findings-inbox.md docs/PROACTIVE_COUNCIL.md docs/AGENTS_GUIDE.md`
4. Update referências em `docs/` para apontar a `~/.claude/agents/`
5. `.nestor/` pode ficar (substrate barata; sem custo de manter)

Memória de checkpoint guarda o HEAD pré-bootstrap (`691a529`) para revert hard se necessário.

## Validation / acceptance criteria

- [x] Fase 1 — core archetypes + v33-specialist criados
- [x] Fase 1 — KB local seed extraída do código (4 docs)
- [x] Fase 1 — smoke test #1 (KB local) PASS
- [x] Fase 1 — smoke test #2 (KB central + gap detection) PASS
- [x] Fase 2 — 6 specialists adicionais criados (frontend, deploy, qa, security, customer-success, v1-intel)
- [x] Fase 2 — ADR-001 (este doc) commit
- [x] Fase 2 — FEATURE_MATRIX stub criado
- [x] Fase 2 — PROACTIVE_COUNCIL.md (5 triggers)
- [ ] Fase 3 — 6 micro-agents
- [ ] Fase 4 — KB hydrate + first sweep
- [ ] 30 dias post-bootstrap — review do council via `core-council-architect`

## References

- `prompts/BOOTSTRAP_COUNCIL_V33.md` — prompt original do bootstrap
- `~/.claude/agents/` — agents cross-product (referência)
- `c:/Users/ue_e-snetto/Documents/projetosPython/watcherdb-council/docs/AGENTS_GUIDE.md` — projecto-mãe
- `c:/Users/ue_e-snetto/Documents/projetosPython/nestor-template/.claude/agents/` — templates
- `docs/AGENTS_GUIDE.md` — guia operacional do council V3.3
- `docs/PROACTIVE_COUNCIL.md` — 5 triggers
- `docs/KNOWLEDGE_BASE_GUIDE.md` — dual-library
- `docs/adr/ADR-002-dual-library-knowledge.md` — decisão dual-library
- `MEMORY.md/feedback_qa_dual_lens.md` — rationale "dois olhares" QA
- `MEMORY.md/feedback_specialist_depth_of_analysis.md` — rationale end-to-end depth
- `MEMORY.md/feedback_velocity_pact.md` — rationale velocity pact
- Commit `691a529` — HEAD V3.3 ao tempo de bootstrap (rollback reference)
