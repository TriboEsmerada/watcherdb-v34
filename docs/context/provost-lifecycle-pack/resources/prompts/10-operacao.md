---
stage: 10
title: Operação — postmortem, memória, blackboard
version: 0.1.0
constraints: [OBS, DOCS, AIWORK]
---

# Etapa 10 — Operação de {{PROGRAM_NAME}}

O produto está vivo. Esta etapa é um LOOP permanente, não um marco:
observar → aprender → destilar → melhorar.

## Rotinas

1. **Freshness watch** (bloco OBS): rotina periódica que verifica a
   idade dos dados servidos, não só o uptime. Dashboard bonito com
   dados de há 2 meses é o incidente mais silencioso que existe —
   detecta-o por rotina, não por acaso.

2. **Postmortem por incidente** (sem culpados, com linha do tempo):
   - Linha do tempo factual (timestamps, quem viu o quê)
   - Hipóteses concorrentes — mantém 2-3 vivas até a evidência decidir;
     a primeira explicação plausível raramente é a causa-raiz
   - Causa-raiz + fatores contribuintes
   - Ações: o teste que teria apanhado, o alarme que faltou, a cláusula
     nova para a memória

3. **Memória destilada**: cada lição vira entrada curta com
   **Porquê** + **Como aplicar** — regra sem porquê não sobrevive a
   3 meses. Incidentes recorrentes indicam cláusula mal escrita:
   reescreve-a, não a repitas.

4. **Blackboard** (bloco AIWORK): CONTEXT.md do projeto — decisões
   vigentes + diário append-only (data | agente | decisão + ponteiro,
   1-3 linhas). Cap de linhas; ao passar, compactar. Relatórios longos
   vivem em ficheiros próprios; o blackboard aponta.

5. **Manutenção periódica** (mensal): dependências (audit + upgrades
   menores), rotação de logs, staleness da documentação (README ainda
   instala? screenshots ainda batem?), revisão das cláusulas
   `last_verified` vencidas.

6. **Realimentar o ciclo**: pedidos de utilizadores e padrões de
   incidentes alimentam a Feature Matrix (etapa 02) — a operação é a
   melhor fonte de ideação da versão seguinte.

## Critério de saída (por ciclo)
- [ ] Zero incidentes sem postmortem escrito
- [ ] Lições do ciclo destiladas na memória (com porquê)
- [ ] Blackboard compactado se acima do cap
- [ ] Backlog da próxima versão atualizado com o aprendido
