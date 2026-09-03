# ADR-002 — Dual-Library Knowledge Pattern (Local V3.3 + Central Nestor)

- **Status:** Accepted
- **Date:** 2026-04-28
- **Owner specialist:** core-librarian (proposto), orquestrador (decidiu)
- **Stakeholders consulted:** watcherdb-v33-specialist, core-council-architect (charter sketches)

## Context

O council V3.3 (Nestor framework) precisa de acesso rápido a dois corpos de
conhecimento distintos quando emite pareceres:

1. **Conhecimento V3.3-específico** — KPI catalog, deploy runbook, AD rotation,
   thresholds, decisões arquitectónicas locais, post-mortems V3.3. Este conteúdo
   é volátil (muda a cada release), específico do projecto, e contém
   informação que pode ser sensitiva (sanitização obrigatória para nomes
   de cliente / hostnames).

2. **Conhecimento doctrinal cross-product** — OWASP Top 10, PyArmor Pro docs,
   packaging Python (PyInstaller, Nuitka), SQL Server reference, attack
   surface canon, watcherdb-family pipeline maps. Este conteúdo é estável
   (semanas/meses entre updates), partilhado entre V3.3 / V5 / V5.5 / V6 / V1
   Intelligence, e doctrinal por natureza.

Misturar os dois corpos numa única biblioteca cria problemas:

- **Performance retrieval** — corpus grande dilui top-K para perguntas
  V3.3-specific
- **Governance** — sensitivity gate aplicado a tudo penaliza canon doctrinal
  (que não tem PII)
- **Sync** — actualizações ao canon não devem requerer redeploy do projecto V3.3
- **Reuso** — V5/V5.5/V6/V1 já consomem a central; duplicar quebra single-source

## Decision

Adoptar **dual-library pattern**:

- **LOCAL** em `<repo>/knowledge_base/` — V3.3-specific, gerido pelo
  `core-librarian` deste projecto + `v33-knowledge-base-curator` (micro-agent)
- **CENTRAL** em `C:\Users\ue_e-snetto\.nestor-library\` — canon doctrinal
  cross-product, partilhado com toda a família WatcherDB e outros projectos
  Nestor (AoLado, Polo)

Specialists do council seguem **regras de precedência** fixas:

1. V3.3-specific → local primeiro
2. Cross-product / doctrinal → central directamente
3. Conflito → local ganha em V3.3-specific; central ganha em doctrinal
4. Tier Std vs Pro → `docs/FEATURE_MATRIX.md` ganha sobre tudo
5. **Citar fonte** sempre (path + linha)

## Rationale

1. **Separação de concerns**: V3.3-specific muda com cada sprint; canon doctrinal
   muda com publicações externas (OWASP releases, novos CVEs). Lifecycles
   distintos justificam stores distintos.
2. **Sensitivity boundary clara**: hard reject de PII / customer data aplica-se
   a ambos, mas a probabilidade de detectar incidents/release notes com
   conteúdo sensível é alta em local (zero em central).
3. **Reuso cross-projecto**: já existe `~/.nestor-library/watcherdb-family/`
   activa com pipeline maps + offensive security canon. V3.3 herda em vez
   de duplicar.
4. **Retrieval focus**: corpus pequeno e bem curado tem precedência > corpus
   gigante e ruidoso para perguntas project-specific.
5. **Governance simétrica**: 5 gates (dedup, license, quality, sensitivity,
   namespace) aplicam-se a ambos, com regras especiais para sensitivity em
   local (mais paranóia).

## Alternatives considered

| Opção | Pros | Cons | Rejeitada porque |
|---|---|---|---|
| **Tudo em central** | Single source, retrieval unified | V3.3-specific dilui canon; sync requer push externo a cada change | V3.3 muda demasiado rápido; canon não deve ser editado por dev velocity |
| **Tudo em local** | Self-contained no repo | Duplica canon entre 5+ projectos; updates a OWASP requerem N PRs | Anti-DRY massive; canon não é V3.3-property |
| **Local-only com symlinks para central** | Simples | Symlinks Windows-fragile; requer setup manual em cada clone | Não portable; não testável em CI sem hacks |
| **Dual-library com regras de precedência** | Best of both | Specialists têm de saber regra | **Aceite** — regra é simples (5 perguntas), formalizada em charter |

## Consequences

### Positive

- Specialists têm latência baixa em perguntas V3.3-specific (KB local pequena)
- Canon doctrinal pode evoluir sem afectar V3.3 deploy
- Reuso garantido entre projectos da família WatcherDB
- Sensitivity boundary é geográfica (local) — fácil enforce em CI

### Negative / Trade-offs

- Specialists têm de aprender regra de precedência (1 parágrafo no charter)
- `core-librarian` gere dois manifestos `index.json` em vez de um
- Retrieval híbrido (local + central) requer 2 chamadas em queries cross-cutting
  → orquestrador pode dispatch paralelo se relevante

### Migration plan

Bootstrap (Fase 1 do prompt `BOOTSTRAP_COUNCIL_V33.md`):

1. Criar `knowledge_base/` skeleton (4 namespaces + index.json + README + glossary)
2. Seed inicial: 4 docs (KPI catalog, deploy runbook, AD rotation, latest release anotado)
3. Adoptar `core-librarian` charter com regras de precedência embutidas
4. ADR-002 (este doc) commitado com Fase 1
5. Fase 4: KB hydrate run — `core-librarian` promove `docs/` existentes para `knowledge_base/`
   com governance gates

### Rollback

Se dual-library provar overhead > valor:

1. Migrar conteúdo de `knowledge_base/` para `~/.nestor-library/watcherdb-family/v33/`
2. Update charter `core-librarian` para single-library
3. Remover regras de precedência (single-library = sem ambiguidade)

## Validation / acceptance criteria

- [x] `knowledge_base/` skeleton criado (Fase 1.1)
- [x] `index.json` válido com 4 namespaces inicializadas
- [x] `core-librarian` charter inclui regras de precedência (5 regras)
- [x] `KNOWLEDGE_BASE_GUIDE.md` documenta dual-library
- [x] Smoke test (Fase 1.5): `v33-specialist` consulta KB local + central com sucesso
- [ ] Fase 4: KB hydrate completo (deferred até autorização)

## References

- `docs/KNOWLEDGE_BASE_GUIDE.md` — guia operacional
- `knowledge_base/README.md` — navegação local
- `knowledge_base/index.json` — manifesto local
- `~/.nestor-library/` — biblioteca central
- `.claude/agents/core-librarian.md` — charter completo
- ADR-001 (council composition) — contexto council bootstrap
- `prompts/BOOTSTRAP_COUNCIL_V33.md` — prompt de bootstrap original
