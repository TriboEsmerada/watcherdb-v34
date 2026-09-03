# Bootstrap Prompt — Nestor Council para WatcherDB V3.3

**Como usar:** abrir Claude Code com `cwd` na raiz do repositório V3.3 (não no `watcherdb-council`)
e colar o bloco abaixo na primeira mensagem. O orquestrador faz o resto.

> Nota: a primeira execução cria ficheiros (`.claude/agents/*.md`, `docs/`, `findings-inbox.md`).
> Aprovar permissões de Write quando forem pedidas.

---

## PROMPT (copiar a partir daqui)

```
Quero que estabeleças neste projecto WatcherDB V3.3 o mesmo padrão de council
que já uso no projecto-mãe `watcherdb-council` (framework Nestor). Lê primeiro
e depois executa em fases, a pedir confirmação entre fases grandes.

CONTEXTO DO PADRÃO (Nestor v1.3)
================================

O modelo é: ORQUESTRADOR (Claude main) + COUNCIL (multi-persona specialists)
+ MICRO-AGENTS (single-task helpers). O orquestrador é quem fala comigo, tem
context completo, tem Edit/Write/Bash, e decide quando delegar. Todos os
specialists/micro-agents são read-only por design — produzem texto, diffs,
pareceres; o orquestrador é que aplica.

Camadas:

  1. CORE ARCHETYPES (fixos em qualquer projecto Nestor)
     - core-council-architect: meta-agent que propõe composição de council
       quando arranca projecto novo ou se rever. Read-only.
     - core-librarian: corpus governance (dedup, license, quality, sensitivity,
       namespace), retrieval avançado, audit de staleness. Único core com
       Write (ingere docs externos). Tem WebFetch.

  2. DOMAIN SPECIALISTS (variam por projecto)
     Multi-persona (3-4 hats), scope profundo, read-only. Para V3.3 a
     composição deve ser:
       - watcherdb-v33-specialist: owner do scope V3.3 Standard Edition
         (Feature Matrix Std vs Pro, SPA watcherdb_portal.html, FastAPI
         routers, Performance module, Windows service porta 8433, auth
         híbrida AD). Personas: Senior Backend + DBA Domain Expert +
         Std/Pro Tier Curator.
       - watcherdb-frontend-specialist: SPA, Jinja2, Chart.js, modais,
         CSS híbrida, WCAG 2.1 AA, vanilla JS por design (on-premise
         footprint). Personas: Frontend Eng + UX Designer + Accessibility
         Auditor + Design System Architect.
       - watcherdb-deploy-architect: PyArmor Pro (reg 11618), Windows
         services, Task Scheduler, AD service accounts least-privilege,
         DDL orchestration, upgrade/rollback. Personas: Release Eng +
         Windows Sysadmin + AD/Security + DBA + SRE.
       - watcherdb-qa-specialist: test strategy, regression health,
         coverage gaps, pre-commit hooks, quality gates. Personas: QA Eng
         + Test Architect + Release Gate Keeper. Pattern: dois olhares por
         teste — técnico + utilizador final crítico (DBA cliente).
         Veredicto = MIN(tech, user).
       - watcherdb-security-auditor: STRIDE, OWASP Top 10, CVE monitoring,
         RBAC review, banking-grade compliance (SOC 2, ISO 27001, PCI-DSS,
         GDPR). Personas: CISO + AppSec Eng + Compliance + Red Team
         mindset. Tem WebSearch (CVE lookups).
       - watcherdb-customer-success-persona: representa o DBA cliente
         pagante. Avalia features antes de ship como se estivesse em prod
         real. Distinto de frontend (esse é visual/CSS) e qa (esse é tests
         formais) — ângulo "cliente real a pagar licença".
       - watcherdb-v1-intel-specialist: collector + infra partilhada
         (BD WatcherDB_Intelligence, usp_swap_kpi_stg_tables, pares
         BLUE/GREEN). Tem direito de veto em mudanças à infra partilhada
         porque V1 é shared com V5/V5.5/V6.

  3. MICRO-AGENTS (tier leve, single-task)
     Um único objectivo, um único output, charter de 1 frase. Read-only.
     Para V3.3 sugere e cria pelo menos:
       - v33-feature-matrix-checker: dado um diff, valida se respeita
         FEATURE_MATRIX.md (Std vs Pro). Output: PASS/FAIL + linhas
         a corrigir.
       - v33-changelog-assistant: dado git log range, propõe entrada
         RELEASE_NOTES no estilo do projecto.
       - v33-port-collision-checker: scan rápido das portas usadas
         (8433 V3.3, 8443 DEV, 8449 V3.2, 8450 V5, 8452 AI Exp, 8460 V6,
         8555 V5.5, 8660 V6 main) e flag de colisão.
       - v33-i18n-coverage: dado um template HTML alterado, lista chaves
         pt-PT/pt-BR/en-US em falta.
       - v33-modal-auth-gate-checker: confirma que modais novos têm
         data-admin-gated quando tocam endpoints _require_admin.

  4. CROSS-PRODUCT (opcional, partilhados com outros projectos)
     Só criar se este projecto for usar. Provavelmente úteis em V3.3:
       - ai-systems-architect (decisões AI/LLM cross-product, com WebSearch)
       - python-packaging-architect (packaging → exe, PyArmor, installers)
     Se forem só lidos a partir do projecto-mãe (já existem em
     ~/.claude/agents/), não duplicar — referenciar.

PADRÕES OPERACIONAIS (não negociáveis)
=======================================

  - Pattern #7 (Cross-Cutting Consensus): para decisões que tocam mais que
    um specialist, dispatch em PARALELO (mesma message, múltiplos Agent
    tool calls), depois sintetizar consenso/dissenso. Ex.: feature nova
    Std/Pro = v33 + frontend + qa + customer-success + security em
    paralelo.

  - Ground truth document (FEATURE_MATRIX.md em V3.3): canonical source
    para tier Std vs Pro. Specialists têm de citar este doc; orquestrador
    valida divergências.

  - ADRs (Architectural Decision Records) em `docs/adr/ADR-NNN-titulo.md`,
    template em `docs/ADR-template.md`. Cada decisão grande (porta, auth,
    migration model, package format) → ADR.

  - Findings Inbox (`findings-inbox.md` na raiz): specialists fazem
    PROACTIVE FINDINGS sem espera. Formato: ID FIND-YYYYMMDD-NNN, severity
    P0/P1/P2, owner specialist, evidence path, recommendation. Triagem
    semanal.

  - Proactive Council (5 triggers, sem o user pedir):
      (1) session sweep no início — orquestrador relê last 3 commits e
          dispatcha specialists relevantes para flag regressions.
      (2) sprint milestone — qa + security + customer-success review
          antes de tag.
      (3) market scan — semanalmente marketing-strategist (se existir)
          + ai-systems-architect.
      (4) feature ideation — quando o user lança ideia, frontend +
          customer-success + tier-curator review fit.
      (5) architectural review — sempre que diff toca >3 ficheiros core.

  - Velocity Pact: aprovação tácita por escopo. Avança no escopo
    autorizado, pára em mudança de rumo, sempre confirma em irreversível
    (rm -rf, push --force, drop table, alteração de infra partilhada V1).

  - Specialist depth-of-analysis: bugs end-to-end devem ser estudados
    end-to-end (auth, session, data flow) antes de emitir parecer. Não
    aceitar análise superficial.

  - Sprint progress reporting: durante sprints autorizados, reportar
    formato `[PROGRESS HH:MM]` % geral + % sprint a cada ~5min.

BIBLIOTECAS DE CONHECIMENTO (DUAL-LIBRARY PATTERN)
====================================================

Os specialists têm de saber consultar DUAS bibliotecas com regras claras:

  A. BIBLIOTECA CENTRAL — Nestor Library (cross-project)
     Path: `C:\Users\ue_e-snetto\.nestor-library\`
     Namespaces existentes:
       - shared/                 (cross-project canon)
           offensive_security/   (OWASP WSTG, HackTricks, etc.)
           owasp_cwe/            (CWE Top 25, OWASP Top 10)
           pyarmor_pro/          (PyArmor Pro docs/licensing)
           python_packaging/     (PyInstaller, Nuitka, packaging canon)
           sql_server_ref/       (SQL Server reference)
       - watcherdb-family/       (compartilhado V3.3, V5, V5.5, V6, V1)
           adrs/                 (ADRs cross-product)
           offensive_security/   (red team runbooks, attack surface maps)
           pipeline_maps/        (canonical pipeline maps)
           runbooks/             (operational runbooks)
     MCP tools (preferenciais quando disponíveis):
       - mcp__nestor-library__library_search    (semantic + keyword)
       - mcp__nestor-library__library_list_docs (inventário)
       - mcp__nestor-library__library_health    (status do índice)
     Fallback: Read/Grep/Glob directos no path.

  B. BIBLIOTECA LOCAL V3.3 — knowledge-base do projecto
     Path: `<repo>/knowledge_base/`  (ou `nestor_library_local/` se preferires
     consistência de naming com o projecto-mãe)
     Estrutura:
       knowledge_base/
         index.json                    # manifesto de docs com checksums
         README.md                     # como navegar / contribuir
         architecture/                 # diagramas, pipeline maps V3.3
         decisions/                    # ADRs locais (espelho de docs/adr/)
         operations/                   # runbooks específicos V3.3 (deploy,
                                       # rollback, AD service account rotation)
         domain/                       # SQL Server domain knowledge V3.3
                                       # (KPI definitions, threshold rationale,
                                       # collector patterns)
         incidents/                    # post-mortems V3.3 (sanitizados)
         release_notes/                # histórico de releases anotado
         glossary.md                   # termos do domínio (DBA + SQL Server +
                                       # WatcherDB-specific)
         seed/                         # 3-5 docs iniciais para arrancar
                                       # vazia não serve — precisa seed

REGRAS DE PRECEDÊNCIA (não negociáveis para specialists)
---------------------------------------------------------

  1. Pergunta V3.3-específica (KPI behaviour, Std vs Pro, modal X,
     porta 8433, AD config V3.3) → consultar BIBLIOTECA LOCAL primeiro.
     Só escalar para central se local não cobre.

  2. Pergunta cross-product / doctrinal (PyArmor, packaging Python,
     OWASP, SQL Server reference, padrões de attack surface) →
     consultar BIBLIOTECA CENTRAL directamente.

  3. Conflito entre local e central → local ganha para V3.3-specific,
     central ganha para canon doctrinal. Em dúvida, citar ambos e
     levantar findings (FIND-YYYYMMDD-NNN).

  4. Ground truth doc (`docs/FEATURE_MATRIX.md`) tem precedência sobre
     qualquer biblioteca para tier Std vs Pro.

  5. Specialists devem CITAR a fonte na resposta (path do doc + linha).
     Pareceres sem citação são rejeitados pelo orquestrador.

CHARTER DOS SPECIALISTS — secção obrigatória
---------------------------------------------

Adicionar a cada agent.md (specialists e micro-agents) bloco fixo:

  ## Knowledge sources

  - **Local first** (`<repo>/knowledge_base/`): consultar antes de
    responder a qualquer pergunta V3.3-specific.
  - **Central** (`C:\Users\ue_e-snetto\.nestor-library\`): canon
    cross-product — usar via MCP `mcp__nestor-library__library_search`
    se disponível, fallback Read/Grep.
  - **Ground truth**: `docs/FEATURE_MATRIX.md` para tier Std/Pro.
  - Citar sempre fonte no parecer (path + linha). Sem citação =
    parecer inválido.

ESTRUTURA A CRIAR
==================

  .claude/
    agents/
      core-council-architect.md
      core-librarian.md                   # gere AMBAS as bibliotecas
                                          # (ver charter dual-library abaixo)
      watcherdb-v33-specialist.md
      watcherdb-frontend-specialist.md
      watcherdb-deploy-architect.md
      watcherdb-qa-specialist.md
      watcherdb-security-auditor.md
      watcherdb-customer-success-persona.md
      watcherdb-v1-intel-specialist.md
      v33-feature-matrix-checker.md       # micro-agent
      v33-changelog-assistant.md          # micro-agent
      v33-port-collision-checker.md       # micro-agent
      v33-i18n-coverage.md                # micro-agent
      v33-modal-auth-gate-checker.md      # micro-agent
      v33-knowledge-base-curator.md       # micro-agent (mantém index.json
                                          # da KB local actualizado)
    settings.json.example                 # permissions baseline
                                          # (incluir permissão MCP nestor-library)

  docs/
    AGENTS_GUIDE.md                       # quem é quem, quando invocar
    ARCHITECTURE.md                       # high-level V3.3
    PROACTIVE_COUNCIL.md                  # 5 triggers + cadence
    HANDOFF_CONTRACT.md                   # formato brief self-contained
    BULLETIN_FORMAT.md                    # findings/parecer format
    KNOWLEDGE_BASE_GUIDE.md               # como usar dual-library +
                                          # precedência + onboarding de docs
    ADR-template.md
    FEATURE_MATRIX.md                     # ground truth Std vs Pro
    adr/
      ADR-001-council-composition.md      # primeira ADR: porque estes specialists
      ADR-002-dual-library-knowledge.md   # decisão: KB local + central
    architecture/
      V33_PIPELINE_MAP.md                 # boot, request lifecycle, auth, KPI flow

  knowledge_base/                         # BIBLIOTECA LOCAL V3.3
    index.json                            # manifesto + checksums
    README.md                             # navegação + contribuição
    architecture/                         # vazia inicialmente
    decisions/                            # vazia inicialmente
    operations/
      seed/
        deploy_runbook_v33.md             # SEED — extrair do código
        ad_service_account_rotation.md    # SEED
    domain/
      seed/
        kpi_catalog_v33.md                # SEED — KPI cards V3.3 com
                                          # thresholds + rationale
    incidents/                            # vazia (privacy-first)
    release_notes/
      seed/
        latest_release_anotado.md         # SEED — última release com
                                          # commentary do council
    glossary.md                           # SEED — DBA + SQL Server +
                                          # WatcherDB termos

  findings-inbox.md                       # vazio com header + formato

PROCEDIMENTO
=============

Faz pelas seguintes fases, parando para eu confirmar entre as fases marcadas
[STOP]:

  Fase 0 — Discovery (sem escrever)
    - lê `c:\Users\ue_e-snetto\Documents\projetosPython\watcherdb-council\docs\AGENTS_GUIDE.md`
    - lê `c:\Users\ue_e-snetto\Documents\projetosPython\nestor-template\.claude\agents\*` (templates EXAMPLE)
    - lê os charters dos specialists relevantes em `~\.claude\agents\watcherdb-*.md`
      (já existem com scope cross-product — vou querer cópias scope-V3.3)
    - inventaria estado actual do repo V3.3: já existe `.claude/agents/`?
      `docs/`? `findings-inbox.md`? FEATURE_MATRIX.md?
    - reporta gap analysis em ≤200 palavras.
    [STOP] espera autorização para Fase 1.

  Fase 1 — Core archetypes + V3.3 specialist + KB local seed
    - cria `.claude/agents/core-council-architect.md`.
    - cria `.claude/agents/core-librarian.md` ADAPTADO para gerir DUAS
      bibliotecas: central (`~\.nestor-library\`) + local (`./knowledge_base/`).
      Charter inclui:
        * onboarding de docs com governance gates (dedup, license,
          quality, sensitivity, namespace)
        * routing por precedência (regras 1-5 acima)
        * staleness audit (timestamps no index.json)
        * uso preferencial dos MCP tools `mcp__nestor-library__*`
      Único agent com Write capability (limitado a `knowledge_base/` e
      `nestor_library/` se existir).
    - cria `.claude/agents/watcherdb-v33-specialist.md` com scope LOCAL
      ao repo V3.3 (não cross-product). Multi-persona, charter completo,
      Read/Grep/Glob/Bash. Inclui secção "Knowledge sources" com
      regras de precedência.
    - cria estrutura `knowledge_base/` com index.json vazio + README.md
      + glossary.md seed.
    - cria 3-5 SEED docs em `knowledge_base/.../seed/` extraindo do
      código actual (KPI catalog, deploy runbook, AD rotation, latest
      release notes anotado). NÃO inventar — só extrair o que está
      no código + commits.
    - cria `docs/KNOWLEDGE_BASE_GUIDE.md` (precedência + onboarding).
    - cria `docs/adr/ADR-002-dual-library-knowledge.md`.
    - cria `findings-inbox.md` vazio com header.
    - cria `docs/AGENTS_GUIDE.md`, `BULLETIN_FORMAT.md`, `ADR-template.md`.
    - smoke test: dispatcha v33-specialist com 2 perguntas:
        (a) "qual a porta do windows service e onde está documentada?"
            → deve consultar KB local primeiro, citar fonte.
        (b) "qual a licensing strategy do PyArmor Pro?"
            → deve consultar biblioteca central, citar fonte.
      Mostra-me ambas as respostas.
    [STOP] espera autorização para Fase 2.

  Fase 2 — Council completo (5 specialists adicionais)
    - cria frontend / deploy / qa / security / customer-success.
    - cria v1-intel-specialist (com nota de veto em infra partilhada).
    - cria `docs/PROACTIVE_COUNCIL.md` (5 triggers documentados).
    - cria `docs/HANDOFF_CONTRACT.md` (formato brief self-contained).
    - cria `docs/FEATURE_MATRIX.md` STUB se não existir (preencho eu
      depois).
    - cria `docs/adr/ADR-001-council-composition.md` (porque estes 7
      specialists, alternativas consideradas, decisão).
    [STOP] espera autorização para Fase 3.

  Fase 3 — Micro-agents (tier leve)
    - cria os 6 micro-agents listados acima (incluindo
      v33-knowledge-base-curator que mantém index.json sincronizado
      com checksums dos ficheiros em knowledge_base/).
    - cada micro-agent charter ≤200 palavras, output format obrigatório,
      bloco "Knowledge sources" curto a apontar KB local primária.
    - documenta no AGENTS_GUIDE.md secção "Micro-agents".
    - smoke test: dispatcha v33-port-collision-checker e
      v33-knowledge-base-curator. Mostra output.
    [STOP] espera autorização para Fase 4.

  Fase 4 — Architecture map + first proactive sweep + KB hydrate
    - cria `docs/architecture/V33_PIPELINE_MAP.md` (boot, request
      lifecycle, auth flow, KPI collection→display).
    - core-librarian executa "KB hydrate run":
        * inventaria docs/ existentes
        * promove os relevantes para `knowledge_base/` com governance gates
        * actualiza index.json com checksums + timestamps + tags
        * gera relatório de gaps (ex.: "incident postmortems vazios",
          "KPI catalog cobre 12/20 cards") em findings-inbox.md
    - executa primeiro PROACTIVE COUNCIL session sweep:
      lê last 5 commits, dispatch v33+frontend+qa em paralelo,
      cada specialist consulta KB local + central, reporta findings
      em `findings-inbox.md` com citações de fontes.

REGRAS DE OURO
===============

  - Cada agent.md em `.claude/agents/` segue formato YAML frontmatter:
      ---
      name: <nome>
      description: <quando invocar — específico, sem fluff>
      tools: Read, Grep, Glob, Bash    # read-only por default
      ---
      <charter detalhado: persona(s), scope, ground truth, anti-patterns,
       quando NÃO invocar>

  - Specialists scope-V3.3 NÃO devem mencionar V5/V5.5/V6 senão como
    "fora de scope, escalar para watcherdb-council mãe".

  - Micro-agents charter ≤200 palavras, output format obrigatório.

  - Nada de emojis nos ficheiros (excepto se eu pedir).

  - Não adicionar comentários explicativos ao código existente.
    Tocar só onde acrescentas valor.

  - Confirmar antes de qualquer commit. Eu autorizo.

Começa pela Fase 0 — Discovery. Reporta gap analysis e pergunta antes de
avançares.
```

---

## Variantes

**Versão curta (se quiseres setup mínimo, só v33-specialist):** apaga as Fases
2-4 e mantém só Fase 0+1.

**Versão "from-template" (se quiseres copiar mais directo de nestor-template):**
substitui Fase 1 por:

> Fase 1 — copia e adapta de `nestor-template/.claude/agents/`:
> core-council-architect.md, core-librarian.md, EXAMPLE-domain-specialist.md
> → renomeia para watcherdb-v33-specialist.md, ajusta scope.

**Para outros projectos (V5, V5.5, V6, V1, AoLado, Polo):** reutiliza este
prompt, troca "V3.3 Standard Edition / porta 8433 / FEATURE_MATRIX Std vs Pro"
pelo scope do projecto-alvo. A lista de micro-agents também muda.
