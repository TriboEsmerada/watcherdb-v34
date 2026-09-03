# ADR-NNN — <Título curto>

- **Status:** Proposed | Accepted | Superseded by ADR-XXX | Deprecated
- **Date:** YYYY-MM-DD
- **Owner specialist:** <nome do specialist que conduziu / orquestrador>
- **Stakeholders consulted:** <list de specialists ou roles>

## Context

<2-4 parágrafos: porque é que esta decisão é necessária? Que problema resolve?
Que alternativas estão na mesa? Restrições conhecidas (compliance, deadline,
recursos)?>

## Decision

<1 parágrafo: a decisão tomada. Resumo accionável.>

## Rationale

<lista numerada: porque é que esta opção foi escolhida em detrimento das
alternativas. Cita evidence (paths, queries, benchmarks, findings).>

1. <Razão 1>
2. <Razão 2>
3. <Razão 3>

## Alternatives considered

| Opção | Pros | Cons | Rejeitada porque |
|---|---|---|---|
| Opção A | ... | ... | ... |
| Opção B | ... | ... | ... |

## Consequences

### Positive

- <ganho directo>
- <segundo ganho>

### Negative / Trade-offs

- <custo aceite>
- <dívida técnica criada>

### Migration plan (se aplicável)

1. <passo 1>
2. <passo 2>
3. <rollback se passo 2 falhar>

## Validation / acceptance criteria

- [ ] <critério mensurável 1>
- [ ] <critério mensurável 2>
- [ ] <critério mensurável 3>

## References

- `docs/<doc>.md` — ...
- `findings-inbox.md` FIND-YYYYMMDD-NNN — ...
- `knowledge_base/<path>.md` — ...
- Commit `<hash>` — ...

---

**Notes:**
- ADRs são **append-only**. Se decisão muda, criar ADR novo com `Supersedes ADR-NNN`.
- Manter ADR ≤ 2 páginas (force foco).
- Cada decisão arquitectónica significativa (porta, auth, migration model, package format,
  composição council, dual-library) merece ADR.
