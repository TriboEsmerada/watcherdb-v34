---
stage: 05
title: Implementação por Waves
version: 0.1.0
constraints: [GIT, ENCAPS, OBS, DOCS, AIWORK]
---

# Etapa 05 — Implementação de {{PROGRAM_NAME}} por Waves

Organiza TODO o trabalho de implementação em Waves nomeadas — unidades
fechadas com abertura, execução e fecho ritualizados. Nunca "vou
mexendo": cada sessão pertence a uma Wave.

## Abertura de Wave
1. Nome + objetivo em 1 frase + entrada no CHANGELOG (SemVer,
   `## [x.y.z] - Wave <NOME> - em curso`).
2. Checkpoint git (bloco GIT #2): branch dedicada ou commit limpo
   ANTES de tocar em código.
3. Panorama visível: lista feito / em curso / pendente; atualiza a
   cada marco.

## Durante a Wave
4. Commits atómicos frequentes; fim de sessão NUNCA com trabalho
   uncommitted sem registo explícito do porquê.
5. Boundaries respeitados (bloco ENCAPS): mudança que atravessa camada
   é sinal de design errado — para e reavalia, não "só desta vez".
6. Serviço/processo alterado? Reiniciar antes de validar — código em
   cache de processo valida a versão ERRADA (classes Python em serviços
   Windows, workers, hot-reload incompleto).
7. Cada fix relevante pergunta: "onde mais existe este padrão?" —
   corrige a família, não a instância (paridade sync/async, variantes
   por ambiente).

## Fecho de Wave
8. Checklist de superfícies: código + testes + CHANGELOG + docs
   afetados + specialists/skills a atualizar. Fechar Wave sem propagar
   é dívida imediata.
   <!-- EXPAND: se o projeto tem múltiplas edições/repos que herdam
   fixes, acrescenta a superfície "propagação a <edições>" com regra
   explícita de verificação (grep anchors no destino primeiro). -->
9. Validação real, não presumida: correr a app (bloco OBS), ver o
   dado/ecrã mudado com os próprios olhos. "Compila" não é "funciona".
10. Commit final da Wave + CHANGELOG fechado + panorama atualizado.

## Critério de saída (por Wave)
- [ ] CHANGELOG fechado com a Wave nomeada
- [ ] Zero trabalho uncommitted não registado
- [ ] Superfícies propagadas (docs/testes/specialists)
- [ ] Validação em execução real feita
