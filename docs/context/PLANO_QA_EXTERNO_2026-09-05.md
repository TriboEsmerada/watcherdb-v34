# Plano de execução — QA externo vs. council (revisão 2026-09-05)

Origem: plano do owner (05/09) revisto pelo orquestrador com core-council-architect e
watcherdb-qa-specialist. Charter do agente: `.claude/agents/qa-externo.md`.
Objetivo: transformar "o council diz X, o QA diz Y" em vereditos medidos, com um gate
permanente por afirmação, sem que o owner seja o copy-paste entre os dois lados.

## 0. Setup

| Item | Estado 05/09 |
|---|---|
| `.claude/agents/qa-externo.md` instalado com correções (secção 0 override do CLAUDE.md; porta 8434 obrigatória; output sem hostnames/instâncias/tokens; UA próprio; A-1/A-2/A-3 reformuladas) | FEITO |
| Pastas `scripts/qa/runtime/` (+ .gitkeep) e `docs/qa/externo/` | FEITO (owner) |
| `docs/qa/externo/` no `.gitignore` até o repo ser privado | FEITO (owner) |
| Hook `guard_write_paths.py` repointado para a cópia V3.4 + prefixos `docs/qa/externo` e `scripts/qa/runtime` | FEITO |
| `tests/integration` fora de `testpaths` | JÁ ESTAVA (movido para `scripts/manual_debug/integration`, commit 89d5be9) |
| Conta `qa_viewer` a responder em **8434** | **NÃO CONFIRMADO** — o curl de 05/09 correu com `<host>` literal e devolveu vazio; repetir com o host real antes da pauta 1 |
| Env `WATCHERDB_QA_URL` (8434), `WATCHERDB_QA_USER`, `WATCHERDB_QA_PASS` fora do repo | owner, por sessão |
| Commit do charter + hook + CONTEXT | owner (regra 3) |

## 1. Barramento entre as duas sessões (decisão)

- **Sessão 1**: esta (VS Code), orquestrador + council.
- **Sessão 2**: terminal `claude` na raiz do repo, primeira mensagem `use o agente qa-externo; pauta 1`.
  Sessões Claude Code locais vêem-se em ListAgents e trocam mensagens (verificado 05/09).
- **O Claude da extensão Chrome NÃO é sessão 2.** Não tem endereço para SendMessage e, no
  estado de 05/09, estava a medir em 8433 com a sessão ADMIN do owner: viola duas regras do
  charter. Só entra se ligado ao PC ("Link to this computer"), e aí é uma sessão Claude Code
  como outra qualquer, sujeita ao mesmo charter.
- Fallback: sessão 2 escreve `docs/qa/externo/<data>-pauta-<n>.md`; sessão 1 lê o ficheiro.

## 2. Ciclo por afirmação

| Passo | Quem | O que faz | Limite |
|---|---|---|---|
| 1 | qa-externo | Reformula, mede no fonte e no runtime (8434), emite bloco A-n | 1 afirmação por vez |
| 2 | council | Agente dono do tema responde com `ficheiro:linha` + teste, ou concede | 1 ronda |
| 3 | qa-externo | Aceita, ou contesta com nova medição (não com argumento) | até 3 rondas |
| 4 | qualquer | Sem acordo à 3.ª: TESTE EM FALTA + esqueleto + "DECISÃO DO OWNER" | — |
| 5 | owner | Lê só os blocos com DECISÃO DO OWNER; decide; council leva ao CONTEXT | — |

Regras (as originais + 4 do qa-specialist, aceites em 05/09):
- Ninguém ganha por citar decisão anterior, data ou "desenho deliberado". Só teste.
- **Runtime resolve "o que acontece"; não resolve "se é bug".** Se o council alega decisão de
  produto, não a "explica" ao QA: escala como DECISÃO DO OWNER (precedente 16/08: viewer a ver
  SQL text era decisão, não bug).
- **Medição reprodutível**: repetir 3×; se varia, é flaky e fica registado como tal, não "ganha"
  (precedente 17/08: pool starvation degradou respostas sem ser bug de app).
- **Gate com owner e prazo.** Cada CONFIRMADO/PARCIAL termina num gate com nome de quem o cria e
  data limite. Sem prazo o gate vira TESTE EM FALTA permanente (precedente: P0-2 pywin32, 6 semanas).
- **Verde tem de ser verde.** Toda a pauta que valida "OK" visual/HTTP confirma que o success
  não é fetch engolido (`.catch(()=>null)` → cartão verde, achado de 17/08).

## 3. Calendário das pautas

| Quando | Pauta | Afirmações | Onde vive o gate |
|---|---|---|---|
| Antes do dia 3 | **P1** | A-1 CSRF same-site (classificar 39 endpoints: exposto = sem `require_same_origin` E sem corpo JSON obrigatório) · A-2 LIVE mono por herança (`#liveBtn` → `#live-tv-modal`) · A-3 tamanhos fora da escala de tokens (o ×1.001 é zoom) | A-1: `tests/` unitário sobre routers (CI). A-2/A-3: `scripts/qa/runtime/` |
| Dia 2 | **P2** | Trusted_Connection nos sítios vivos; pré-flight de permissões `sql_monitoring` nas 63 instâncias | `scripts/qa/runtime/` (precisa de PRD; CI não tem serviço nem BD) · owner + prazo |
| Dias 4–5 | **P3** | `destroyTabCharts` desligado; soak 3×1h, troca de tab a cada 10 s | `scripts/qa/runtime/` (Playwright headless + CDP) · owner + prazo |
| Dia 3 ou 8 | **P4** | reset-password não revoga JWT; token em localStorage E cookie; logout limpa ambos? | `tests/` unitário onde possível; resto `scripts/qa/runtime/` |
| Dia 8 | **P6a** | Reconciliação KPI **snapshot** (backup/CHECKDB/suspect) em 10 instâncias, tolerância 0 | `scripts/qa/runtime/` · owner + prazo |
| Dia 9 | **P6b** | Reconciliação KPI **de janela** (bloqueios/deadlocks) em 10 instâncias, tolerância `max(2 eventos, 5%)`, **mesma janela UTC exata** nas duas queries | `scripts/qa/runtime/` · owner + prazo |
| Dia 11 | **P5** | `innerHTML` que recebem dados de instância: lista exata | `tests/` (grep estático) |

Métrica do soak P3 (não adjetivos): amostra a cada 10 s via CDP `Performance.getMetrics`
(JSHeapUsedSize) e `Memory.getDOMCounters` (nodes); leak fechou se o declive da regressão linear
do heap na última hora não é significativamente positivo E os nós DOM voltam a ±10% do baseline
após cada `destroyTabCharts`, sem crescimento monótono.

`tests/e2e` só recebe gates quando existir job de CI que arranque a app de facto (hoje não
existe); criar gate e2e antes disso repete P0-1 (testes que nunca correm).

Cada pauta: meio dia de sessão 2, uma ronda do council, no máximo 20 min do owner. Se uma pauta
ultrapassa um dia, a afirmação está mal formulada: parte-a.

## 4. Critérios de fecho de cada pauta

- Todos os blocos A-n com veredito e "Fecha com" preenchido (teste + onde vive + owner + prazo).
- `docs/qa/externo/<data>-pauta-<n>.md` gravado pela sessão 2, linha 1 = versão/porta medida,
  sem hostnames/instâncias/tokens.
- Council regista uma linha no CONTEXT com os vereditos (nunca o qa-externo).
- Pelo menos um gate novo por pauta, com owner e prazo.

## 5. Sinais de que a montagem está a falhar

- **qa-externo concorda com tudo** → verificar se leu `docs/context`. Se leu, matar a sessão 2 e
  abrir outra; contexto contaminado não se limpa.
- **council responde com datas e SHAs** → devolver com "ficheiro:linha ou TESTE EM FALTA".
- **pauta com mais de 3 rondas** → falta teste, não argumento.
- **owner a colar texto entre janelas** → usar o fallback por ficheiro.
- **contexto da sessão 2 a esgotar** → uma pauta por sessão; nunca reaproveitar.

## 6. Custo esperado

Sete pautas (P6 partida) × (meio dia de sessão 2 + uma ronda do council) ≈ 3,5 dias de agente e
~2,5 h do owner em 3 semanas.
