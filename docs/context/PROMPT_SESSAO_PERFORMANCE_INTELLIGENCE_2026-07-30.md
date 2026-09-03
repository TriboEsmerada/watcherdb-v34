# Sessão — Performance da WatcherDB_Intelligence

> Cola isto numa sessão nova. É auto-suficiente: não precisas de contexto anterior.
> Escrito a 2026-07-30 no fecho da sessão de indexação (Wave B).

---

## Quem és e como trabalhas

Consultor. O owner é o único executor. Lês, diagnosticas, propões em blocos; **paras** e esperas.

- `sql_monitoring` é a única identidade que liga à BD, e **só faz SELECT**
- Nenhuma connection string com `Trusted_Connection` ou `Integrated Security`
- DDL, DROP, jobs e alterações a ficheiros: bloco para o owner correr à mão, com **identidade declarada, impacto e rollback anotado antes**
- Lê `docs/context/CONTEXT.md` antes de começar e anexa a decisão no fim
- Podes escrever em `docs/context/` e `.claude/`. Fora disso, handshake

## O alvo

`WatcherDB_Intelligence` em `SQLHDSTST505\I01`. É a BD **partilhada** — V3.3 Standard, V5/V6 Pro e o collector V1 leem-na todos. Qualquer mudança estrutural afecta produtos em simultâneo, e o `watcherdb-v1-intel-specialist` tem **direito de veto**. Despacha-o antes de qualquer alteração de contrato; ele já conhece o histórico desta wave.

---

## O que já está feito — não repitas

Sessão de 29-30/07 fez o diagnóstico de indexação completo. Resultados que **não precisas de refazer**:

| | |
|---|---|
| Fragmentação | **Não é problema.** 2 índices acima de 5% numa base de ~3 GB |
| Estatísticas | Saudáveis. `auto_update_stats` ligado; as `NULL` são de tabelas vazias |
| `page_verify` | Já em `CHECKSUM`; `suspect_pages` vazia |
| `DBCC CHECKDB` | Correu limpo a 29/07 — o primeiro desde a criação da base (06/04) |
| Manutenção agendada | Instalada (SECÇÃO 20, job diário 03:00). Índices reorganizados por desgaste + estatísticas na mesma execução |
| Índices | 34 removidos, 6 melhorados, 2 criados. Família ALWAYSON converge com o canonical |

**Censo (2026-07-30):** 606 índices não-clustered. **189 (31%)** são a assinatura `IX_<tabela>_Instance` + `IX_<tabela>_UpdateTS` gerada pela `usp_setup_environment_tables`.

---

## O trabalho de performance, por ordem de retorno

### 1. As tabelas de ambiente são HEAPS — e é a causa-raiz de tudo

`usp_setup_environment_tables` (canonical linhas ~2320-2409) cria as tabelas `_PRD/_QA/_TST` com `SELECT * INTO ... WHERE 1=0`, que **não copia PK nem clustered index**. São ~90 tabelas em 13 famílias, todas heaps, com dois índices cegos como único acesso.

Isto é performance, não arrumação: heap sem chave significa *forwarded records* a acumular com cada `TRUNCATE`+`INSERT`, e nenhum caminho de acesso ordenado.

**Ordem obrigatória** — pela inversa remove-se o único acesso indexado de dezenas de heaps:
1. Corrigir a proc para criar PK clustered
2. Retrofit de PK nas ~90 tabelas existentes (operação pesada — parecer + ensaio em TST + faseamento)
3. Só então os 189 índices do par cego ficam redundantes e caem em massa

Query para medir o estrago antes de decidir:
```sql
USE [WatcherDB_Intelligence];
SELECT OBJECT_NAME(ps.object_id) AS Tabela, ps.forwarded_record_count,
       ps.page_count, ps.avg_page_space_used_in_percent
FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, 0, NULL, 'DETAILED') ps
WHERE ps.index_id = 0 AND ps.forwarded_record_count > 0
ORDER BY ps.forwarded_record_count DESC;
```

### 2. Escritas desproporcionadas — dois casos medidos

| Tabela | Linhas | Escritas por índice (33 dias) | Leituras |
|---|---|---|---|
| `kg_relations` | 32.025 | 4.992.824 × 4 índices | **zero** |
| `kg_entities` | 33.066 | 4.631.166 × 3 índices | **zero** |

~34 milhões de operações de manutenção de índice sobre tabelas de 32 mil linhas. O grafo de conhecimento está a ser **reconstruído de fio a pavio**, repetidamente. Código V5/V6 — o ganho é deles e a correcção também.

### 3. 651.601 seeks numa tabela de eventos raros

`KPI_MSSQL_ALWAYSON_FAILOVER_HIST` regista *failovers* — dezenas por mês num ambiente saudável. O número é assinatura de verificação linha-a-linha em ciclo no escritor, provavelmente um "este evento já existe?" antes de cada insert. O índice `IX_ALWAYSON_FAILOVER_HIST_TS_Source` foi criado e trata o sintoma. **A causa está no lado V6.**

### 4. Predicado que anula o índice em DEADLOCKS_HIST

`modules/performance/investigators/deadlocks.py:170`:
```sql
WHERE UPPER(REPLACE(Instance_Name, CHAR(92), '_')) = UPPER(REPLACE('...', CHAR(92), '_'))
```
A função sobre a coluna torna o predicado não-SARGable → scan do clustered index numa tabela com duas colunas `NVARCHAR(MAX)` e uma `XML`, para devolver `TOP 10`. Extensão medida: 7 ocorrências nesse ficheiro, 6 em views do canonical.

Remediação: coluna computada `PERSISTED` normalizada + índice sobre ela. Cura: normalizar as chaves na escrita — o formato inconsistente vem da migração de 25/03.

### 5. Retenção das HIST

Maiores tabelas: `FG_USAGE_HIST` 583 MB / 2,3 M linhas · `WatcherDB_Ensemble_Results` 548 MB · `DATAFILES_HIST` 361 MB · `ERRORLOG_HIST` 3,1 M linhas · `KPI_OS_DISK_PERF_HIST` 4,1 M linhas. Existe `PURGE_KPI_HISTORY_RETENTION.sql` — verificar se corre e o que cobre.

### 6. Limpezas pendentes

- **Censo dos 385** índices fora do par cego — a parte lenta, exige análise de consumidor por família
- **`DROP TABLE`** nas 6 tabelas `_OLD`, confirmadas frias desde Dezembro (`sp_rename` da migração BLUE/GREEN, nunca limpo)
- **`KPI_MSSQL_COLLECTION_HISTORY` está vazia** — zero linhas, nunca escrita. É a tabela que devia responder a "as recolhas correram e quanto demoraram". Ponto cego por investigar
- **Cobertura do Componente A**: 7 famílias com fonte de frescura, 5 chegam ao dashboard, ~29 sem nenhuma

---

## Cinco armadilhas que já custaram tempo nesta base

Estas não são teoria. Cada uma produziu uma conclusão errada em 29-30/07, e todas foram apanhadas por verificação.

1. **O canonical não é fonte de verdade sobre o que está a correr.** Aconteceu **cinco vezes**: inferir do `INSTALACAO_COMPLETA_UNIFICADA.sql` e a base viva dizer outra coisa — em índices e na meta de frescura. O ficheiro diz o que um *cliente novo* recebe. As duas divergem por defeito, não por excepção. **Mede sempre na base.**

2. **Ler chaves **e** INCLUDEs.** Classificar redundância pela coluna-chave produz falsos positivos: `IX_DB_State` parecia prefixo redundante e é o único a cobrir `Mirroring_State`, exigido por uma view.

3. **Estatísticas de uso não desempatam índices idênticos.** O optimizador escolhe um arbitrariamente e ignora o outro. Entre duplicados exactos mantém-se o **declarado no canonical**, não o que mostra leituras.

4. **Pares BLUE/GREEN: a metade inactiva mostra zero em tudo.** Confirma o slot activo em `KPI_STG_ACTIVE_TABLE` antes de concluir que algo não é usado.

5. **Família desactivada ≠ índice morto.** Quatro famílias (`BLOCKED_USERS`, `SERVICE_STATUS`, `DB_IO_STATS`, `LONG_LOCKS`) estão em `DEPRECATED_KPIS` (`V1/scripts/run_collections.py:128-139`), desligadas de propósito a 13/05. Os índices delas parecem mortos porque o alimentador está desligado.

**E uma que não é sobre índices:** `is_data_fresh()` valida frescura **por linha**. Collector morto devolve zero linhas → o tile diz "0 problemas" para sempre. Foi esse o ponto cego que escondeu uma falha de mirroring de 13/05 a 17/07. Para "collector parado" o mecanismo certo é o **Componente A** (`api/routers/intelligence/helpers.py:2463`), que trabalha ao nível do grupo. Não confundas os dois.

---

## Método que funcionou

Corre em OODA e verifica antes de afirmar:

1. **Mede na base**, não no ficheiro
2. **Lê o código à volta do match**, não o match — um `grep` localiza, não analisa
3. **Procura o consumidor** antes de classificar algo como descartável
4. **Anota o rollback antes** de propor a alteração
5. **Um bloco de cada vez**, com verificação entre eles

Fonte da verdade a consultar primeiro: memória `reference_v3_3_schema_catalog.md` (tem as regras acima e o censo) e `project_collector_freshness_findings_2026_07.md`.

---

## Primeiro passo sugerido

Antes de qualquer proposta, mede o estado dos heaps (query da secção 1) e cruza com o tamanho das tabelas. Se os *forwarded records* forem significativos, a wave de PK deixa de ser arrumação e passa a ser o item de performance com maior retorno da lista — e justifica o custo do retrofit.

Se vierem baixos, ataca antes o ponto 2 (as escritas do grafo) e o ponto 4 (o predicado dos deadlocks), que são localizados e não exigem tocar em 90 tabelas.
