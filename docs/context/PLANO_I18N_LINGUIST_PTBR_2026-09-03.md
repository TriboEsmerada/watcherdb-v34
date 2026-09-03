# Plano: agente linguista i18n + pt-BR como 4.º locale (overlay esparso) — 2026-09-03

Aprovado pelo owner em plan mode (sessão 03/09). Charter do agente: `core-council-architect`.

## Contexto

- Pergunta do owner: "já temos um agente especialista em idiomas EN / pt-BR / pt-PT / ES?" → **não**.
  Só existia `v33-i18n-coverage` (mecânico: chaves em falta + hardcoded). Ninguém auditava qualidade.
- Decisões do owner: agente linguista novo; `pt.json` = pt-PT pós-AO90 (norma 2026-08-16);
  **pt-BR passa a existir como opção**; es neutro LATAM; en-US; glossário em
  `knowledge_base/domain/i18n_glossary.md`; **acentuação rigorosa** (pedido explícito mid-sessão).
- Medições (1715 chaves-folha por locale): pt.json pendia para pt-BR (usuário 19 vs utilizador 5,
  arquivo 7 vs ficheiro 3, configurações 7 vs definições 0). Candidatos a acento em falta: pt 195
  chaves, es 313. 211 chaves com pt == en.
- Incoerências apanhadas: docstring do motor dizia "PT-BR (default)"; selector mostrava 🇧🇷 na opção
  pt com `lang="pt-BR"` enquanto o HTML declara `lang="pt-PT"`; 3 ciclos de idioma com
  `['pt','en','es']` e `% 3` hardcoded; `pt.json` tem chaves duplicadas (`effort_label`/`impact_label`
  ~1656 e ~1787-1788) — por isso o script edita por texto, nunca por round-trip JSON.

## Design do 4.º locale

O motor (`static/js/watcherdb_i18n_v2.js`) já resolve fallback **por chave** e o template já cai em
pt nos dicionários inline (`kpi.i18n[lang]`). Logo `pt-BR.json` é overlay esparso:
`FALLBACK_CHAIN['pt-BR'] = ['pt-BR', 'pt']`. Custo ≈ 100 overrides em vez de 1715 chaves.

## Entregáveis desta sessão

| Ficheiro | Estado |
|---|---|
| `.claude/agents/v33-i18n-linguist.md` | escrito (charter + regra de acentos P1 + lotes A-E) |
| `.claude/agents/v33-i18n-coverage.md` | actualizado (overlay pt-BR, handoff ao linguista) |
| `docs/context/I18N_PTBR_PASSO1_apply.py` | script de aplicação (28 patches + CHANGELOG + lote A + glossário); validado em cópia scratchpad |
| `docs/context/I18N_PTBR_LOTE_A.json` | saída do linguista: 98 fix / 7 neutral / 3 falsos positivos |
| `docs/context/I18N_PTBR_PASSO2_commit.ps1` | commit |
| `docs/context/PROMPT_PROPAGACAO_V6_I18N_PTBR_2026-09-03.md` | regras 3-4 do owner |

Ficheiros que o PASSO 1 toca (owner executa; hook impede a AI): `static/js/watcherdb_i18n_v2.js`,
`templates/watcherdb_portal.html`, `scripts/i18n_validate.py`, `tests/unit/test_i18n_parity.py`,
`docs/FEATURE_MATRIX.md`, `docs/AGENTS_GUIDE.md`, `docs/adr/ADR-001-council-composition.md`,
`docs/changelog/CHANGELOG.md`, `static/i18n/pt.json`; cria `static/i18n/pt-BR.json` e
`knowledge_base/domain/i18n_glossary.md`. `--nestor` actualiza `council_v33_local.md` central.

## Execução (owner)

```
python docs/context/I18N_PTBR_PASSO1_apply.py --dry-run
python docs/context/I18N_PTBR_PASSO1_apply.py --nestor
python -m pytest tests/unit/test_i18n_parity.py -q      # 6 passed
python scripts/i18n_validate.py                          # 0 errors
.\docs\context\I18N_PTBR_PASSO2_commit.ps1
```
Depois: `v33-knowledge-base-curator` para `knowledge_base/index.json`; DEV 8443 → selector com 4
opções, "Português (Brasil)" muda só os overrides, F5 mantém escolha, ciclo do relatório KPI
percorre 4 línguas. O agente `v33-i18n-linguist` só fica invocável na **próxima sessão** (o harness
carrega `.claude/agents/` no arranque); nesta sessão correu via agente genérico com o charter.

## Decisões tomadas pelo orquestrador (rotina, reversíveis)

- `alwayson.fetch_primary_title`: "Obter dados completos do nó primário" (verbo é fetch, não pesquisar).
- `log.cat_click_to_fetch` / `log.cat_fetch_error` mantêm registo informal pré-existente ("clica",
  "Tenta") — fora do escopo do lote A; candidato a lote de tom.

## Pendentes (lotes do linguista, GO por lote)

- **B** acentuação: pt 195 / es 313 chaves candidatas (falsos positivos: "esta" demonstrativo, tempdb).
- **C** es ibérico → neutro. **D** en-GB → en-US. **E** 211 chaves pt == en (traduzir vs termo técnico).
- Gerúndios pt-BR fora da lista A (ex.: `overview.alwayson_check` "Verificando…") e família
  detectado/detetado noutras chaves — apanhar no lote B.
- Rollback do PASSO 1: ver docstring do script (git checkout dos 9 ficheiros + git clean dos 2 novos).
