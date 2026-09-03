# Bulletin Format — Council V3.3

Specialists comunicam entre si via `.nestor/bulletin/inbox.md`. Cada post é
single-purpose, dirigido (a 1+ specialists), e tem estrutura fixa para
parsing humano e futuro automação.

## Quando postar

- Encontraste algo cross-domain (afecta outro specialist + tu)
- Identificaste finding que o owner natural não viu
- Querias coordenar mudança a infra partilhada (ex.: V1 collector tabelas)
- Reportar handoff: "fiz X, próximo passo é Y, recomendo specialist Z"

**NÃO postar para:**

- Findings dirigidos ao orquestrador (vão para `findings-inbox.md` na raiz)
- Anotações privadas (vão para `.nestor/session.log`)
- Conversa cliente-facing (out-of-scope desta substrate)

## Formato canónico

```markdown
## [YYYY-MM-DD HH:MM] <from-specialist> → <to-specialist>(s)

**Subject:** <título curto, 60 chars max>

**Context:** <1 parágrafo — porque estou a postar>

**Evidence:**
- <path:linha ou commit hash ou query ref>

**Action requested:**
- [ ] <acção concreta requerida do destinatário>

**Severity:** info | low | medium | high | critical

**Related:** FIND-YYYYMMDD-NNN (se aplicável) | session.log entry | ADR

---
```

## Convenções

- **From / To**: nomes exactos dos agents (ex.: `watcherdb-v33-specialist`, `watcherdb-frontend-specialist`)
- **Multi-destinatário**: separar com `, ` ou `+` (ex.: `→ frontend-specialist + qa-specialist`)
- **Severity rubric** (igual a findings-inbox):
  - `info` — FYI, sem acção urgente
  - `low` — registar; tratar em backlog
  - `medium` — tratar nesta sprint
  - `high` — tratar nas próximas 24-48h
  - `critical` — pára outra coisa, trata já

## Lifecycle

1. Specialist posta → orquestrador ou destinatário lê no próximo dispatch
2. Destinatário responde (post adjacente) ou cria FIND no `findings-inbox.md`
3. Quando resolvido, marcar com `~~strikethrough~~` no post original ou mover para `.nestor/bulletin/archive/YYYY-MM/`

## Exemplo

```markdown
## [2026-04-28 14:32] watcherdb-v33-specialist → watcherdb-frontend-specialist

**Subject:** Modal "Add Server" sem `data-admin-gated` mas chama endpoint `_require_admin`

**Context:** Durante audit do auth flow Patch D, detectei que o modal `addServerModal` em
`templates/watcherdb_portal.html:33850` não tem o atributo `data-admin-gated` mas o
endpoint que ele chama (`POST /api/v1/servers`) está protegido por `_require_admin`
(`api/routers/servers.py:42`). UI mostra modal a non-admin → server retorna 403 → UX confusa.

**Evidence:**
- `templates/watcherdb_portal.html:33850` (modal markup)
- `api/routers/servers.py:42` (decorator)

**Action requested:**
- [ ] Adicionar `data-admin-gated` ao modal e validar com `v33-modal-auth-gate-checker`

**Severity:** medium

**Related:** FIND-20260428-002 (criado)

---
```
