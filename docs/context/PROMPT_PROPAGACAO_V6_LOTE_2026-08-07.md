# PROMPT — Propagação V3.3 → V6 · LOTE 07/08 (ausência de dados + AlwaysOn por base)

Para a sessão AI do V6. Origem: sessão V3.3 de 06–07/08.
Regra: `v33-v6-propagation-rule`. Commit V3.3: **(por commitar — pedir ao owner antes de aplicar)**.

**Antes de tudo:** o portal do V6 é um *subconjunto mais simples* do V3.3, **não** um
superconjunto. Os âncoras abaixo vêm como **strings de pesquisa**, não como números de
linha. Se o `grep` não encontrar, a feature pode simplesmente não existir no V6 — nesse
caso **não** a construir de raiz sem falar com o owner; reportar como "ausente no V6".

---

## REGRA GERAL DESTE LOTE (é isto que interessa, mais do que os diffs)

> **Ausência de dado não é ausência de problema.**
> Um cartão só pode ficar verde quando a leitura teve **sucesso** e o resultado foi zero.
> Se a leitura falhou, o cartão mostra **N/D em cinzento neutro** — nunca verde, nunca zero.

Esta sessão encontrou quatro sítios onde o produto pintava verde por cima de um buraco de
dados. O padrão de correcção é sempre o mesmo e deve ser aplicado como **contrato**, não
como quatro fixes soltos:

```
disponivel = payload?.success === true
cor        = !disponivel ? CINZA_NEUTRO : (contagem === 0 ? VERDE : VERMELHO)
valor      = disponivel ? contagem : 'N/D'
```

O cinzento tem de ser o **mesmo** já usado no cartão de Serviços (`#6b7280`), para o
utilizador aprender uma única convenção visual em vez de três.

**Porquê isto importa comercialmente:** o incidente que originou o lote foi um colega a
reportar bases de produção sem full backup que o produto **tinha detectado mas não
mostrava**. Um monitor que mente por omissão é pior do que um monitor que não existe,
porque gera confiança falsa. Este é o argumento a usar se alguém no V6 sugerir "deixa
verde, é mais bonito".

---

## Unidade 1 — Cartões do Overview deixam de mentir (N/D)

**O que mudou no V3.3:** os cartões de Backup, Backup Gaps e Problemas de BD passaram a
distinguir "zero problemas" de "não consegui ler". Introduzidas as flags
`backupDataAvailable`, `backupGapsAvailable`, `dbDataAvailable` e a constante
`NO_DATA_COLOR = '#6b7280'`.

**Sintoma antes:** servidor com zero dados recolhidos aparecia com "Backup OK" a verde e
"Backup Gaps 0" a verde. Verde por ausência de dados.

**Onde procurar no V6:** `grep` por `backupIssues`, `kpi-ok`, `kpi-alert` no template do
portal. O padrão a substituir é qualquer expressão da forma
`x.length === 0 ? verde : vermelho` que **não** teste primeiro se a resposta teve sucesso.

**Chave i18n nova:** `overview.no_coverage` = `"N/D"` (pt) / `"N/A"` (en) / `"N/D"` (es).

---

## Unidade 2 — Cartão "Por Ambiente"

**O que mudou no V3.3:** duas coisas, ambas por pedido explícito do owner.

1. O título deixou de ser "POR AMBIENTE (CRÍTICO)" e passou a **"Por Ambiente"** —
   chave `kpi_report.by_environment_t`.
2. Os valores deixaram de ser contagens de KPIs críticos e passaram a ser o
   **número de instâncias monitorizadas por ambiente**, lido de
   `instance_availability.ok_by_env`. Clicar num ambiente filtra o relatório.

**Contrato de backend que o V6 tem de ter:** o payload de `instance_availability` precisa
de expor `ok_by_env` como `{PRD: n, QLT: n, TST: n, Undefined: n}`.

**A parte importante — como esse `ok_by_env` é calculado.** No V3.3 é derivado por JOIN à
tabela `KPI_MSSQL_INST_ENVS`:

```sql
SELECT ISNULL(e.Env, 'Undefined') AS Env, COUNT(DISTINCT a.Instance) AS Cnt
FROM dbo.KPI_MSSQL_INST_AVAILABILITY_ACTIVE a WITH (NOLOCK)
LEFT OUTER JOIN dbo.KPI_MSSQL_INST_ENVS e WITH (NOLOCK)
    ON LTRIM(RTRIM(UPPER(e.Instance))) = LTRIM(RTRIM(UPPER(a.Instance)))
WHERE a.Is_Available = 1
GROUP BY ISNULL(e.Env, 'Undefined')
```

**Se o V6 usar `LIKE '%PRD%'` sobre o nome da instância, está errado e tem de mudar.** A
heurística por substring classifica mal qualquer instância cujo nome contenha o token por
acidente, e é silenciosa quando falha. `INST_ENVS` é a fonte de verdade do ambiente.

**Decisão do owner a respeitar:** o cartão conta **só as instâncias que respondem**
(`Is_Available = 1`), não as 62 mapeadas. Foi escolha explícita — não "corrigir" para o
total sem falar com ele.

---

## Unidade 3 — Banner de diagnóstico de rede no Overview

**O problema que resolve:** quando um servidor não responde, o utilizador via cartões
vazios e não tinha como saber se o problema era do servidor monitorizado ou da própria
WatcherDB. Pergunta literal do owner: *"como quem usa o programa vai saber que é problema
na máquina monitorada?"*

**O que mudou no V3.3:** um banner acima dos cartões que mostra quantas verificações
falharam, quais, há quanto tempo, e a causa provável cruzada com o evento do colector.

**Duas regras de honestidade que o banner respeita e que o V6 tem de manter:**

1. **Distinguir "host responde mas SQL está mudo" de "host inalcançável"** — são
   diagnósticos diferentes e levam a acções diferentes (serviço vs rede/firewall).
2. **Nomear a perspectiva.** O banner termina sempre com o aviso de que o diagnóstico é
   *do ponto de vista do colector* e que o servidor pode estar a responder normalmente a
   outros clientes. Sem isto, o produto acusa um servidor saudável de estar em baixo — e
   um DBA que abra um incidente com base numa acusação falsa não volta a confiar no
   produto.

**Chaves i18n novas** (nas três locales, `overview.*`):
`run_diagnostics`, `diag_checks_failed`, `diag_host_up`, `diag_sql_mute`,
`diag_host_unreachable`, `diag_no_event`, `diag_which`, `diag_perspective`.

**Nota de tiering:** isto é diagnóstico descritivo — mostra estado e contexto. Std.
A camada seguinte (emitir o comando de remediação que o DBA deve executar) **não** foi
implementada e a classificação Std/Pro dessa camada está **por decidir pelo owner**. Não
a implementar no V6 sem essa decisão.

---

## Unidade 4 — Modal AlwaysOn mostra o nome da base

**Pedido do owner:** *"aqui poderia ter também o nome do database que não está saudável"*.

**Causa:** a tabela `KPI_MSSQL_ALWAYSON_STATUS_STG` **sempre teve** granularidade por base
(coluna `[Database]`, 405 linhas), mas a query do drill-down nunca a seleccionava. O modal
só conseguia dizer *que servidor* estava mal, nunca *qual base*.

**Diff V3.3** (`api/routers/intelligence_kpis.py`, ramo `kpi_type == "always-on"`):

```sql
     SELECT
         s.AgName,
         s.Instance,
+        s.[Database],
         ISNULL(e.Env, 'Undefined') AS Env,
         ...
-    ORDER BY s.Instance
+    ORDER BY s.Instance, s.[Database]
```

No portal, o bloco `kpiType.includes('always-on')` passou a mostrar a linha `Database:` e
uma linha `Estado:` com o valor real.

**A regra não-óbvia — como ler o estado correctamente.** O colector escreve **uma linha por
réplica**, e só preenche o lado que aquele nó assume:

| Nó | Colunas preenchidas | Colunas vazias |
|---|---|---|
| Primário | `Pri_*` | `Sec_*` |
| Secundário | `Sec_*` | `Pri_*` |

**O lado vazio é NORMAL, não é avaria.** Por isso o estado apresentado tem de ser
`Pri_Synch_Health || Sec_Synch_Health` (o lado que tem valor), e qualquer filtro de
"não saudável" tem de excluir explicitamente vazio e NULL:

```sql
Pri_Synch_Health <> 'HEALTHY' AND Pri_Synch_Health IS NOT NULL AND Pri_Synch_Health <> ''
```

Omitir o `<> ''` faz o produto reportar **toda a frota** como não saudável.

---

## FINDING que afecta o V6 directamente — **NÃO aplicar fix sem consenso**

A coluna `Problem_Reason` da `KPI_MSSQL_ALWAYSON_STATUS_STG` é **falso positivo em 405 de
405 linhas** (100%). O colector escreve-a com a lógica antiga que trata o lado vazio da
réplica como avaria:

| Padrão de linha | Linhas | `Problem_Reason` escrito |
|---|---|---|
| `Sec_*` preenchido, `Pri_*` vazio | 205 | `Health Problem + Sync State` |
| `Pri_*` preenchido, `Sec_*` vazio | 200 | `Secondary Replica Unhealthy ()` |

O parêntesis vazio em `Unhealthy ()` é a assinatura do bug.

**Consequência para o V6:** a `KPI_MSSQL_ALWAYSON_STATUS_AGG_VIEW` expõe
`Problem_Reasons` preenchido em **todos os 21 AGs**, mesmo com `Unhealthy = 0`, porque o
sub-query `pr` lê a coluna crua sem filtro de estado. Qualquer ecrã do V6 que mostre
`Problem_Reasons` da AGG está a mostrar lixo. **Verificar isso no V6 é acção imediata; o
fix da coluna não é.**

**Estado do fix:** já existe escrito em
`WATCHERDB INTELLIGENCE V1/database/FIX_ALWAYSON_PROBLEM_REASON_LOGIC.sql` (31/12/2025),
com 4 secções. **Só duas entraram** — as das views (a `DET_VIEW` devolve 0 linhas e o
`Unhealthy` está correcto). A secção 2, que converte `Problem_Reason` em coluna computada
`PERSISTED` com a lógica certa, **não foi aplicada**: a coluna continua com
`is_computed = 0`.

**Porque é que não se aplica já:** é DDL numa tabela de staging da `WatcherDB_Intelligence`
**partilhada** entre V1, V3.3, V6 e tiers Pro, sujeita ao swap BLUE/GREEN via
`usp_swap_kpi_stg_tables`. Questões por responder antes de tocar:
- o `PERSISTED` interfere com o swap? o par GREEN precisa do mesmo `ALTER`?
- algum consumidor Pro depende do **texto actual** do `Problem_Reason`?
- impacto de escrita com 405 linhas/minuto?

**Contorno que o V3.3 já usa e o V6 deve copiar:** não consumir `s.Problem_Reason`.
Recalcular o motivo na query, a partir das colunas de estado, com o `<> ''` incluído.
Isso dá o resultado certo hoje, sem esperar por DDL nenhum.

---

## Fora de escopo neste lote

- **`collect_server_ping.py`** (resolução de porta de instância nomeada por cache
  aprendida): vive no V1, que é infra partilhada. O V6 herda pela BD assim que for
  aplicado — **não** replicar código.
- **8 ocorrências restantes de `LIKE '%PRD%'`** no V3.3: ficam para commit próprio por
  segurança de rollback. Se o V6 tiver o mesmo padrão, reportar mas não corrigir junto
  com este lote.

## Validação sugerida no V6 (após aplicar)

1. Abrir o Overview de um servidor **sem dados recolhidos** → Backup e Backup Gaps têm de
   mostrar **N/D cinzento**, nunca verde.
2. Cartão Por Ambiente → soma dos ambientes = nº de instâncias com `Is_Available = 1`;
   clicar filtra.
3. Correr `SELECT COUNT(*) FROM dbo.KPI_MSSQL_ALWAYSON_STATUS_DET_VIEW` → se der 0 e
   algum ecrã do V6 ainda mostrar AGs com problema, esse ecrã está a ler a coluna crua.
4. Modal AlwaysOn: só validável visualmente quando existir uma base fora de estado. Com a
   frota saudável o modal vem vazio — **isso é o comportamento correcto**, não uma
   regressão.
