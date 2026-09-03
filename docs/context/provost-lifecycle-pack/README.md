# provost-lifecycle — Lifecycle Prompt Pack (PROPOSTA v0.1.0)

> Data: 2026-07-24 | Autor: AI (modo consultor) + síntese de dispatch
> challenger (a77df457) + ai-systems-architect (ae36488b).
> Estado: PROPOSTO — ficheiros prontos-a-colar; owner copia para o repo
> Provost manualmente.

## O que é

Domain pack do Provost (plugin irmão de `provost-ai`) que destila a
expertise de construção do WatcherDB (V1/V3.3/V5/V6) em **11 prompts de
etapa do ciclo de vida** + **1 ficheiro de constraints transversais**.
O utilizador dá `nome do programa + parágrafo da ideia`; a skill
orquestradora `generate-pack` instancia os prompts dedicados à ideia.

O motor de adaptação é o próprio Claude Code — não há app standalone,
não há chamadas de API extra. (Decisão sustentada por challenger:
standalone só se ≥3 pedidos externos concretos E 1º cliente V6 fechado.)

## Decisões de design (síntese dos specialists)

1. **Plugin irmão `provost-lifecycle`**, não extensão do bootstrap core
   nem parte do `provost-ai` — lifecycle é transversal a produtos AI e
   não-AI; segue o padrão de domain packs já estabelecido.
2. **Instanciação híbrida**: templates Markdown com placeholders fixos
   (`{{PROGRAM_NAME}}`, `{{IDEA}}`, `{{STACK}}`, `{{DATA_SENSITIVITY}}`,
   `{{TARGET_PLATFORMS}}`, `{{GOVERNANCE_PRESET}}`, `{{TEAM}}`) +
   secções `<!-- EXPAND: condição -->` que a skill expande por
   julgamento. Esqueleto auditável/versionável; drift limitado ao que
   genuinamente precisa de julgamento; corpo estático cacheable.
3. **Cross-cutting em `constraints.md` único** com front-matter
   `applies_to:` por bloco — a skill injeta cada bloco SÓ nas etapas
   onde é relevante ("subtrair é a maestria"; nada de mesa lotada).
4. **Um skill orquestrador**, não 11 skills (evita collision de routing).
5. **SemVer por ficheiro** (front-matter `version:`) + `last_verified:`
   nos blocos que datam rápido (frameworks UI, packaging).
6. **Show, don't write**: a skill mostra os prompts instanciados e só
   escreve após aprovação explícita (mesmo gate do bootstrap).
7. **Captura de lições**: incidentes → `lessons.md` → consolidação
   periódica em `constraints.md` com cap (máx 15 cláusulas/bloco).

## Layout de instalação (destino no repo Provost)

```
Provost/
└── plugins/
    └── provost-lifecycle/
        ├── .claude-plugin/plugin.json        (owner cria; espelhar provost-ai)
        ├── README.md                          ← este ficheiro (adaptar)
        ├── skills/
        │   └── generate-pack/SKILL.md         ← skill orquestradora
        └── resources/
            ├── constraints.md                 ← 8 blocos transversais
            ├── lessons.md                     ← inbox de lições (seed)
            └── prompts/
                ├── 00-governanca.md
                ├── 01-ideacao.md
                ├── 02-produto.md
                ├── 03-arquitetura.md
                ├── 04-council.md
                ├── 05-implementacao-waves.md
                ├── 06-qa.md
                ├── 07-hardening.md
                ├── 08-packaging.md
                ├── 09-release-gate.md
                └── 10-operacao.md
```

## Fasquia de sucesso (challenger)

O pack justifica-se se: usado em ≥2 bootstraps reais, output "nome +
parágrafo → prompts dedicados" em <1 sessão, ≥80% aproveitado sem
reescrita. Senão, era só um documento.

## Riscos aceites e mitigação

| Risco | Mitigação |
|---|---|
| SOTA-lag (frameworks UI, packaging datam) | `last_verified:` por bloco + revalidação trimestral |
| Genericidade sem ação (prompts-menu) | cada secção expandida FORÇA recomendação + razão |
| Write-scope descontrolado (11 ficheiros/invocação) | gate show-don't-write |
| IP leak (licença Provost indefinida) | pack fica local até decisão de licença do Provost |
