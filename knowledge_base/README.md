# Knowledge Base — WatcherDB V3.3 (Local)

Biblioteca local do projecto V3.3, parte do **dual-library pattern** Nestor.

## Quando consultar esta biblioteca (vs central)

| Tipo de pergunta | Biblioteca |
|---|---|
| Std vs Pro tiering, KPI behaviour V3.3, modal X em `watcherdb_portal.html`, porta 8433, AD config V3.3, deploy V3.3 | **Local** (este dir) |
| PyArmor Pro / packaging Python / OWASP / SQL Server reference / attack surface canon | **Central** (`~/.nestor-library/`) |
| Conflito local vs central | Local ganha para V3.3-specific; central ganha para canon doctrinal |
| Tier Std/Pro definitivo | `docs/FEATURE_MATRIX.md` ganha sobre tudo |

## Estrutura

- `architecture/` — diagramas, pipeline maps V3.3
- `decisions/` — espelho de `docs/adr/`
- `operations/` — runbooks (`deploy_runbook_v33.md`, `ad_service_account_rotation.md`, ...)
- `domain/` — SQL Server domain (`kpi_catalog_v33.md`, thresholds, collector patterns)
- `incidents/` — post-mortems sanitizados (sem nomes de cliente)
- `release_notes/` — releases anotadas pelo council
- `glossary.md` — termos do domínio (DBA + SQL Server + WatcherDB)
- `index.json` — manifesto + checksums (mantido pelo `v33-knowledge-base-curator`)

## Como contribuir

1. **Submeter** ao `core-librarian` (chat path) — *"adiciona X à KB local"*
2. **5 Governance Gates** (dedup / license / quality / sensitivity / namespace) — obrigatórios
3. Após PASS, doc é colocado na namespace + entrada em `index.json`
4. `v33-knowledge-base-curator` recalcula checksums semanalmente

## Anti-patterns

- Editar directamente `index.json` à mão (deixar para o curator)
- Misturar ficheiros internos (que possam ter nomes de cliente / hostnames reais) sem sanitização
- Duplicar conteúdo já presente em `~/.nestor-library/shared/` (regra: doctrinal canon vive na central)

## References

- `docs/KNOWLEDGE_BASE_GUIDE.md` — guia completo (precedência + onboarding + governance gates)
- `docs/adr/ADR-002-dual-library-knowledge.md` — decisão arquitectónica
