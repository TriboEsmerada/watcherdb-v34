# Propagação para o V6 — `Volume_Free_MB` e cobertura de volumes

**Data:** 2026-09-24
**Origem:** WatcherDB V3.4 + WatcherDB Intelligence V1
**Commits:** `e38409f`, `ed35ccc` (V1, ramo `wave-b-indexacao-dmv`, publicados)

Três correções no recolhedor e no canónico. O V6 tem cópias próprias destes
ficheiros — confirma cada uma na tua árvore antes de aplicar, porque a V1 e a
V3.4 já tinham divergido entre si e é provável que o V6 também tenha.

---

## 1. `Volume_Free_MB` juntava pelo prefixo do caminho (`ed35ccc`)

### O defeito

Em `scripts/collectors/collect_datafiles.py`, a tabela temporária
`#VolumeInfo` é construída assim:

```sql
SELECT DISTINCT
    mf.database_id, mf.file_id,              -- a chave certa, recolhida…
    LEFT(vs.volume_mount_point, 3) AS Drive, -- …e deitada fora
    CAST(vs.available_bytes / 1024.0 / 1024.0 AS DECIMAL(18,2)) AS Volume_Free_MB
INTO #VolumeInfo
FROM sys.master_files mf
CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs;
```

Como `database_id`/`file_id` são únicos por ficheiro, o `DISTINCT` não colapsa
nada: `#VolumeInfo` fica com **uma linha por ficheiro da instância**. A seguir:

```sql
UPDATE d SET d.Volume_Free_MB = ISNULL(v.Volume_Free_MB, 0)
FROM #Datafiles d
LEFT JOIN #VolumeInfo v ON d.Drive = v.Drive;   -- 3 caracteres
```

Numa instância onde uma letra aloja vários volumes (mount points NTFS, CSV de
cluster), dezenas de linhas partilham a chave `'F:\'` com `Volume_Free_MB`
**diferente** — cada uma do seu volume real. Um `UPDATE ... FROM x LEFT JOIN y`
com `y` não-único é **não-determinístico** no SQL Server: escolhe um candidato
qualquer. Um ficheiro num volume quase cheio herda o espaço livre de um volume
irmão com folga, ou o contrário.

### Porque passou despercebido oito meses

Num servidor sem mount points todos os candidatos de `'F:\'` têm o mesmo valor
— o resultado sai certo por acidente. O defeito só morde onde uma letra aloja
vários volumes, que é a topologia típica de Failover Cluster / S2D, ou seja os
servidores de maior valor.

E o workaround do read-path não o apanha. `tlog_usage_classes.py` faz
`MIN(NULLIF(Volume_Free_MB, 0))`, que só protege o caso "sem correspondência"
(0 → NULL → sem visibilidade). Aqui há sempre correspondência e o valor é
plausível: **dado errado silencioso**, sem sinal que o denuncie.

### A correção

Três alterações, todas dentro da string `QUERY` do recolhedor:

1. `#Datafiles` ganha `DB_Id INT NULL, File_Id INT NULL` **no fim** da definição
   — o `INSERT` dinâmico é posicional e não tem lista de colunas, por isso
   acrescentar a meio deslocaria tudo.
2. O `INSERT` dinâmico passa a fornecer `DB_ID()` e `df.file_id` nas duas
   posições novas. `DB_ID()` corre depois do `USE [base]`, logo devolve o id
   correto.
3. O `UPDATE` junta por `ON d.DB_Id = v.database_id AND d.File_Id = v.file_id`.

O `SELECT` final **não** projeta as colunas novas. `KPI_MSSQL_DATAFILES_STG`, a
lista `COLUMNS` e o contrato de leitura ficam idênticos — sem DDL, sem
coordenação entre tiers.

### Medição na frota, antes e depois

Método: para cada ficheiro, derivar o volume correto pelo prefixo **mais longo**
do caminho físico que corresponda a um `Drive` da `KPI_MSSQL_DISK_USAGE_STG`, e
comparar com o `Volume_Free_MB` que o recolhedor gravou.

| | Ficheiros | OK | ERRADO |
|---|---|---|---|
| Pré-fix (2026-09-23 14:52) | 2 982 | 1 580 | **1 402 (47%)** |
| Pós-fix (2026-09-23 16:13) | 3 948 | 3 948 | **0** |

Casos concretos:

- `CAGENPRD06_I06` — os ficheiros de `C:\ClusterStorage\I06_LOGS\` (61,9 GB
  livres) reportavam 219,1 GB, o valor do `I06_DATA0`. Três vezes e meia o
  espaço que existe.
- `SQLIDSPRD03_I01` — ~30 volumes sob `F:`. Ficheiros em volumes com 329,9 /
  302,6 / 262,5 / 256,7 GB livres reportavam **todos** os 127,9 GB do
  `F:\Hist_Data_11\`. E os logs em `L:\Logs1\` (1 011,9 GB) reportavam os
  1 564,5 GB do `L:\Logs2\`.

A `DATAFILES` é a fonte de `Volume_Free_MB` em **1 023 das 1 054 bases**, por
isso este é o caminho principal e não um recurso secundário.

### O que isto alimenta

Os verdicts `VOLUME_SATURADO`, `VOLUME_BAIXO` e `AUTOGROW_NAO_CABE` em
`api/routers/intelligence/tlog_usage_classes.py` dependem diretamente deste
valor. Antes da correção podiam ser falsos-negativos (a mascarar disco cheio a
sério) ou falsos-positivos, sem padrão previsível.

### Query de verificação no V6

Corre antes e depois de aplicares. Esperado depois: zero `ERRADO`.

```sql
WITH esperado AS (
    SELECT df.Volume_Free_MB AS Obtido_MB,
           du.Free_MB        AS Esperado_MB,
           ROW_NUMBER() OVER (PARTITION BY df.Instance, df.[Database], df.File_Name
                              ORDER BY LEN(du.Drive) DESC) AS rn
    FROM dbo.KPI_MSSQL_DATAFILES_STG df WITH (NOLOCK)
    JOIN dbo.KPI_MSSQL_DISK_USAGE_STG du WITH (NOLOCK)
      ON du.Instance = df.Instance
     AND df.Physical_Path LIKE REPLACE(du.Drive, '[', '[[]') + '%'
    WHERE df.Volume_Free_MB > 0
)
SELECT COUNT(*) AS Verificados,
       SUM(CASE WHEN ABS(Esperado_MB - Obtido_MB) <= 1024 THEN 1 ELSE 0 END) AS OK,
       SUM(CASE WHEN ABS(Esperado_MB - Obtido_MB) >  1024 THEN 1 ELSE 0 END) AS ERRADO
FROM esperado WHERE rn = 1;
```

A tolerância de 1 GB cobre o desfasamento entre as duas colheitas. As
diferenças do defeito são de dezenas a centenas de GB, não se confundem.

Cuidado ao interpretar: uma verificação mais fraca — confirmar que o valor
corresponde a *algum* volume da instância — dá "OK" nos dois casos, porque o
valor errado também vinha de um volume irmão da mesma instância. Tem de ser
pelo prefixo mais longo.

---

## 2. Volumes dedicados a LOG eram invisíveis (`e38409f`)

`collect_disk_usage.py` e `watcherdb_intelligence/collectors/async_data_collector.py`
tinham `WHERE mf.type = 0` na consulta a `sys.master_files`. Só ficheiros de
dados entravam, logo um volume que só aloja logs (`L:`, `H:`, `I:`) nunca era
passado ao `dm_os_volume_stats` e **a linha nunca chegava a existir** — sem
NULL, sem erro, sem sinal. O KPI Disk Space ficava cego ao volume que enche
quando um log cresce, em 33 de 44 instâncias.

Efeito medido na frota: 225 → **279 volumes** (+24%) depois do restart.

E destapou logo um caso real: `SQLHDSPRD214_I01`, volume `L:` com 101 GB e
~10 MB livres (0,01%), onde um único log (`DBADashDB_log`, 97,3 GB, 100% usado)
ocupava 96% do volume e as 12 bases nesse disco não conseguiam crescer. Até ao
commit, invisível no portal.

**Alinhamento:** os dois recolhedores ficam consistentes com
`collect_datafiles.py` (`#VolumeInfo` sem filtro) e `collect_file_io.py`
(`mf.type IN (0,1)`).

---

## 3. Canónico: `Drive` passa a `VARCHAR(260)`

Produção já estava a `varchar(256)` — alargada à mão algures em Dez/2025 (ver
`FIX_DRIVE_COLUMN_SIZE.sql`, que teve de dropar e recriar a PK porque `Drive` é
chave na `DISK_USAGE`). O canónico nunca aprendeu, e as duas coisas divergiram
~9 meses sem ninguém dar por isso.

Uma instalação de raiz a partir do canónico de hoje cria as tabelas a
`VARCHAR(8)` e a recolha rebenta com *String or binary data would be truncated*
no primeiro servidor com mount points. O caso mais comprido na frota é
`C:\ClusterStorage\I06_TEMPDB\`, com 29 caracteres.

E o `e38409f` agrava isto: ao trazer os volumes de log, traz precisamente os que
aparecem como mount points em cluster (`L:\Logs1\`, `C:\ClusterStorage\I06_LOGS\`).

**Alterar** — `KPI_MSSQL_DISK_USAGE_STG` e `KPI_MSSQL_DISK_USAGE_HIST`, em cada
cópia do canónico que o V6 tenha.

**Não alterar, deliberadamente:**

| Alvo | Porquê |
|---|---|
| `KPI_OS_DISK_PERF_STG` / `_HIST` / `@Drive` de `usp_OS_Disk_Upsert` | Família WMI: grava só a letra, `MAX(LEN(Drive)) = 2` em produção. Alargar antes de resolver o filtro `not d.Name.endswith(":")` em `os_performance.py:524` não muda nada. |
| `KPI_MSSQL_DATAFILES_STG.Drive` (`VARCHAR(10)`) | O recolhedor grava `LEFT(caminho, 3)` e o `ed35ccc` deixou de depender dele. Guardar o mount point completo é trabalho próprio, com o seu teste. |

Efeito em produção: **nenhum** — as tabelas vivas já estão a 256.

---

## Cuidados ao aplicar no V6

1. **Confirma os números de linha na tua árvore.** A V1 e a V3.4 têm cópias do
   `INSTALACAO_COMPLETA_UNIFICADA.sql` com linhas diferentes para as mesmas
   tabelas. Durante esta sessão, duas análises chegaram a contagens diferentes
   por estarem a ler ficheiros diferentes. Usa âncora de texto, não número de
   linha.
2. **O `INSERT` dinâmico do `collect_datafiles.py` é posicional**, sem lista de
   colunas. Se acrescentares colunas à `#Datafiles` sem as fornecer no `SELECT`,
   o recolhedor rebenta em *todas* as bases, e o `BEGIN CATCH END CATCH` vazio
   engole o erro por base — ficas com a tabela vazia e nenhuma mensagem. Há um
   teste a guardar isto (`test_o_insert_dinamico_preenche_a_identidade`).
3. **Confirma que a coleta é posterior ao teu deploy** antes de julgar o
   resultado. `MAX(Update_TS)` na `KPI_MSSQL_DATAFILES_STG` contra a hora do
   restart. Nesta sessão medimos dados pré-fix e quase concluímos que a
   correção não funcionava.

---

## Ficheiros de aplicação

Scripts idempotentes com `--check` (valida âncoras, não escreve) e `--preview <dir>`:

| Script | Árvore |
|---|---|
| `docs/context/DATAFILES_VOLUME_JOIN_2026-09-23_apply.py` | V1 |
| `docs/context/CANONICAL_DRIVE_260_2026-09-24_apply.py` | V1 |
| `docs/context/CANONICAL_DRIVE_260_2026-09-24_apply.py` | V3.4 |

Testes: `tests/unit/test_datafiles_volume_join_20260923.py` (7 âncoras, offline,
sem BD).

---

## Aberto, não tratado aqui

Levantado durante a sessão, por dimensionar:

- **Cobertura do `collect_datafiles`.** Cada execução recolhe de **18 ou 19 de
  42 servidores**, e o conjunto muda. `TIMEOUT_SECONDS = 60` em
  `base_collector.py:118`; as falhas são ~12 timeouts, 5× erro 976 (secundário
  de AG sem leitura), 1× erro 978 (exige `ApplicationIntent=ReadOnly`) e 1× erro
  139 (`OATXP01` é anterior ao SQL Server 2008 e não suporta
  `DECLARE @sql NVARCHAR(MAX) = N''`). Corrigir o JOIN torna corretos os
  ficheiros que lá estão; não põe lá os que faltam. **Vale mais do que tudo o
  que está acima.**
- **Gravação silenciosa.** A execução das 15:19 de 2026-09-23 recolheu 1 936
  registos e nenhum dos seis slots BLUE/GREEN ficou atualizado. O log não tem
  uma única linha de armazenamento, nem de sucesso nem de falha.
- **`KPI_MSSQL_DISK_USAGE_AGG_VIEW` conta linhas.** Uma instância com 31
  volumes pesa dez vezes mais na contagem da frota do que uma com 3, sem estar
  pior. E um LUN de 4 TB a 12% livre (480 GB de folga) conta igual a um `C:` de
  80 GB a 12% (9,6 GB).
