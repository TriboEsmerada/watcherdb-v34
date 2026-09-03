# Subagents do WatcherDB V3.3 para Claude Code / VS Code

Conjunto de **6 subagents** com roteamento por modelo, todos com as regras
READ-ONLY / Advisor-Never-Executor / `sql_monitoring` embutidas.

Origem: pacote adaptado do V6 em 2026-06-11 (ver
`WATCHERDB_V6/docs/ai/SUBAGENTS_PACK_README.md`). Diferenças nesta edição:

- **`nlu-prompt-engineer` NÃO instalado** — AI é Pro-only; V3.3 Standard
  não tem runtime de IA (tier discipline, `docs/FEATURE_MATRIX.md`).
- Agentes referenciam a stack real do V3.3: pyodbc via
  `execute_on_intelligence()` (`api/connection_pool.py:798`), portal SPA
  `watcherdb_portal.html`, serviço porta 8433, BD partilhada
  `WatcherDB_Intelligence` (veto do V1 collector).
- `architecture-advisor` e `test-generator` vigiam **tier leak**
  (feature Pro a vazar para a Standard).

## Mapa de roteamento

| Agente | Modelo | Quando dispara |
|---|---|---|
| code-explorer | haiku | grep, localizar código, leitura rápida |
| test-generator | sonnet | criar/ampliar suítes pytest |
| docs-writer | sonnet | CLAUDE.md, ADRs, READMEs, runbooks, docs comerciais |
| sql-deep-reviewer | inherit | tuning T-SQL, planos de execução, schema Intelligence |
| architecture-advisor | inherit | ADRs, design SPA/routers, evolução Standard |
| incident-forensics | inherit | post-mortems, root-cause, failovers AG, collector silence |

`inherit` = usa o modelo da sessão principal.

## Fronteiras com o council existente (anti-colisão de roteamento)

- `test-generator` → gerar testes; estratégia QA/gates é do `watcherdb-qa-specialist`.
- `docs-writer` → redigir docs; CHANGELOG de release é do `v33-changelog-assistant`.
- `architecture-advisor` → design; classificação tier Std/Pro é do
  `watcherdb-v33-specialist` + `v33-feature-matrix-checker`.
- `code-explorer` → só localizar/ler.

## Avisos

- NÃO defina a variável de ambiente `CLAUDE_CODE_SUBAGENT_MODEL`:
  ela sobrescreve o modelo de TODOS os agentes e quebra o roteamento.
- Verifique a instalação com `/agents` dentro do Claude Code (pode ser
  necessário reiniciar a sessão).
