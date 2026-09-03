---
stage: 02
title: Definição de produto e tiers
version: 0.1.0
constraints: [XPLAT, DOCS]
---

# Etapa 02 — Definição de produto de {{PROGRAM_NAME}}

Com a síntese da ideação em mãos, transforma {{PROGRAM_NAME}} numa
definição de produto operacional.

## Tarefas

1. **Personas** (máx. 3): quem usa, em que dispositivo, com que
   frequência, com que nível técnico. A persona menos técnica define a
   fasquia de UX.

2. **Feature Matrix** — o ground truth do produto. Tabela:
   feature | v1/v2/futuro | tier (se houver edições Free/Pro) | persona
   servida. Regra: uma feature sem persona é feature de vaidade — corta.
   <!-- EXPAND: se a ideia sugere modelo comercial (SaaS, licença,
   one-off), recomenda estrutura de tiers com 1 linha de racional;
   senão remove a coluna tier. -->

3. **Plataformas-alvo** — para {{TARGET_PLATFORMS}}: decide AGORA a
   estratégia (bloco XPLAT: árvore PWA → Flutter → RN → Kivy). A
   decisão de plataforma na etapa de produto evita reescrita na de
   arquitetura. Regista como ADR-lite.
   <!-- EXPAND: aplica a árvore de decisão XPLAT à ideia concreta e
   dá a recomendação com razão. Se offline-first importa para esta
   ideia, di-lo aqui. -->

4. **Signal, não noise** — para qualquer dashboard/lista/alerta do
   produto: define o que é SINAL acionável para a persona. Dedupe e
   agregação primeiro; detalhe estrutural só a pedido.

5. **Smart defaults** — zero configuração obrigatória na primeira
   execução. Auto-detecta o que puderes; config avançada existe mas
   nunca bloqueia o primeiro uso.

## Critério de saída
- [ ] FEATURE_MATRIX.md escrito (será citado por todas as etapas seguintes)
- [ ] Estratégia de plataforma decidida e registada como ADR
- [ ] Personas com dispositivo e fasquia de UX definidos
