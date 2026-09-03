# PROMPT — Propagação V3.3 → V6 · LOG_SPACE_USAGE HAS_DBACCESS (05/08)

Para a sessão AI do V6. Origem: sessão V3.3 de 05/08. Fix validado na BD
viva do PRD213 + **consenso do sql-deep-reviewer**. Commit V3.3: `676da69`.
Regra: `v33-v6-propagation-rule`.

---

## O que mudou e porquê (LER — a regra geral fica)

**REGRA GERAL:** a guard canónica do padrão "USE `<db>` dinâmico dentro de
um batch único" é **`HAS_DBACCESS(name) = 1`**, não `DATABASEPROPERTYEX`
nem `is_primary_replica`.

Porquê: quando o `USE <db>` corre para uma base que a login não consegue
abrir, o erro rebenta na **COMPILAÇÃO do sub-batch** (não no runtime), por
isso o `TRY/CATCH` do mesmo batch **não o apanha** — uma única base má
derruba o endpoint inteiro com 500. Dois modos de falha, ambos provados no
`SQLHDSPRD213_I01` (15 bases state=0):
- **erro 976** — secundárias AG não-legíveis (data movement suspenso).
- **erro 916** — bases sem acesso da login (`model`, `DBA_RESOURCE_DB`).

`HAS_DBACCESS(name)` responde exactamente à pergunta "a login corrente
consegue entrar nesta base" (avaliada no contexto de `sql_monitoring`, que
é quem corre o USE) → devolve 0 para **ambos** os modos, pela raiz. As
tentativas anteriores eram inferiores:
- `DATABASEPROPERTYEX(Collation) IS NOT NULL` — a collation vem da metadata
  do master, devolvida na mesma para secundárias → **não exclui nada** (as 15).
- `NOT EXISTS is_primary_replica` — cobre as AG mas deixa passar model+
  DBA_RESOURCE_DB (→ 916) **E** cega as secundárias AG **legíveis**
  (readable), que ocupam disco real e **devem** aparecer num relatório de
  file/log-space. (era o que o V6 tinha.)

## Onde aplicar no V6 (anchor confirmado pelo sql-deep-reviewer)

**`WATCHERDB_V6/modules/monitoring/queries.py`**, query **`LOG_SPACE_USAGE`**
(≈ linhas 613-682). O guard está nas **linhas 647 e 656-660** e tem AS DUAS
guardas fracas: `DATABASEPROPERTYEX(Collation) IS NOT NULL` (647) **e**
`NOT EXISTS ... is_primary_replica` (656-660). Substituir ambas por:

```sql
    FROM sys.databases
    WHERE state = 0
      AND HAS_DBACCESS(name) = 1;
```

(manter só o `state = 0` como pré-filtro barato; remover as duas guardas
fracas — não são defesa-em-profundidade, o is_primary_replica muda a
semântica para pior ao cegar as secundárias legíveis).

**Nota:** o V6 **não tem** `FILE_SPACE_DETAIL` (essa query é só do V3.3) —
só há a `LOG_SPACE_USAGE` a corrigir no V6.

## Fora de escopo (NÃO tocar)

- Query de estatísticas desatualizadas (~1378 no V3.3): usa cursor com
  `EXEC` por-BD dentro do TRY externo → já é crash-safe (o CATCH apanha).
- `LOG_SPACE_MONITORING` (V6 ~684): usa `DBCC SQLPERF(LOGSPACE)`, sem USE
  por-BD → não tem o crash. Tem só uma inconsistência cosmética
  (is_primary_replica no SELECT principal vs HAS_DBACCESS no fallback) —
  harmonização opcional, não é bug.

## Validação V6 (após aplicar)

Correr `LOG_SPACE_USAGE` contra uma instância com AG secundárias e bases
de sistema restritas (ex.: um servidor PRD com secundárias). Esperado:
- **sem 500** (nem 976 nem 916);
- inclui as bases abríveis (master/tempdb/msdb + primárias + secundárias
  **legíveis**);
- omite as secundárias não-legíveis + bases sem acesso.

## Risco residual (nomeado pelo sql-deep-reviewer)

`HAS_DBACCESS` fecha as falhas determinísticas (o caso repetível). Fica um
race teórico: uma base pode tornar-se inacessível **entre** o SELECT que
constrói o `@sql` e o `EXEC`. Janela minúscula. Se surgir algum 500
residual nos logs, o follow-up de robustez é reestruturar para o padrão
**`EXEC` por-BD dentro do TRY externo** (como a query do cursor já faz) —
aí qualquer falha de USE, inclusive por race, é apanhada. Não fazer agora;
HAS_DBACCESS resolve o incidente.
