---
stage: 04
title: Council de specialists AI
version: 0.1.0
constraints: [AIWORK]
---

# Etapa 04 — Council de specialists para {{PROGRAM_NAME}}

Monta o conjunto de subagents AI que o projeto precisa. Se o Provost
core está instalado, delega a autoria ao `council-architect` — esta
etapa define O QUE pedir-lhe.

## Tarefas

1. **Base pack** (qualquer projeto): explorer (buscas baratas),
   test-generator, docs-writer, architecture-advisor, e um
   adversarial/challenger para decisões que importam.

2. **Specialists de domínio** — deriva da Feature Matrix e do stack
   {{STACK}}: um specialist por área com profundidade real (ex.: BD
   específica, framework UI escolhido, integração externa crítica).
   Regra anti-colisão: cada descrição diz QUANDO usar E quando NÃO
   usar; duas descrições que se sobrepõem = routing partido.
   <!-- EXPAND: propõe 3-6 specialists concretos para esta ideia, cada
   um com nome, missão de 1 linha e "NÃO usar para". -->

3. **Routing de custo**: modelo barato para lookups, mid-tier para
   geração mecânica, modelo de sessão para decisões. Specialist caro
   (arquitetura, forensics) só quando a decisão importa.

4. **Padrão de trabalho** (bloco AIWORK): modo de dispatch — para
   trabalho não-trivial, a AI PROPÕE o plano de dispatch e espera GO;
   verificação independente a cada N unidades; blackboard partilhado
   (CONTEXT.md) que todos leem antes e anexam decisão depois.

5. **Evolução**: o council cresce com o projeto — gap detetado
   (pergunta recorrente sem specialist certo) vira proposta de agent
   novo, não sobrecarga de um existente.

## Critério de saída
- [ ] Lista de specialists aprovada (nome + missão + NÃO-usar-para)
- [ ] Routing de custo definido
- [ ] Blackboard criado e regra "ler antes / anexar depois" em vigor
