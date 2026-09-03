# Propagação V6 — Manutenção da BD partilhada (SECÇÃO 20)

> **Veredicto curto: o V6 HERDA tudo. Zero código, zero DDL do lado do V6.**
> Mas há coisas que a AI do V6 tem de saber para não tirar conclusões erradas
> dos dados novos — é para isso que serve este documento.

## 0. Contrato dos dados — ler antes de consumir

A `WatcherDB_Intelligence` é **partilhada**: V1 escreve, V3.3 e V6 lêem. A
manutenção corre **uma vez**, no servidor da Intelligence, e beneficia as três
edições. Não há nada para instalar no V6.

### O que passou a existir

| Objecto | O que é |
|---|---|
| `WDB_MAINTENANCE_LOG` | histórico do que a manutenção fez, linha a linha |
| `usp_maintenance_indexes` | reorganize/rebuild dirigido por fragmentação |
| `usp_maintenance_statistics` | update statistics, FULLSCAN nas `*_HIST` |
| Job `WatcherDB - Maintenance (Index + Statistics)` | **diario 03:00**, 2 passos |

### Armadilhas de leitura do `WDB_MAINTENANCE_LOG`

**1. `Action_Taken = 'SKIPPED_CHURN'` não é um erro.** É o desenho. As tabelas
`*_STG_BLUE*`/`*_STG_GREEN*` são truncadas a cada ciclo, portanto reconstruí-las
seria desperdício. Um dashboard que conte `SKIPPED_CHURN` como falha de
manutenção está a ler mal.

**2. `SKIPPED_CHURN` com `Frag_Pct` alto NÃO é um alarme.** *(corrigido após
verificação — a primeira versão deste documento afirmava o contrário.)*
Chegou-se a escrever que fragmentação alta ali provava um `TRUNCATE` falhado com
recurso ao `DELETE` de fallback. **Não se confirmou:** não há vista schema-bound
nem FK a bloquear o truncate, e o sintoma aparece em várias famílias
(`BACKUP_EXEC_FAILURES`, `ERRORLOG`), em PRD, QA e TST. A explicação provável é
banal: em **heaps**, `avg_fragmentation_in_percent` mede fragmentação de
*extents*, e um heap truncado e recarregado com inserts em lote fica naturalmente
com páginas não contíguas. **É esperado.** Um painel que trate isto como avaria
gera um falso alarme por dia.

**3. `Object_Name = '(time box)'`** é uma linha de controlo, não uma tabela.
Significa que a execução parou aos 45 minutos e o resto ficou para o dia
seguinte. Filtrar em qualquer contagem por objecto.

**4. `Action_Taken = 'ERROR'` é isolado, não fatal.** Um índice que falha não
aborta os restantes. Um erro no log **não** quer dizer que a manutenção não correu.

*(As três seguintes foram observadas no primeiro ensaio real, 2026-07-29.)*

**5. `Run_Start` é por *procedure*, não por execução do job.** O job tem 2 passos
(índices, estatísticas) e cada um grava o seu `Run_Start`. Filtrar por
`MAX(Run_Start)` mostra apenas o ÚLTIMO passo — tipicamente as estatísticas — e
dá a impressão falsa de que os índices não foram tratados. Agrupar por
`Run_Start` em vez de filtrar pelo máximo.

**6. `DRY_RUN` fica no mesmo log que a execução real.** Os ensaios não são
separados. Qualquer contagem de "o que a manutenção fez" tem de excluir
`Action_Taken = 'DRY_RUN'`, senão o ensaio é contado como trabalho.

**7. `Duration_Ms` é `NULL` em `SKIPPED_CHURN` e `DRY_RUN`** (não houve trabalho).
`SUM`/`AVG` devolvem `NULL`, não `0` — usar `ISNULL` em qualquer agregação.

### Porque é diária, e porque o limiar de rebuild é alto

O servidor da Intelligence é **Standard Edition**: `REBUILD` é **offline** e
bloqueia; `REORGANIZE` é online em qualquer edição. Correr **todos os dias**
impede a fragmentação de chegar aos 30%, portanto na prática só corre
`REORGANIZE` — o ensaio confirmou: zero rebuilds. Diária é *mais* segura que
semanal, não menos.

**Custo em log (relevante para quem avaliar):** a BD está em `FULL recovery` e já
gera **1,5–3,5 GB de log por hora** só com os collectors (ficheiro de log 9,2 GB,
maior que os 8,7 GB de dados). O reorganize diário acrescenta ~300–500 MB uma vez
por dia — marginal. Se alguém propuser baixar o limiar de rebuild, é aí que o
custo passaria a doer.

## A. O que o V6 pode querer fazer com isto (opcional)

Nada é obrigatório. Mas há duas leituras que fariam sentido no portal V6, se e
quando houver espaço:

1. **Frescura da manutenção** — `MAX(Run_Start)` do log responde a "quando é que
   esta BD foi mantida pela última vez?". Encaixa no mesmo espírito do
   Collector Health.
2. **Tendência de fragmentação ao longo do tempo** — o log acumula `Frag_Pct` por
   objecto e data. Um índice que sobe consistentemente apesar da manutenção diária
   é sinal de padrão de escrita a mudar. *(Não usar `SKIPPED_CHURN` para isto —
   ver armadilha 2.)*

Ambas são **leitura**; nenhuma exige escrita nem DDL.

## B. O que NÃO fazer

- **Não criar um segundo job de manutenção no V6.** A BD é uma só; dois jobs a
  reorganizar os mesmos índices colidiriam. Se o V6 tiver BD própria algures,
  aí sim — mas então é outro contexto e este documento não se aplica.
- **Não separar índices e estatísticas em dois jobs.** O próprio produto avisa
  que rebuild invalida estatísticas e que devem correr em sequência.

## C. Verificação (read-only, no dia seguinte à primeira execução)

```sql
USE WatcherDB_Intelligence;

-- Correu?
SELECT MAX(Run_Start) AS Ultima_Manutencao FROM dbo.WDB_MAINTENANCE_LOG;

-- O que fez, por passo e por tipo de accao (Run_Start e' por PROC, nao por job;
-- DRY_RUN excluido para nao contar o ensaio como trabalho -- ver armadilhas 5-7)
SELECT Run_Start, Action_Taken, COUNT(*) AS N, SUM(ISNULL(Duration_Ms,0))/1000 AS Segundos
FROM dbo.WDB_MAINTENANCE_LOG
WHERE Run_Start >= DATEADD(DAY, -2, GETDATE())
  AND Action_Taken <> 'DRY_RUN'
GROUP BY Run_Start, Action_Taken
ORDER BY Run_Start DESC, N DESC;

-- Churn ignorado (informativo, NAO e' alarme -- ver armadilha 2)
SELECT Object_Name, Frag_Pct, Page_Count
FROM dbo.WDB_MAINTENANCE_LOG
WHERE Action_Taken = 'SKIPPED_CHURN' AND Object_Name <> '(time box)'
ORDER BY Frag_Pct DESC;
```
