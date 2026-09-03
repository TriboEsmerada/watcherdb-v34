# Knowledge Base Guide — V3.3 Dual-Library

Como specialists e o orquestrador consultam e contribuem para as duas
bibliotecas que servem o council V3.3.

## 1. Visão geral

| Biblioteca | Path | Conteúdo | Curador |
|---|---|---|---|
| **Local V3.3** | `knowledge_base/` (dentro do repo) | Docs V3.3-specific (KPI catalog, deploy runbook, AD rotation, ADRs locais, incidents sanitizados, release notes anotadas) | `core-librarian` + `v33-knowledge-base-curator` |
| **Central Nestor** | `C:\Users\ue_e-snetto\.nestor-library\` | Canon doctrinal cross-product (OWASP, PyArmor, packaging Python, SQL Server reference, watcherdb-family pipeline maps) | `core-librarian` (gere ambas) |

## 2. Regras de precedência (não negociáveis)

1. **Pergunta V3.3-específica** (KPI behaviour, Std vs Pro, modal X, porta 8433,
   AD config V3.3, deploy V3.3) → consultar **LOCAL primeiro**.
   Só escalar para central se local não cobre.

2. **Pergunta cross-product / doctrinal** (PyArmor, packaging Python, OWASP,
   SQL Server reference, padrões de attack surface, threat models genéricos)
   → consultar **CENTRAL directamente**.

3. **Conflito entre local e central** → local ganha para V3.3-specific;
   central ganha para canon doctrinal. Em dúvida, citar **ambos** e levantar
   finding no `findings-inbox.md`.

4. **Ground truth doc** (`docs/FEATURE_MATRIX.md`) tem **precedência sobre
   qualquer biblioteca** para tier Std vs Pro.

5. **Specialists CITAM a fonte** (path do doc + linha) na resposta.
   Pareceres sem citação são rejeitados pelo orquestrador.

## 3. Como consultar

### MCP tools (preferenciais para central)

```
mcp__nestor-library__library_search    # semantic + keyword
mcp__nestor-library__library_list_docs # inventário
mcp__nestor-library__library_health    # status do índice
```

### Fallback (local OU central quando MCP falha)

- `Read <path>` — quando sabes o doc exacto
- `Grep <pattern> <path>` — pesquisa por keyword
- `Glob <pattern>` — encontrar ficheiros por padrão

### Ordem operacional típica

1. Identifica natureza da pergunta (V3.3-specific vs doctrinal)
2. Tenta MCP `library_search` (se central) ou `Glob`/`Grep` (se local)
3. Se top-K results não respondem → escala ao `core-librarian` (retrieval avançado)
4. Cita path + linha na resposta

## 4. Como contribuir (onboarding de doc novo)

### Path A: Chat (operacional)

User ou specialist invoca `core-librarian`:

> *"adiciona X à KB local"* (ou *"ingest este URL no central"*)

### 5 Governance Gates (obrigatórios em qualquer onboarding)

| Gate | O que valida | Reject se |
|---|---|---|
| **1. Dedup (SHA-256)** | Hash do content normalizado vs `index.json` | Hash já existe → REJECT (link ao existente) |
| **2. License** | LICENSE file, header, frontmatter | GPL viral, CC-BY-NC, unknown → REJECT/ASK |
| **3. Quality** | Length 500-100k chars, formato MD/TXT, coerente | Binary, PDF não extraído, malformed → REJECT |
| **4. Sensitivity (HARD)** | PII, secrets, customer data, real user IDs | Detectado → HARD REJECT (mesmo se "ignora") |
| **5. Namespace** | Doc pertence à namespace correcta | Errada → mover para namespace certa |

### Após PASS

- `core-librarian` escreve doc no namespace
- Actualiza `index.json` (manifesto + checksum SHA-256 + timestamp)
- Loga em `.nestor/session.log`
- Posta bulletin se afecta outro specialist

## 5. Audit / staleness

### Cadence

- **Manual:** orquestrador pede *"audit da KB"*
- **Weekly (Fase 4+):** automated session sweep

### Output

- Docs > 180 dias sem touch (configurável em `index.json:stale_threshold_days`)
- Docs marcados `superseded` ainda no corpus
- Recomendações: archive / refresh / delete

## 6. Anti-patterns

- Editar `index.json` à mão sem recalcular SHA-256
- Misturar conteúdo cliente-facing com canon interno
- Ingerir URL externa sem validar licença
- Promover doc local para central sem aprovação explícita do user (fronteira é deliberada)
- Skipping sensitivity gate "porque é só interno" — IPs / hostnames internos não
  devem ir para corpus pesquisável sem sanitização

## 7. Estrutura interna

### Local V3.3 (`knowledge_base/`)

```
knowledge_base/
├── index.json                    # manifesto + checksums
├── README.md                     # navegação + contribuição
├── glossary.md                   # termos do domínio
├── architecture/                 # diagramas, pipeline maps V3.3
├── decisions/                    # espelho de docs/adr/ (cópias para retrieval)
├── operations/
│   └── seed/                     # deploy, AD rotation
├── domain/
│   └── seed/                     # KPI catalog, thresholds
├── incidents/                    # post-mortems sanitizados
└── release_notes/
    └── seed/                     # latest release anotado
```

### Central Nestor (`~/.nestor-library/`)

```
.nestor-library/
├── index.json
├── shared/                       # universal canon (OWASP, RFC, CS papers)
└── watcherdb-family/             # cross-tier WatcherDB
    ├── adrs/
    ├── offensive_security/
    ├── pipeline_maps/
    └── runbooks/
```

## 8. References

- `knowledge_base/README.md` — navegação local
- `knowledge_base/index.json` — manifesto local
- `~/.nestor-library/index.json` — manifesto central
- `docs/adr/ADR-002-dual-library-knowledge.md` — decisão arquitectónica
- `.claude/agents/core-librarian.md` — charter completo do curador
