---
stage: 00
title: Governança e identidades
version: 0.1.0
constraints: [GIT, SEC, AIWORK]
---

# Etapa 00 — Governança e identidades de {{PROGRAM_NAME}}

Estás a preparar o terreno de {{PROGRAM_NAME}} ({{IDEA}}) ANTES da
primeira linha de código. Nada de implementação nesta etapa.

## Objetivo
Sair daqui com: regras do projeto escritas, preset de autonomia da AI
escolhido e enforced, e identidades separadas.

## Tarefas

1. **Preset de governança** — confirma `{{GOVERNANCE_PRESET}}`:
   - Advisor: AI lê e propõe; humano executa tudo.
   - Guarded: AI escreve código e corre testes; pede antes de ops
     destrutivas, schema, dados sensíveis, push.
   - Autonomous: loop completo; pede antes de force-push, deletes,
     credenciais de produção, publicação externa.
   <!-- EXPAND: se {{DATA_SENSITIVITY}} inclui dados pessoais,
   financeiros, saúde, credenciais ou BD de produção — recomenda
   Advisor ou Guarded explicitamente e justifica em 2 linhas. -->

2. **Identidades** — define ANTES de existir código:
   - Conta de serviço least-privilege para dados (nome, escopo, o que
     NUNCA pode fazer).
   - Conta pessoal/domínio: proibida em connection strings.
   - Onde vivem os segredos (keyring/DPAPI/.env fora do repo).

3. **Regras do projeto (CLAUDE.md)** — prioridade-ordenadas, regra de
   governança SEMPRE #1; inclui: preset e o que significa na prática,
   regras de dados (nunca fabricar dados; nunca dados reais em testes),
   fasquia de qualidade, convenções de língua/nomes.

4. **Repo** — `git init`, `.gitignore` completo, primeiro commit só
   com governança + docs. Branch por projeto desde já.

## Critério de saída
- [ ] CLAUDE.md escrito e aprovado pelo humano
- [ ] Preset enforced (hook/policy), não só documentado
- [ ] Identidades e localização de segredos decididas por escrito
- [ ] Repo inicializado com .gitignore antes de qualquer código
