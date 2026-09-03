---
name: generate-pack
description: Generate a dedicated lifecycle prompt pack for a new program idea. Use when the user gives a program name plus an idea paragraph and wants stage-by-stage build prompts (discovery through operations), or asks to instantiate one specific lifecycle stage. Reads the generic stage templates and cross-cutting constraints, adapts them to the idea, shows the result, and writes only after approval.
version: 0.1.0
---

# Lifecycle Pack Generator

Transformas os templates genéricos em `resources/prompts/*.md` num pack
de prompts DEDICADO à ideia do utilizador. O motor de adaptação és tu.

## Fase 1 — Inputs

Recolhe (do interview do `/provost:bootstrap` se já correu; senão
pergunta — máx. 1 ronda, usa AskUserQuestion se disponível):

- `{{PROGRAM_NAME}}` — nome do programa
- `{{IDEA}}` — parágrafo da ideia (1 parágrafo chega; não exijas spec)
- `{{STACK}}` — decidida ou "council propõe"
- `{{DATA_SENSITIVITY}}` — pessoal/financeiro/saúde/credenciais/prod-DB?
- `{{TARGET_PLATFORMS}}` — subconjunto de {desktop, web, android, ios,
  tablet}; se o utilizador disser "todos", confirma se offline importa
- `{{GOVERNANCE_PRESET}}` — Advisor / Guarded / Autonomous
- `{{TEAM}}` — solo ou equipa; experiência com AI-assisted coding

## Fase 2 — Instanciar (mostrar, NÃO escrever)

Para cada etapa pedida (default: todas as 11):

1. Lê o template em `resources/prompts/NN-*.md`.
2. Substitui TODOS os placeholders `{{VAR}}`. Zero placeholders órfãos.
3. Resolve cada bloco `<!-- EXPAND: condição -->`: se a condição se
   aplica à ideia, escreve a secção adaptada (2-10 linhas, específica,
   com recomendação explícita + razão curta — nunca menu de opções);
   se não se aplica, remove o bloco inteiro.
4. Injeta os blocos de `resources/constraints.md` cujo front-matter
   `applies_to:` inclui a etapa. NÃO injetes blocos não aplicáveis —
   contexto inchado é defeito, não zelo.
5. Verifica o checklist de qualidade (abaixo) antes de mostrar.

Mostra o pack instanciado ao utilizador (ou um índice + 2 exemplos
completos se forem as 11 etapas, para não inundar o chat).

## Fase 3 — Escrever (só após aprovação explícita)

Escreve em `<projeto-alvo>/docs/prompts/` um ficheiro por etapa,
mais `00-INDEX.md` com a ordem de uso e o estado (pendente/em curso/
feito) de cada etapa. Nunca sobrescrevas pack existente sem mostrar
diff. Regista no fim: pack version usada + data.

## Checklist de qualidade (obrigatório antes de mostrar)

- [ ] Zero `{{...}}` e zero `<!-- EXPAND` no output
- [ ] Cada secção expandida tem recomendação explícita + razão
- [ ] Prompt instanciado ≤ ~100 linhas (subtrair > acrescentar)
- [ ] Constraints injetadas batem com o `applies_to:` declarado
- [ ] Nenhuma referência a WatcherDB/empregador no output (é genérico)
- [ ] Etapas com `last_verified:` > 6 meses → avisa o utilizador que o
      conteúdo pode ter datado (frameworks, versões)

## Regras

- Uma etapa pode ser instanciada isolada ("dá-me só o prompt de QA").
- Lições novas do utilizador ("da última vez falhou X") vão para
  `resources/lessons.md` como proposta — consolidação em
  `constraints.md` é decisão do owner do pack, não tua.
- Se `{{DATA_SENSITIVITY}}` inclui dados regulados, o preset
  recomendado é Advisor ou Guarded — di-lo na etapa 00 e porquê.
