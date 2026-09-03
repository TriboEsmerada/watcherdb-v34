---
stage: 03
title: Arquitetura e ADRs
version: 0.1.0
constraints: [GIT, PY-PKG, ENCAPS, XPLAT, SEC, OBS]
---

# Etapa 03 — Arquitetura de {{PROGRAM_NAME}}

Desenha a arquitetura mínima que serve a Feature Matrix da etapa 02 —
nem mais uma camada. Stack: {{STACK}}.

## Tarefas

1. **Camadas e boundaries** (bloco ENCAPS): diagrama simples
   UI ↔ API ↔ domínio ↔ dados; para cada fronteira, o contrato (o que
   passa, o que nunca passa). UI nunca toca na BD.

2. **Modelo de dados** — esquema inicial + catálogo (tabela: nome,
   colunas-chave, dono, quem lê/escreve). O catálogo é documento vivo:
   toda a proposta de SQL futura valida contra ele antes de assumir
   colunas.
   <!-- EXPAND: se a ideia é read-heavy com dashboards, considera o
   padrão staging BLUE/GREEN com swap atómico para leituras nunca
   verem dados a meio de carga; recomenda ou descarta com razão. -->

3. **ADR-lite por decisão estrutural** (1 parágrafo cada: contexto →
   decisão → consequência): framework UI (herda da etapa 02), acesso a
   dados (driver/ORM), async vs sync, gestão de estado, estratégia de
   erro/degradação graciosa (feature indisponível mostra estado
   degradado, nunca crash).

4. **Segurança por design** (bloco SEC): threat model STRIDE leve
   (1 tabela), pontos de autenticação/RBAC, onde há rate limiting.

5. **Observabilidade por design** (bloco OBS): logging estruturado,
   /healthz, e o KPI de freshness de dados desde o desenho.

6. **Preparar o packaging desde já** (bloco PY-PKG): `pyproject.toml`,
   layout `src/`, config via Pydantic Settings — decisões baratas
   agora, caras de retrofit.
   <!-- EXPAND: se {{TARGET_PLATFORMS}} inclui mobile, define aqui a
   fronteira API (o backend serve JSON puro; o cliente mobile/PWA é
   consumidor) para o multi-plataforma não contaminar o domínio. -->

## Critério de saída
- [ ] Diagrama de camadas + contratos de fronteira escritos
- [ ] Catálogo de schema iniciado (documento vivo)
- [ ] ADRs das decisões estruturais registados
- [ ] Threat model leve feito; identidade de acesso a dados confirmada
