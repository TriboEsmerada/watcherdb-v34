---
name: wave-close
description: Fecha uma Wave em WatcherDB com checklist obrigatorio de propagacao -- canonical SQL sync (INSTALACAO_COMPLETA_UNIFICADA.sql se V1 schema), specialist agent training (.claude/agents/*.md), documentacao em bibliotecas internas (knowledge_base/) + Nestor central (~/.nestor-library/watcherdb-family/), e CHANGELOG SemVer com tier annotations.
---

# Wave Close

## When this skill triggers

User diz "fecha Wave X", "Wave shipped, e agora?", "finaliza Wave", ou
acaba de fazer commit do code/test da Wave e precisa propagar mudancas
a documentacao + specialists + libraries antes de declarar Wave concluida.

## Filosofia

Code merged != Wave fechada. Wave shipped pode deixar 4 tipos de drift
silencioso:

1. **Canonical install drift** -- fresh install num cliente novo cria BD
   com schema antigo porque `INSTALACAO_COMPLETA_UNIFICADA.sql` nao foi
   actualizado (so' o migration script foi)
2. **Specialist knowledge drift** -- subagents (.claude/agents/*.md)
   continuam a recomendar patterns antigos porque description / domain
   knowledge nao foi update
3. **Library drift** -- documentacao em `knowledge_base/` (local) e
   `~/.nestor-library/watcherdb-family/` (central) desactualizada =
   AI propoe arquitectura obsoleta em sessoes futuras + cross-product
   consultations recebem info errada
4. **Changelog drift** -- CHANGELOG SemVer sem entry da Wave = audit
   trail incompleto

## Checklist obrigatorio

### 1. Schema canonical sync (se Wave envolveu V1 schema change)

- [ ] `WATCHERDB INTELLIGENCE V1/database/INSTALACAO_COMPLETA_UNIFICADA.sql`
      reflecte estado final post-wave (PRIMARY canonical, fresh install)
- [ ] Migration script `UPDATE_<OBJ>_WAVE_<X>.sql` criado se in-place
      upgrade necessario para instalacoes vivas
- [ ] Reference [[doc-updates-on-watcherdb-intelligence-schema-changes]]

Verificar:
```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython"
git log --oneline --follow "WATCHERDB INTELLIGENCE V1/database/INSTALACAO_COMPLETA_UNIFICADA.sql" | Select-Object -First 5
```

### 2. Specialist training (subagents .md)

Quando Wave introduz/modifica feature, pattern, ou domain knowledge que
specialist actual nao conhece -> UPDATE specialist .md em `.claude/agents/`.

**Quando treinar:**
- Nova feature visivel a DBA cliente -> `watcherdb-customer-success-persona`,
  `watcherdb-v33-specialist` (se Std), `watcherdb-v5-specialist` (se Pro),
  `watcherdb-v1-intel-specialist` (se V1 schema)
- Novo pattern UI/UX -> `watcherdb-frontend-specialist`
- Nova security surface -> `watcherdb-security-auditor` + `watcherdb-hacker-team-specialist`
- Novo deploy mechanism -> `watcherdb-deploy-architect`
- Nova test pattern -> `watcherdb-qa-specialist`
- Tier classification change -> `v33-feature-matrix-checker`

**O que update:**
- Description (se scope do specialist evoluiu)
- Domain knowledge body (ex: "conhece X feature shipped Wave Y")
- Wave history references (manter linha do tempo)

**Verificar quem precisa update:**
```powershell
cd "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3"
Select-String -Path ".claude/agents/*.md" -Pattern "Wave [A-Z]" | Group-Object Path | Sort-Object Count -Descending
```

### 3. Library documentation (DUAS bibliotecas)

#### 3a. LOCAL `knowledge_base/` (V3.3 project-specific)

Estrutura:
- `architecture/` -- decisoes arquitecturais, ADRs locais
- `domain/` -- domain knowledge SQL Server monitoring
- `operations/` -- runbooks operacionais
- `release_notes/` -- notas user-facing

Update aplicavel quando Wave envolveu:
- Architecture change -> `architecture/<area>.md`
- Operational pattern change -> `operations/<topic>.md`
- User-visible feature -> `release_notes/`

Manter `knowledge_base/index.json` sincronizado via
`v33-knowledge-base-curator` agent (SHA-256 checksums + timestamps).

#### 3b. NESTOR central `~/.nestor-library/watcherdb-family/`

Estrutura:
- `adrs/` -- Architecture Decision Records cross-product
- `architecture/` -- arquitectura cross-tier (V3.3 + V5 + V6 + V1)
- `offensive_security/` -- red team runbooks (RB-001..)
- `pipeline_maps/` -- WATCHERDB_AI_PIPELINE_MAP.md tipo docs
- `runbooks/` -- operational runbooks cross-product

Update quando Wave teve impacto cross-product (V3.3 -> V6 propagation,
V1 schema shared, tier matrix change). Use `core-librarian` agent para
ingest com 5 governance gates (dedup + license + quality + sensitivity +
namespace).

**Anti-pattern:** updates so' no LOCAL sem propagar a NESTOR quando
mudanca afecta multiple tiers -> outras sessoes (V5, V6, AoLado) nao
veem o update.

### 4. CHANGELOG SemVer

- [ ] Entry na versao SemVer apropriada (major/minor/patch decidido per Wave)
- [ ] `[tier: Std]` ou `[tier: Pro]` por linha (convencao V3.3)
- [ ] `### Highlights`, `### Added`, `### Changed`, `### Compatibility`,
      `### Documentation`, `### Refs` (Pattern Keep-a-Changelog estabelecido)

### 5. Memoria persistente (lessons learned)

Se a Wave gerou lesson learned (incident, surprise, validation falhou
e fix) -> propor memoria nova/update via PROPOSTA DE MEMORIA. Per modo
consultor AI nao escreve directamente em memory/.

### 6. Indice de solucoes (SOLUCOES.md) — decisao owner 2026-08-19

- [ ] Por cada bug / falso positivo / armadilha / regressao resolvido na
      Wave: 1 linha em `docs/context/SOLUCOES.md` (formato e regras na
      skill `recall`: data | sintoma | causa-raiz | fix | ponteiro |
      palavras-chave PT+EN). E' o que permite `/recall` encontrar o
      precedente na proxima vez que o sintoma aparecer.

## Output (dispatch decision)

Apos completar checklist, propor dispatch:

- `v33-feature-matrix-checker` -> validar tier antes do commit
  ([[force-tier-checker-precommit]])
- `v33-knowledge-base-curator` -> sync `index.json` se KB local mudou
- `core-librarian` -> ingest novo doc em Nestor se cross-product

Esperar GO antes de dispatch (Mode B suggest pattern,
[[dispatch-mode-b-suggest]]).

## Anti-pattern

- Declarar "Wave fechada" baseado so' em "commit + push merged"
- Skip specialist training -> outros agents recomendam pattern obsoleto
  na proxima sessao
- Skip library docs -> drift entre code real e doc canonical
- Skip Nestor propagation -> cross-product sessions com info errada
- Skip CHANGELOG -> audit trail incompleto

## Relacionado

- [[doc-updates-on-watcherdb-intelligence-schema-changes]] -- 5-surface rule
- [[v33-v6-propagation-rule]] -- V3.3 fixes propagam a V6
- [[force-tier-checker-precommit]] -- tier validation antes commit
- [[no-premature-excitement]] -- nao declarar Wave shipped antes de validar
- [[dispatch-mode-b-suggest]] -- propor dispatch + esperar GO
