# AVISO à equipa V6 — antes de aplicar o DDL do `Problem_Reason`

Destinatário: quem cuida do assistente de IA do V6.
Origem: sessão de 07/08, parecer `watcherdb-v1-intel-specialist`.
**Enviar ANTES de correr o DDL, não depois.** É esse o ponto deste aviso.

---

## O que vai mudar

A coluna `Problem_Reason` da `KPI_MSSQL_ALWAYSON_STATUS_STG` (BD partilhada
`WatcherDB_Intelligence`) vai passar de **coluna física** a **coluna computada
`PERSISTED`** com a lógica corrigida — script já escrito, secção 2 de
`WATCHERDB INTELLIGENCE V1/database/FIX_ALWAYSON_PROBLEM_REASON_LOGIC.sql`.

## Porque é que isto vos afecta

`services/tool_orchestrator.py`, na função `_tool_failover_history`, usa
**a presença** desta coluna como proxy de detecção de failover:

```python
Problem_Reason IS NOT NULL AND LEN(...) > 0
```

Hoje a coluna está preenchida em praticamente todas as linhas com valores que
são falso positivo. Logo, o assistente está a gerar evidências `WARNING` /
`CRITICAL` de failover em quase 100% dos casos.

**Depois do DDL, esses alarmes vão cair a pique.**

> Isso é a correcção a funcionar, **não** uma regressão do assistente.

Se ninguém for avisado, a queda vai ser lida como "o assistente deixou de
detectar failovers" — e alguém vai gastar uma sessão a investigar um bug que
não existe.

## Contexto de porque a coluna está podre

O colector escreve `NULL` no lado da réplica que aquele nó não assume — o
primário preenche `Pri_*` e deixa `Sec_*` vazio, o secundário faz o inverso.
**O lado vazio é normal.** Duas coisas conspiraram:

1. O colector faz `fillna("")` (`scripts/collectors/collect_alwayson_status.py`),
   convertendo esse `NULL` legítimo numa string vazia.
2. A lógica da coluna só testa `IS NOT NULL`, nunca `<> ''`.

Resultado: 205 linhas com `Health Problem + Sync State` e 200 com
`Secondary Replica Unhealthy ()` — o parêntesis vazio é a assinatura do bug.

**Refinamento apurado a 07/08:** a coluna na BD viva é **física**
(`is_computed = 0`, confirmado), e **nada a reescreve** — a lista de colunas
do colector é explícita e não a inclui, não há trigger, e a única escrita SQL
é um backfill pontual de 29/12/2025. Ou seja, os valores estão **congelados**
há mais de sete meses. O DDL não corrige apenas a lógica: torna a coluna viva.

## O que não muda

- **Não interage com o swap BLUE/GREEN**: o AlwaysOn Status não participa do
  swap. As tabelas `_STG_BLUE`/`_STG_GREEN` existem mas estão órfãs.
- **Ninguém depende do texto exacto** — todos os consumidores testam presença,
  não fazem parsing. Não há contrato a proteger.
- **Impacto de escrita desprezável** (~405 linhas por ciclo).

## Contorno já aplicado, independente do DDL

O V3.3 (`676da69`) e o V6 (`1997848`) já **deixaram de consumir a coluna** nos
respectivos drill-downs de AlwaysOn: recalculam o motivo a partir das colunas
de estado, com o `<> ''` incluído. Isso resolve o ecrã hoje. O DDL resolve para
todos os outros consumidores — incluindo o vosso.

⚠️ Se recalcularem por vossa conta, **o `<> ''` não é opcional**: sem ele o
produto reporta a frota inteira como não saudável.
