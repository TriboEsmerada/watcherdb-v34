# Plano QA externo v2 — o que falta implementar (2026-09-07)

Substitui a secção 3 (calendário) de `PLANO_QA_EXTERNO_2026-09-05.md`; o resto daquele documento
(setup, barramento, ciclo, regras, critérios de fecho, sinais de falha) continua válido.
Revisto com watcherdb-qa-specialist em 07/09. Panorama apresentado em cada fecho de ronda.

## 0. Estado de partida

| Item | Estado |
|---|---|
| Pauta 1 (A-1 CSRF, A-2 LIVE, A-3 escala) | 3 rondas; A-1 e A-2 fechadas em fonte+testes+runtime não autenticado; falta a ronda 4 autenticada (cookie em runtime, tabela LIVE com dados, KPIs/Overview) |
| Conta `qa_viewer` | Bloqueada; password divergente entre janelas. Reset na UI zera o contador |
| Lotes shipped a partir da pauta 1 | CSRF middleware (0999245), cookie (1e47802), LIVE tipografia (af3a505, a776336) |
| Gates existentes | 21 testes unitários novos; 2 scripts em `scripts/qa/runtime/` |
| Repo | Público; 7 commits por enviar; decisão de privar pendente desde 04/09 |
| CI | LOTE0 correu e falhou em Linux (pyodbc sem unixodbc; import Windows-only na colecção); hotfix PASSO3/4 escrito por outra sessão em 05/09 23:47, NÃO aplicado |

## 1. Regras novas (acrescentam-se às de 05/09)

- **Nunca asserir valores literais de PRD.** Jornadas e gates asserem invariantes: selector existe,
  contagem ≥ 0 e do mesmo tipo antes/depois, 0 erros de consola, 0 respostas 5xx, tempo por passo
  dentro de orçamento. Valores literais só contra o canário sintético (secção 4).
- **Bloqueante vs consultivo.** Cada gate declara o que trava (P0/P1, violações axe serious/critical,
  mensagem de erro sem próxima acção) e o que é só delta acompanhado (rótulos, glossário, minor).
- **Acesso à BD só pela mão do owner.** O QA nunca liga à BD. O owner corre os SELECTs canónicos e
  grava `docs/qa/externo/<data>-p6-<instancia>.csv` com colunas
  `instancia,kpi,query_hash,valor,collected_at_utc` (sem SQL text). O QA compara com a UI.
- **Janela de comparação.** P6b: mesma janela UTC exacta nas duas queries. P6a (snapshot): ≤ 2 min
  entre SELECT e screenshot.
- **Foco visível mede-se a sério.** axe-core chega para contraste; foco valida-se com Tab via
  Playwright + `getComputedStyle(el).outline !== 'none'`. Confirmar versão do axe antes de assumir
  cobertura de `target-size`.

## 2. Sequência (3 semanas, ~20 min/dia do owner)

| # | Pauta | Afirmações a medir | Bloqueante | Exige do owner | Gate |
|---|---|---|---|---|---|
| 1 | **P1 ronda 4** | cookie em runtime; LIVE com dados; KPIs/Overview ⊆ escala; #liveBtn viewer | — | reset password + login validado na mesma shell | já existem (`qa_ext_*`) |
| 2 | **P2 credenciais/BD** | Trusted_Connection nos sítios vivos (fonte); pré-flight de permissões `sql_monitoring` em 63 instâncias (owner corre o script, QA lê o CSV) | falha de permissão = P1 | correr 1 script de leitura, 10 min | `scripts/qa/runtime/p2_permissoes.py` + CSV |
| 3 | **P4 sessão/token** | reset-password não revoga JWT; token em localStorage E cookie; logout limpa ambos?; enumeração de contas pelo 401; expiração do lockout não repõe contador; OpenAPI ≠ payload real | enumeração e não-revogação = P1 | conta `qa_dba` além da viewer, 5 min | `test_auth_session_*.py` + `qa_ext_p4_session.py` |
| 4 | **P7 jornadas** | (a) DBA de manhã: login → overview → drill num alarme → exportar; (b) viewer só leitura: 403 com corpo `{}`; (c) sessão a expirar a meio da jornada (liga a P4) | 5xx, erro de consola, passo sem elemento = P1 | escrever as 3 jornadas em 10 linhas cada | `qa_ext_p7_jornadas.py` |
| 5 | **P6a/P6b KPI vs canónico** | 10 instâncias; a) snapshot backup/CHECKDB/suspect tol. 0, ≤2 min; b) janela bloqueios/deadlocks tol. max(2 eventos, 5%), mesma janela UTC | divergência = P0 | correr SELECTs, gravar CSV, 15 min por lote | `qa_ext_p6_reconcilia.py` |
| 6 | **P9 heurística** | por ecrã público e autenticado: contraste (axe), alvos ≥ 24px, foco visível por Tab, tema claro/escuro, 10 princípios com evidência | axe serious/critical = P1 | nada | `qa_ext_p9_heuristica.py` |
| 7 | **P5 innerHTML** | lista exacta dos `innerHTML` que recebem nomes de DB/job/login, SQL do LIVE, logs (grep estático) | sink sem escape = P0 | instância canário com nomes maliciosos (secção 4) | `test_innerhtml_sinks.py` |
| 8 | **P8 UX writing** | lista fechada de mensagens de erro/vazio (fonte + i18n); critério "diz o que fazer a seguir"; rótulos consistentes; glossário | mensagem sem próxima acção = trava release; resto = delta | nada | `docs/qa/externo/mensagens.csv` + `test_mensagens_accionaveis.py` |
| 9 | **P3 soak** | pré-teste 20 min (troca de tab a cada 10 s, heap via CDP + nós DOM); só se o declive for positivo corre 3×1h | leak confirmado = P1 | 20 min de janela, depois 3 h | `qa_ext_p3_soak.py` |

Corta-se P3 só se o pré-teste de 20 min der declive plano. A/B e usabilidade com humanos ficam fora:
não são tarefa de agente.

## 3. Backlog de implementação (fora das pautas, por ordem)

| # | Item | Dono | Prazo | Estado |
|---|---|---|---|---|
| B1 | Reset `qa_viewer` + login validado + `claude --resume` (ronda 4) | owner | hoje | pendente |
| B2 | Aplicar CI hotfix PASSO3/4 (outra sessão) depois de o ler; sem CI verde os gates novos não valem | owner + council | esta semana | pendente |
| B3 | Privar o repo; depois purga do histórico e rotação `sql_monitoring` (achado 04/09) | owner | antes do 1.º push | pendente |
| B4 | `tests/unit/test_csrf_surface.py` (superfície via `app.openapi()` + ordem dos middlewares) | council | com P4 | por escrever |
| B5 | Ratchet CI de literais fora da escala (congelar no número medido na ronda 4) + rótulo "LIVE" 13px congelado por asserção | council | após ronda 4 | por escrever |
| B6 | `watcherdb_main.py:798` versão literal → ler do `pyproject.toml` (verificar consumidores antes) | council | esta semana | por escrever |
| B7 | `/release-check` passa a exigir "última pauta fechada" | council (docs-writer) | antes do próximo release | por escrever |
| B8 | Canário sintético (secção 4) | owner decide | antes de P5/P7 | DECISÃO DO OWNER |
| B9 | Rodar password `qa_viewer` no fim de cada pauta | owner | contínuo | — |

## 4. DECISÃO DO OWNER — canário sintético

Sem uma instância com dados estáveis e conhecidos, P5, P6 e P7 herdam a flakiness de PRD: valores
mudam entre a medição e o screenshot, e um nome de objecto malicioso não pode ser plantado em
produção. Opções:

- **(a) Instância SQL Server de teste registada no collector** (nomes de DB/job com `<script>` e
  aspas, KPIs previsíveis, backups controlados). Custo: 1 instância, 1 h de setup, mantida por ti.
  Ganho: P5 e P7 com asserções literais, P6 com verdade conhecida.
- **(b) Sem canário**: P5 só por grep estático (sem prova em runtime), P7 só com invariantes, P6 só
  contra PRD com janela ≤ 2 min. Custo zero, evidência mais fraca.

Recomendação do orquestrador: (a), porque é também o único sítio onde um banco aceita que se prove o
XSS sem tocar em dados reais.

## 5. Panorama (modelo a repetir em cada fecho)

| Área | Estado | Bloqueio |
|---|---|---|
| Pauta em curso | | |
| Pautas fechadas / por abrir | | |
| Lotes shipped a partir do QA | | |
| Gates (testes + scripts) | | |
| Conta QA | | |
| Repo e CI | | |
| Decisões do owner pendentes | | |
