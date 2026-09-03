# Proactive Council — V3.3 (5 Triggers + Cadence)

Council "vivo": specialists não esperam pedidos — actuam por gatilhos. Esta doc
codifica os **5 gatilhos canónicos** + cadence + checklist de PROACTIVE FINDING.

Última actualização: 2026-04-28 (bootstrap)

---

## 1. Princípio

Council reactivo (espera pedido) deixa muito problema escondido. Council proactivo
detecta antes do user pedir. Mas **proactivity sem disciplina = ruído**. Daí 5
gatilhos formais com checklist e severity rubric.

## 2. Os 5 gatilhos

### Trigger 1 — Session sweep (no início de cada sessão Claude Code)

**Quem dispara:** orquestrador (automático no arranque).

**O que faz:**

1. Lê last 5 commits no V3.3
2. Identifica áreas tocadas (auth? frontend? DDL? deploy?)
3. Dispatch dos specialists relevantes em paralelo (Pattern #7) com brief: *"última
   janela tocou em X — qualquer regression / proactive finding?"*
4. Cada specialist lê `.nestor/session.log` + `.nestor/bulletin/inbox.md` (Living Nestor)
5. Findings vão para `findings-inbox.md`

**Tempo:** ~2-3 min, custo ~ 30-50k tokens. Skip se sessão é muito curta (1
pergunta trivial).

### Trigger 2 — Sprint milestone (antes de tag / release)

**Quem dispara:** orquestrador quando user pede *"vamos preparar release"* ou
*"tag v3.3.X"*.

**O que faz:**

1. `qa-specialist` corre Gate 3 (ver `qa-specialist` charter)
2. `security-auditor` corre CVE scan + compliance checklist
3. `customer-success-persona` corre 3 critical workflows (morning check / incident
   triage / compliance audit)
4. `deploy-architect` valida installer corre clean em staging
5. **Veredicto consolidado** = MIN(qa, security, customer-success, deploy)

**Não é commit-gate** (orquestrador escolhe se procede). É **release-gate**.

### Trigger 3 — Market scan (semanal — opcional)

**Quem dispara:** user pede *"sweep semanal"* ou cadence weekly automated.

**O que faz:**

1. `ai-systems-architect` (cross-product, ~/.claude/agents/) faz horizon scan SOTA AI
2. Para V3.3 que é Std sem AI, este trigger é **light** — focado em deps Python
   (FastAPI updates? pyodbc CVEs?), packaging trends (Nuitka maturity?), banking
   compliance evolution (novos controls?)
3. Findings em `findings-inbox.md` com prefixo `MARKET-` (separar de bugs)

V3.3 sozinho usa este trigger pouco (mais relevante em V5+ Pro). Light cadence.

### Trigger 4 — Feature ideation (quando user lança ideia)

**Quem dispara:** user diz *"e se fizéssemos X?"* ou sketches feature nova.

**O que faz:**

1. `core-council-architect` valida que council tem owner para a feature
2. `v33-specialist` corre Tier Decision Framework (4 questions) → Std / Pro / ambíguo
3. Se Std: dispatch paralelo de `frontend` + `qa` + `customer-success` + `security`
   para fit assessment
4. Output: feasibility + tier + complexity estimate + risks before implementation

**Crítico:** não implementar antes do council ter falado. Anti-pattern: "user pediu,
só faço". Council protege user de erros.

### Trigger 5 — Architectural review (diff toca > 3 ficheiros core)

**Quem dispara:** orquestrador detecta diff grande em `git status` antes de commit.

**Definição "ficheiro core":**

- `watcherdb_main.py`
- `api/async_db.py`, `api/connection_pool.py`
- `api/routers/auth_compat.py`
- Qualquer `modules/performance/investigators/*.py`
- `services/web_service/service.py`, `install.py`, `config.yaml`
- `templates/watcherdb_portal.html`
- `scripts/sql/performance_module_schema.sql`

**O que faz:**

1. Dispatch paralelo: `v33-specialist` + relevantes (auth → security; SPA → frontend; DDL → v1-intel)
2. Cada specialist faz review com formato HANDOFF_CONTRACT
3. Output: GO / GO-com-ressalvas / NO-GO antes de commit
4. Se NO-GO: orquestrador pergunta user antes de proceder

## 3. Severity rubric (cross-trigger)

| Severity | Significado | Acção |
|---|---|---|
| **critical** | Produção quebrada / data loss / segurança crítica | Pára outra coisa, trata já |
| **high** | Bug funcional / regressão Std visível ao cliente / CVE HIGH em dep | 24-48h |
| **medium** | Gap de tiering / divergência Std-Pro / docs em falta importantes | Sprint actual |
| **low** | Limpeza / dívida técnica / docs em falta minor | Backlog |

## 4. Checklist PROACTIVE FINDING (formato literal)

```
[PROACTIVE FINDING]: <category> | <path:linha> | <severity> — <descrição 1 frase> / <sugestão 1 frase>
```

- **category:** `security | performance | reliability | opportunity | tiering | docs | ux | privacy | compliance | accessibility`
- **path:linha:** absoluto ou relativo a V3.3, **confirmado via Read/Grep** (não especulativo)
- **máx 3 findings por resposta** (prioriza alta severidade)

Findings vão para `findings-inbox.md` (raiz V3.3) com FIND-YYYYMMDD-NNN.

## 5. Cadence anti-burnout

Specialists não devem disparar findings constantemente. Disciplina:

- **Por sessão:** máx 3 findings por specialist por dispatch
- **Por trigger 1 (session sweep):** total findings de todos os specialists ≤ 10
- **Por trigger 2 (sprint milestone):** sem cap (release exige rigor)
- **Por trigger 5 (architectural review):** sem cap mas pesado (commit decision)

Triagem semanal: orquestrador / DBA Lead promove findings P0/P1 a tasks; arquiva
P2 sem owner.

## 6. Anti-patterns

- "Proactive" sem disciplina → 50 findings P3 noise, P0 perdido
- Dispatch paralelo sem síntese — relatórios de 3 specialists sem o orquestrador
  consolidar é só ruído
- Findings sem evidence (path + linha) — rejeitar
- Skip de session sweep "porque é só pergunta rápida" — perde-se contexto que
  ajuda perguntas seguintes

## 7. References

- `docs/AGENTS_GUIDE.md` — quem é quem
- `docs/HANDOFF_CONTRACT.md` — formato brief
- `docs/BULLETIN_FORMAT.md` — comunicação inter-specialist
- `findings-inbox.md` — depósito de findings
- `.nestor/session.log` — Living Nestor activity log
- `.nestor/bulletin/inbox.md` — Living Nestor bulletin
