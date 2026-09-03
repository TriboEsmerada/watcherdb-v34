---
description: Varredura de qualidade (pytest mocks + classificação de falhas + diffs propostos)
---

Execute uma varredura de qualidade no WatcherDB V3.3 sobre: $ARGUMENTS
(se vazio, suíte completa).

1. Leia docs/context/CONTEXT.md.
2. Subagent code-explorer: mapear a área alvo.
3. Rode a suíte pytest relevante em tests/ (mocks apenas; PROIBIDO
   tocar banco ou serviço real — patch de execute_on_intelligence()).
4. Classifique cada falha: bug real / teste quebrado / flaky;
   severidade; causa provável.
5. Bugs reais: proponha correção como DIFF — não aplique (modo
   consultor; código-fonte está fora dos caminhos de escrita).
6. Relatório em docs/context/auditorias/AAAA-MM-DD_varredura.md.
7. 1-3 linhas no Diário do CONTEXT.md com conclusão + ponteiro.
8. Resumo executivo: top 3 problemas e diffs propostos.
