# Handoff Contract — Brief Self-Contained para Specialists

Specialists do council não vêem a conversa entre user e orquestrador. Cada
dispatch começa com context vazio. Briefs mal escritos = pareceres shallow.

Este doc define o **formato canónico** que o orquestrador deve usar quando
spawn um specialist via `Agent` tool.

## Anatomia de um bom brief

```
[CONTEXT — porque a task existe]
1-2 parágrafos. Que problema motiva esta análise? O que falhou antes?
Que iteração estamos (#1 inicial, #3 follow-up depois de fix)?

[STATE — o que já foi tentado / descartado]
- Já consultei <doc> e <doc>: <resumo do que aprendi>
- Tentei <approach X>: rejeitado porque <razão>
- Open questions: <lista>

[LOCATION — paths absolutos]
- Ficheiros relevantes (com linhas):
  - `c:/...path/file.py:123-145`
  - `c:/...path/template.html:33850`
- Commits relevantes: `691a529`, `7c95c53`

[TASK — lista numerada, accionável]
1. Revê <X> e responde: <pergunta concreta>
2. Verifica se <Y> aplica em <contexto>
3. Se <condição A>, propõe <output A>; se <condição B>, propõe <output B>

[CONSTRAINTS]
- Read-only: produz diffs em texto, não aplica
- Backward compat: <feature Z> não pode ser quebrada
- Word count cap: 500 palavras (force foco)
- Citar fonte: path + linha em cada afirmação

[OUTPUT FORMAT]
Template literal com headings que esperas:

  ## <Specialist> review: <topic>
  ### Findings
  - ...
  ### Recommendations
  - ...
  ### Risks
  - ...
  ### Files inspected
  - <path:line>

[KNOWLEDGE SOURCES]
- KB local primeiro: knowledge_base/<namespace>/
- Central: ~/.nestor-library/<namespace>/
- Ground truth: docs/FEATURE_MATRIX.md
- Cita fonte na resposta — sem citação = rejeito.

[PROACTIVE FINDINGS]
Se detectares algo fora do scope da task mas relevante, sinaliza no fim
com prefixo literal:
[PROACTIVE FINDING]: <category> | <path:linha> | <severity> — <descrição> / <sugestão>

Máx 3 por resposta.
```

## Checklist (antes de dispatchar)

- [ ] Brief tem **paths absolutos** (não relativos)?
- [ ] Brief tem **linhas concretas** (não "algures no ficheiro X")?
- [ ] **Tarefa é numerada** (não "podes analisar")?
- [ ] **Constraints declaradas** (read-only, word cap, formato)?
- [ ] **Knowledge sources citadas** (KB local + central + ground truth)?
- [ ] **Output template** explícito?
- [ ] Brief sob **800 palavras** (idealmente 400-600)?

## Anti-patterns

| Anti-pattern | Porquê é mau |
|---|---|
| `Agent(prompt="review V3.3 auth")` | Genérico → shallow output |
| "Based on findings, fix X" | Delega entendimento (orquestrador é quem sintetiza) |
| Sem location/linhas | Specialist gasta tokens a procurar |
| Sem output format | Output incoherente, difícil de comparar entre specialists em paralelo |
| Sem constraints | Specialist pode tentar `Bash+sed` (subverte read-only) |
| Brief monolítico (>1500 palavras) | Specialist queima context budget só a ler |

## Exemplo bom

> Terceira interacção sobre Patch D (auth multi-domain LDAP). Emitiste duas
> reviews — segunda foi GO-com-ressalvas. Agora pede-se review final do commit
> `691a529` antes de tag. Cliente pagante Std (XYZ Corp) pediu multi-domain
> esta semana, não há margem para regressão.
>
> Localização:
> - `api/routers/auth_compat.py:209` (`_require_admin`)
> - `api/routers/auth_compat.py:340-410` (multi-domain dispatch novo)
> - Commit `691a529` (Patch D)
>
> Tarefa:
> 1. Verificar que multi-domain dispatch não regride single-domain (clientes
>    Std actuais com 1 só domínio)
> 2. Confirmar que LDAPS (porta 636) é default; LDAP (389) só com flag
> 3. Detectar PII em logs (DN com nome real do user a aparecer em
>    `service_health.txt`?)
> 4. Verdict: GO (commit-and-tag) | GO-com-ressalvas (tag-after-fix-N) | NO-GO
>
> Constraints:
> - Read-only — produz diffs se houver fixes
> - Sob 600 palavras
> - KB local primeiro: `knowledge_base/operations/seed/ad_service_account_rotation.md`
> - Central: `~/.nestor-library/shared/owasp_cwe/` (CWE-287, CWE-522)
> - Cita path + linha em cada afirmação
>
> Output:
> ```
> ## V3.3 specialist review: Patch D auth multi-domain (commit 691a529)
> ### Findings
> ### Recommendations
> ### Risks
> ### Verdict: GO | GO-com-ressalvas | NO-GO
> ### Files inspected
>
> [PROACTIVE FINDING]: (0-3)
> ```

## References

- `docs/AGENTS_GUIDE.md` — quando invocar cada specialist
- `docs/BULLETIN_FORMAT.md` — comunicação inter-specialist
- `docs/PROACTIVE_COUNCIL.md` — 5 triggers + cadence
