---
description: Revisão de design do portal (capturas DEV + ux-design-reviewer + mockups)
---

Execute uma revisão de design do WatcherDB V3.3 sobre: $ARGUMENTS
(se vazio, telas principais do portal SPA).

1. Leia docs/context/CONTEXT.md.
2. Capture o estado atual via Playwright em DEV (NUNCA produção,
   NUNCA dados reais de cliente) →
   docs/context/design/capturas/AAAA-MM-DD/.
   Sem Playwright disponível: peça screenshots ao usuário e PARE.
3. Subagent ux-design-reviewer: analisar capturas + código de frontend
   (templates/watcherdb_portal.html).
4. Entregar: diagnóstico por tela com severidade; 5 inovações ranqueadas
   por impacto/esforço; mockups HTML estáticos das top 3 em
   docs/context/design/mockups/; diffs de quick wins (sem aplicar).
5. Relatório em docs/context/design/AAAA-MM-DD_review.md.
6. 1-3 linhas no Diário do CONTEXT.md.
