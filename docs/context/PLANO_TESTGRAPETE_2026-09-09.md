# TestGrapete: plano (2026-09-09)

Origem: pergunta do owner sobre TestSprite (rejeitado para PRD por soberania;
avaliação em laboratório fora da TAP fica como trilho separado). Council:
watcherdb-qa-specialist + challenger. Decisão: NÃO construir um clone do
TestSprite; construir a cola que falta. A lacuna real é uma só: ninguém corre os
e2e sem uma pessoa os lançar. Não há job noturno, bundle de falhas persistido,
nem regressão entre rondas.

Duas metades com o mesmo motor:
- **Council (afirma):** runner Playwright parametrizado, módulo x perfil, com
  bundle de evidências. Produz "corrigido" com prova.
- **qa-externo (confere):** os scripts dele em scripts/qa/runtime continuam
  independentes, correm no mesmo job, a seguir, e escrevem na mesma pasta.
  Divergência entre as duas metades é achado. O council não edita os scripts dele.

## Pré-requisito

Lote 0 hotfix do CI (PASSO 3 e 4, ainda por aplicar em 09/09). Os três runs do
Actions desde 05/09 falharam pela mesma causa (unixodbc + import win32 na
coleção). Sem CI verde, o TestGrapete herda instabilidade que não é dele.

## Lotes

| Lote | Conteúdo | Esforço | Critério de saída |
|---|---|---|---|
| TG-1 | Runner do council: tests/e2e/test_smoke_modules_e2e.py (fleet + 16 abas x 3 perfis), evidências JSON por caso, screenshot e trace em falha; scripts/qa/nightly_testgrapete.ps1 que corre council e depois externo e escreve SUMMARY.md | meio dia | Corrida manual na 8434 com os 3 perfis: 0 pageerror, bundle escrito em docs/qa/externo/AAAA-MM-DD/ |
| TG-1b | Painel estático: scripts/qa/testgrapete_board.py lê os bundles e gera docs/qa/externo/index.html (linha do tempo, council vs externo lado a lado, divergências) e board.html por corrida; o job noturno chama-o no fim. Sem servidor, sem dependências, abre por file:// | meio dia | index.html regenerado após cada corrida, divergências listadas |
| TG-2 | Job noturno: tarefa agendada no host da 8434 (02:00), credenciais em .env.qa fora do git, linha por corrida em docs/qa/externo/NIGHTLY_LOG.md | 1 hora | 3 noites seguidas com bundle escrito sem intervenção |
| TG-3 | Ratchet de regressão: invariantes (0 pageerror, 0 erros de consola fora do ruído, 0 respostas 5xx, abas a responder) comparadas com a corrida anterior; falha nova = linha no findings-inbox | meio dia | Primeira regressão real apanhada antes do owner |
| TG-4 | Decisão do canário (2 e2e falham sempre contra PRD sem réplica, plano v2 do qa-externo) e e2e no CI (exige runner self-hosted com serviço vivo) | decisão do owner | Fora deste plano até TG-3 provar valor |

## Barra para continuar (do challenger)

Quatro semanas a correr sozinho, no máximo um falso positivo por semana, e pelo
menos uma regressão real apanhada antes do owner. Se em quatro semanas não
apanhar nada que o qa-externo não apanhasse, pára em TG-3.

## O que NÃO entra

Crawler que descobre ecrãs (os 16 módulos são fixos), gerador de testes por IA
(o test-generator e o Claude já o fazem por pedido), execução paralela (48 casos
não justificam), FEATURE_MATRIX como PRD (é um stub de 4 linhas).

## Decisões do owner

1. Conta admin de QA: hoje só existem qa_viewer e qa_dba. Criar qa_admin pela
   API (como fizeste para qa_dba a 08/09) ou correr o perfil admin com a tua conta.
   Recomendo qa_admin: o bundle fica com login rastreável e a tua sessão fora dos logs de teste.
2. Servidor alvo do smoke: um TST. Vai em WATCHERDB_QA_SERVER (nome ou server_id).
   Sem ele o runner escolhe o primeiro com environment TST.
3. Hora do job: 02:00 evita o pico de coleta? Confirmar com o intervalo dos collectors.
4. TestSprite: trial só depois de TG-3, em laboratório fora da TAP, sem upload de código.

## Ficheiros

- docs/context/TG1_PASSO1_apply.py: escreve o teste, o script noturno e o .gitignore das evidências pesadas.
- docs/context/TG1_PASSO2_commit.ps1: corrida manual de validação contra 8434 + commit.
- Evidências: docs/qa/externo/AAAA-MM-DD/council/ (JSON por caso, junit, playwright/ com screenshots e traces só em falha) e docs/qa/externo/AAAA-MM-DD/externo/ (saída dos qa_ext_*.py).
