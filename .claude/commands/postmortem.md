---
description: Post-mortem de incidente (linha do tempo + hipóteses + causa-raiz, anonimizado)
---

Conduza um post-mortem do incidente: $ARGUMENTS.

1. Leia docs/context/CONTEXT.md.
2. Colete o que eu fornecer (logs, mensagens de erro, linha do tempo).
   Consultas de diagnóstico adicionais: apenas PROPOSTAS em bloco de
   código para eu rodar via sql_monitoring (read-only).
3. Subagent incident-forensics: método completo de post-mortem
   (linha do tempo, hipóteses concorrentes, causa-raiz, fatores
   contribuintes, ações corretivas, oportunidade de detector/KPI novo
   para o WatcherDB).
4. ANONIMIZAR: zero nomes de servidores/sistemas/empregador (regra de IP).
5. Relatório em docs/context/postmortems/AAAA-MM-DD_<slug>.md.
6. 1-3 linhas no Diário do CONTEXT.md.
7. 1 linha em docs/context/SOLUCOES.md (sintoma | causa-raiz | fix |
   ponteiro | palavras-chave) — formato na skill `recall`. Antes de
   começar o passo 3, correr `/recall <sintoma>` para apanhar precedentes.
