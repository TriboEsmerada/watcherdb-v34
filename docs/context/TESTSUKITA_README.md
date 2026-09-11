# TestSukita — como correr, o que produz, como ler

**O que é.** O vigia noturno do WatcherDB: um runner Playwright (council, *afirma*) e os scripts do qa-externo
(*confere*), a correr às 02:00 na máquina da 8434, com painel local e ratchet de regressão. Sem cloud.

## Correr

```powershell
pwsh scripts/qa/nightly_testsukita.ps1            # corrida completa (a mesma da tarefa agendada)
py scripts/qa/testsukita_board.py                 # só regenerar o painel
py scripts/qa/testsukita_ratchet.py               # só o ratchet do dia
py -m pytest tests/e2e/test_smoke_modules_e2e.py -m e2e --no-cov -p no:cacheprovider -q -k viewer   # um ficheiro, um perfil
```

Credenciais em `.env.qa` na raiz (ignorado pelo git); modelo no cabeçalho do script noturno. Perfil sem conta salta com motivo.

## Ficheiros do motor

| Ficheiro | Função |
|---|---|
| tests/e2e/test_smoke_modules_e2e.py | fleet + 16 abas × perfil; contexto da aba; helpers partilhados (login com cache, servidor de teste, evidências) |
| tests/e2e/test_semantic_e2e.py | grupos de KPI, drill-down (Always On: cartão = instâncias distintas), viewport 1093×614, filtro de bases |
| tests/e2e/test_interactions_e2e.py | explorador: cliques, campos e selects por aba |
| tests/e2e/test_api_smoke_e2e.py | GET do OpenAPI por perfil |
| tests/e2e/conftest.py | DOM em falha para `<bundle>/dom/` |
| scripts/qa/nightly_testsukita.ps1 | orquestra: council → pausa → externo → janela do log → ratchet → painel → NIGHTLY_LOG |
| scripts/qa/testsukita_ratchet.py | regressões vs corrida anterior + hipóteses |
| scripts/qa/testsukita_board.py | docs/qa/externo/index.html e board.html por dia |
| scripts/qa/runtime/NIGHTLY.txt | scripts do qa-externo que correm sozinhos (dono: qa-externo) |

## O que sai, por noite, em docs/qa/externo/AAAA-MM-DD/

- council/cases/*.json — um por caso (perfil, caso, tempos, DOM, erros, abortados, tocados, endpoints)
- council/playwright/ — screenshot e trace só em falha; council/dom/ — DOM só em falha
- council/pytest.log, junit.xml, service_log_window.log, RATCHET.json, RATCHET.md
- externo/*.log e externo/results.json
- SUMMARY.md; e uma linha em docs/qa/externo/NIGHTLY_LOG.md

## Como ler o painel

1. Linha do tempo: verde/âmbar/vermelho/cinzento por noite. Cinzento = não mediu (credenciais).
2. Ratchet: regressões e novas com hipótese. Uma regressão real vai para o findings-inbox.
3. Council vs externo lado a lado; a secção de divergências é onde nascem os achados.
4. Avisos de tempo (aba > 60 s) não são falhas; três noites seguidas na mesma aba são.

## Regras

- Nunca corre contra produção por omissão: escolhe o primeiro servidor `test`, depois `quality`.
- Falhas do runner corrigem-se no runner; falhas do portal viram achado depois de reproduzidas.
- Os scripts do qa-externo não são editados pelo council.
