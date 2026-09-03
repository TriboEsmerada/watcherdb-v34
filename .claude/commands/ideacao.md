---
description: Ciclo de ideação 3 rodadas (propostas → críticas → pre-mortem → síntese)
---

Execute um ciclo de ideação para o WatcherDB V3.3 sobre: $ARGUMENTS
(se vazio, evolução geral). Abra nova seção datada em
docs/context/IDEACAO.md.

RODADA 1 — subagent architecture-advisor: 5 ideias de evolução, cada
uma com premissa, valor esperado mensurável, custo e assunções.
Diversificadas (não atacar o mesmo subsistema). Tier Standard apenas.
Registrar em docs/context/IDEACAO.md.

RODADA 2 — subagent sql-deep-reviewer: criticar cada ideia (viabilidade
técnica, custo no cliente on-premise, risco para a infra partilhada
BLUE/GREEN). PROIBIDO concordar sem apontar pelo menos um problema real
por ideia. Anexar no mesmo arquivo. Máx. 3 sobreviventes.

RODADA 3 — subagent incident-forensics: pre-mortem das sobreviventes
("2027, isto causou incidente grave em produção bancária — por quê?").
Anexar no mesmo arquivo.

SÍNTESE — orquestrador consolida: ranking, trade-offs, vencedora e plano
de validação barato (a menor experiência que prova ou mata a premissa).
1 linha no Diário do CONTEXT.md.

REGRAS: cada rodada lê o arquivo IDEACAO.md original (não resumos);
nada é implementado; decisão final é humana.
