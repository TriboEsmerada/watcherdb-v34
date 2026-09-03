# Agents Guide — WatcherDB V3.3 Council

Documento operacional do Nestor Council local em V3.3. Quem são os agents,
quando invocar, como pedir bem.

Última actualização: 2026-04-28 (bootstrap)

---

## 1. Modelo mental

```
+----------------------+
|  Utilizador (DBA)    |
+----------+-----------+
           |
           v
+----------------------+         +---------------------+
|  Orquestrador        |  spawn  |  Specialist /        |
|  (Claude Code main)  | ------> |  Micro-agent        |
|                      |         |                     |
|  - Edit/Write/Bash   |  result |  - Read-only        |
|  - context completo  | <------ |  - context vazio    |
|  - aplica mudanças   |         |  - emite parecer    |
+----------------------+         +---------------------+
```

**Princípios:**

1. O **orquestrador** fala com o user, tem context completo, aplica mudanças.
2. **Specialists** são read-only — produzem pareceres, diffs em texto, findings.
3. **Micro-agents** são read-only single-task — output rígido.
4. Excepção: `core-librarian` tem `Write` (limitado a `knowledge_base/` + `.nestor/`).

## 2. Inventário do council V3.3 (project-local)

### Core archetypes (fixos em qualquer projecto Nestor)

| Agent | Tools | Quando invocar |
|---|---|---|
| `core-council-architect` | Read, Grep, Glob, Bash | Re-avaliação periódica do council, gaps detectados, propostas de novos micro-agents |
| `core-librarian` | Read, Grep, Glob, Bash, WebFetch, **Write** | Onboarding de doc à KB local/central com 5 gates, retrieval avançado, audit de staleness |

### Domain specialists V3.3

| Specialist | Multi-persona | Scope |
|---|---|---|
| `watcherdb-v33-specialist` | Senior Backend Eng + DBA Domain Expert + Std/Pro Tier Curator | Owner técnico V3.3 — FastAPI, performance module, KPI flow, auth multi-domain LDAP, tabelas KPI partilhadas com V1 |
| `watcherdb-frontend-specialist` | Frontend Eng + UX Designer + A11y Auditor + Design System Architect | SPA `watcherdb_portal.html`, Jinja2, Chart.js, modais, CSS, WCAG 2.1 AA, vanilla JS |
| `watcherdb-deploy-architect` | Release Eng + Windows Sysadmin + AD/Security + DBA + SRE | PyArmor Pro (reg 11618), Windows services, Task Scheduler, AD service accounts, DDL orchestration, upgrade/rollback |
| `watcherdb-qa-specialist` | QA Eng + Test Architect + Release Gate Keeper | Test strategy, regression health, coverage, pre-commit hooks, quality gates. Pattern: dois olhares (técnico + utilizador final crítico); veredicto = MIN(tech, user) |
| `watcherdb-security-auditor` | CISO + AppSec Eng + Compliance + Red Team mindset | STRIDE, OWASP Top 10, CVE monitoring, RBAC, banking-grade compliance (SOC 2, ISO 27001, PCI-DSS, GDPR). Tem WebSearch para CVE lookups |
| `watcherdb-customer-success-persona` | DBA Lead + Support Eng + Customer Advocate | Voz do DBA cliente pagante. Avalia features antes de ship como em prod real. Friction em troubleshooting / runbooks / FAQ |
| `watcherdb-v1-intel-specialist` | Collector Eng + DBA + SRE | Collector V1 + BD partilhada `WatcherDB_Intelligence`, `usp_swap_kpi_stg_tables`, pares BLUE/GREEN. **Veto power** em mudanças à infra partilhada (V1 alimenta V3.3 e tiers Pro) |

### Micro-agents (tier leve, single-task)

| Micro-agent | Output |
|---|---|
| `v33-feature-matrix-checker` | Dado um diff, valida tier Std vs Pro. PASS/FAIL + linhas a corrigir |
| `v33-changelog-assistant` | Dado git log range, propõe entrada de RELEASE_NOTES no estilo do projecto |
| `v33-port-collision-checker` | Scan rápido das portas usadas (8433, 8443, 8449, 8450, 8452, 8460, 8555, 8660); flag de colisão |
| `v33-i18n-coverage` | Dado HTML alterado, lista chaves pt/en/es em falta |
| `v33-modal-auth-gate-checker` | Confirma que modais novos têm `data-admin-gated` quando tocam endpoints `_require_admin` |
| `v33-knowledge-base-curator` | Mantém `index.json` da KB local actualizado (checksums + timestamps + tags) |

### Cross-product (referenciar, NÃO duplicar)

Estes vivem em `~/.claude/agents/` e são partilhados com outros projectos. V3.3 invoca-os
via `Agent` tool (Claude Code resolve user-level por defeito quando project-level não existe):

- `ai-systems-architect` — decisões AI/LLM cross-product (raro em V3.3, que é Std sem AI)
- `python-packaging-architect` — packaging Python → exe (PyArmor, installers)

## 3. Padrões operacionais

### Pattern #7 — Cross-Cutting Consensus

Decisões que tocam multi-domain → dispatch em **paralelo** (mesma message, múltiplos
`Agent` tool calls), depois sintetizar consenso/dissenso.

Exemplo: feature core nova → `v33-specialist` + `frontend-specialist` + `qa-specialist`
+ `customer-success-persona` + `security-auditor` em paralelo.

### Knowledge sources (precedência fixa)

1. **Pergunta V3.3-específica** → KB local (`knowledge_base/`) primeiro
2. **Pergunta cross-product / doctrinal** → KB central (`~/.nestor-library/`)
3. **Conflito** → local ganha em V3.3-specific; central ganha em canon doctrinal
4. **Tier Std/Pro** → `docs/FEATURE_MATRIX.md` ganha sobre tudo
5. **Specialists CITAM fonte** (path + linha). Sem citação = parecer inválido

### Velocity Pact

- Aprovação tácita por escopo: avança no escopo autorizado
- Pára em mudança de rumo (não apenas detalhe)
- **Sempre** confirma irreversível: `rm -rf`, push --force, drop table, alterar infra V1 partilhada

### Sprint progress reporting

Durante sprints autorizados: `[PROGRESS HH:MM] X% geral / Y% sprint` a cada ~5min.

## 4. Quando invocar (cheat sheet)

| Situação | Specialist |
|---|---|
| Feature core nova (qualquer KPI, dashboard, performance) | `v33-specialist` (P0) + `frontend-specialist` se UI |
| Bug em produção V3.3 | `v33-specialist` + `qa-specialist` (regression) |
| Modal novo / mudança SPA | `frontend-specialist` + `v33-modal-auth-gate-checker` |
| Deploy / installer / PyArmor | `deploy-architect` + `python-packaging-architect` (cross-product) |
| Auth / AD / RBAC | `v33-specialist` (multi-domain LDAP) + `security-auditor` |
| Compliance / CVE / threat model | `security-auditor` |
| UX review / DBA cliente perspective | `customer-success-persona` |
| Mudança que toca tabelas KPI / V1 collector | `v1-intel-specialist` (veto power) + `v33-specialist` |
| Re-avaliação do council, gaps | `core-council-architect` |
| Adicionar doc à biblioteca | `core-librarian` |
| Tier Std vs Pro de mudança proposta | `v33-feature-matrix-checker` (micro) |
| Mudança em SPA, validar i18n | `v33-i18n-coverage` (micro) |
| Antes de release tag | `v33-changelog-assistant` (micro) + `v33-port-collision-checker` (micro) |

## 5. Como escrever bons briefs (checklist)

Specialists não vêem a conversa. Bons briefs têm:

- [ ] Contexto do problema (1-2 parágrafos)
- [ ] Estado actual (o que foi tentado / descartado)
- [ ] Localização precisa (paths absolutos + linhas)
- [ ] Tarefa concreta (lista numerada, não "podes analisar")
- [ ] Restrições críticas (read-only? backward compat? sem commit?)
- [ ] Formato de output esperado (template com headings fixos)
- [ ] Word count cap (500-700 palavras força foco)

## 6. Anti-patterns

- "Based on findings, fix X" → delega entendimento. Cita path/linha exacto.
- Prompt genérico ("review V3.3") → shallow output garantido.
- Spawnar specialist para 1 grep → overhead > valor; usar Grep directamente.
- Reusar agent com `SendMessage` para tarefa nova → context desactualizado; spawn fresh.
- Confiar no resumo do agent → reports intenção, não execução. Verificar via `git diff`/`Read`.

## 7. Onde editar

- Project-local agents: `WATCHERDB_V3.3/.claude/agents/<name>.md`
- User-level agents (cross-product): `C:\Users\ue_e-snetto\.claude\agents\<name>.md`
- Project-local agents **têm precedência** quando o cwd é V3.3.

## 8. References

- `docs/PROACTIVE_COUNCIL.md` — 5 triggers de council vivo
- `docs/HANDOFF_CONTRACT.md` — formato brief self-contained
- `docs/BULLETIN_FORMAT.md` — formato bulletin posts entre specialists
- `docs/KNOWLEDGE_BASE_GUIDE.md` — dual-library + onboarding
- `docs/FEATURE_MATRIX.md` — ground truth tiering
- `docs/adr/ADR-001-council-composition.md` — porque estes 7 specialists
- `docs/adr/ADR-002-dual-library-knowledge.md` — KB local + central
