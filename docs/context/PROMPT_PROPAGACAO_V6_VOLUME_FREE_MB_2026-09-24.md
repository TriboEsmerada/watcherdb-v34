# Propagação para o V6 — `Volume_Free_MB` e cobertura de volumes

**Data:** 2026-09-24
**Origem:** WatcherDB V3.4 + WatcherDB Intelligence V1
**Commits:** `e38409f`, `ed35ccc`, `18f9117` (V1, ramo `wave-b-indexacao-dmv`, publicados)

Quatro correções no recolhedor e no canónico. O V6 tem cópias próprias destes
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

## 4. O recolhedor só via 43 das 59 instâncias (`18f9117`)

> Esta era a rubrica "Cobertura do `collect_datafiles`" que a versão anterior
> desta nota deixava em aberto, com a observação *"vale mais do que tudo o que
> está acima"*. Ficou resolvida na mesma sessão. **Aplica esta antes das outras
> três** — corrigir o JOIN torna corretos os ficheiros que lá estão; isto põe lá
> os que faltam.

### O defeito

`collect_datafiles.py` percorre as bases de `sys.databases` e monta, por base,
um bloco `USE [base]; ... INSERT #Datafiles ...` dentro de um `N'...'`, cada um
envolvido em `BEGIN TRY ... BEGIN CATCH END CATCH`.

O `CATCH` vazio dava a ilusão de que uma base problemática era simplesmente
saltada. Não é o que acontece. Numa réplica **secundária** de AG, o `USE` falha
com **erro 976** (*The target database is not configured for online access*), e
o 976 tem severidade que aborta o lote inteiro — o `TRY/CATCH` por base **não o
apanha**. Basta uma base nessas condições para o servidor inteiro não entregar
nada, com as outras ~90 bases dele. Daí o número oscilar entre execuções: muda
conforme qual a base que calha primeiro e qual o estado do AG nesse momento.

O mesmo vale para o **978** (réplica legível que exige
`ApplicationIntent=ReadOnly`) e para o **916** (a conta não tem acesso à base).

### Porque este ficheiro ficou para trás

Não é um defeito novo. O `CHANGELOG_JOBS_COLETA.md:406-414` regista que em
**2026-02-17** este exato problema foi corrigido nos outros três recolhedores
com SQL dinâmico por base. O `collect_datafiles.py` ficou de fora dessa wave e
era o único que ainda dependia só do `CATCH`. **Confirma na tua árvore se o V6
herdou a wave de Fevereiro completa ou pela metade.**

### A correção

Filtrar **antes** do loop, em vez de esperar que o `CATCH` salve. É o filtro já
provado em `collect_tlog_usage.py:41-47`:

```sql
DECLARE @SqlVersion INT = CAST(SERVERPROPERTY('ProductMajorVersion') AS INT);

IF OBJECT_ID('tempdb..#AGSecondary') IS NOT NULL DROP TABLE #AGSecondary;
CREATE TABLE #AGSecondary (database_id INT);

IF @SqlVersion >= 11
BEGIN
    INSERT INTO #AGSecondary (database_id)
    EXEC sys.sp_executesql N'
        SELECT DISTINCT drs.database_id
        FROM sys.dm_hadr_database_replica_states drs
        INNER JOIN sys.dm_hadr_availability_replica_states ars
                ON ars.replica_id = drs.replica_id
        WHERE drs.is_local = 1 AND ars.role_desc = ''SECONDARY''';
END
```

e, no `WHERE` que escolhe as bases:

```sql
AND HAS_DBACCESS(d.name) = 1
AND d.database_id NOT IN (SELECT database_id FROM #AGSecondary);
```

O `TRY/CATCH` fica como defesa secundária, não como mecanismo primário.

**O gate de versão não é decorativo.** As DMV `sys.dm_hadr_*` só existem em SQL
2012+. Se o texto que as menciona não estiver dentro de um `sp_executesql`
aninhado **e** atrás do `ProductMajorVersion >= 11`, o lote inteiro falha a
compilar nas instâncias antigas da frota (2008 R2) — trocavas um buraco de
cobertura por outro maior. Com o gate, nessas instâncias `#AGSecondary` fica
vazia e `NOT IN (vazio)` deixa passar tudo, que é o comportamento certo: num
servidor sem AG não há secundários para excluir.

### Bónus na mesma passagem

`FILEPROPERTY(df.name, 'SpaceUsed')` era chamado **três vezes por ficheiro**
(espaço usado, espaço livre e percentagem). Passa a uma só, por `CROSS APPLY`:

```sql
CROSS APPLY (SELECT FILEPROPERTY(df.name, 'SpaceUsed') AS SpaceUsedPages) su
```

No `SQLIDSPRD03_I01` são ~1 490 leituras em vez de ~4 460, e as três colunas
passam a ser coerentes entre si por virem da mesma leitura.

### A esteira, medida antes de aplicar

O filtro exclui **todos** os secundários locais, incluindo os legíveis. Num
servidor que hoje funcione e tenha secundários legíveis, esses ficheiros
deixariam de ser recolhidos. Medida na frota: das **191** bases de AG com
ficheiros, as **191** tinham linha na `KPI_MSSQL_TLOG_USAGE_ACTIVE` — que já
aplica este mesmo filtro, logo foram recolhidas no primário. Perda: **zero**.

Corre o equivalente no V6 antes de aplicar:
`docs/context/sql/esteira_filtro_ag_2026-09-24.sql`.

### Medição na frota, antes e depois

| | Antes | Depois |
|---|---|---|
| Instâncias com ficheiros | 43 (18-19 nalguns ciclos) | **58 de 59** |
| Instâncias em falta | 16 | **1** (`SQLHDSPRD213_I01`, 31,96% livre) |
| Bases sem ficheiro de log | 37 em 17 instâncias | **8 em 3** |
| Coerência do `Volume_Free_MB` | 3 948 / 0 errados | **7 709 / 0 errados** |

As instâncias recuperadas incluem as que mais importavam: `SQLMDMPRD04_I01`
(2,81% livre), `SQLHDSPRD405_I01` (8,82%), `SQLMDMPRD02_I01` (10,67%).

A última linha é o no-regression do `ed35ccc` (secção 1): o número de ficheiros
quase duplicou e continuam zero errados. **Corre-a depois de aplicares** — é a
melhor prova de que as duas correções seguram juntas.

### Consequência para o KPI de T-Log

O ramo `LEGACY` — inventado a 21/09 para classificar bases sem ficheiro de log
conhecido — **não é uma categoria legítima de bases**. É este buraco de
cobertura com outro nome. Caiu de 37 bases para 8. Se o V6 tem a mesma
classificação, revê-a depois de aplicar: o que sobra são poucos casos e merecem
diagnóstico próprio, não um ramo de fallback.

### Armadilha do ficheiro

Todo o corpo do SQL por base vive dentro de um template `N'...'`. **Qualquer
plica solta fecha o literal**, incluindo dentro de um comentário. A primeira
versão deste lote levava um comentário em português abreviado (`le' o ficheiro`)
e os 6 servidores de TST responderam
`Incorrect syntax near 'o'. (102)`. Apanhado pelo `--dry-run`, zero registos
gravados. Há um teste a guardar isto
(`test_sem_plicas_soltas_no_sql_dinamico`) que distingue as três plicas
legítimas de concatenação (`USE ' + QUOTENAME(d.name) + N';`) das ilegítimas.

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
| `docs/context/DATAFILES_COBERTURA_2026-09-24_apply.py` | V1 |
| `docs/context/CANONICAL_DRIVE_260_2026-09-24_apply.py` | V1 |
| `docs/context/CANONICAL_DRIVE_260_2026-09-24_apply.py` | V3.4 |

Testes, offline e sem BD:
`tests/unit/test_datafiles_volume_join_20260923.py` (7 âncoras) e
`tests/unit/test_datafiles_cobertura_20260924.py` (10 âncoras).

Consultas de verificação (V3.4, correm com `docs/context/sql/_run.py`, só
leitura): `coerencia_volume_free_2026-09-23.sql`,
`cobertura_datafiles_2026-09-24.sql`, `esteira_filtro_ag_2026-09-24.sql`.

---

## Aberto, não tratado aqui

Levantado durante a sessão, por dimensionar:

- **SQL Server 2005/2008 no `collect_datafiles`.** Resolvida a cobertura
  (secção 4), sobra o `OATXP01`: erro **139**, porque é anterior ao SQL Server
  2008 e não suporta `DECLARE @sql NVARCHAR(MAX) = N''` (inicialização na mesma
  linha da declaração). Exige separar declaração de atribuição em todo o
  recolhedor, e provavelmente o caminho de cursor completo. É a única instância
  da frota nessa condição.
- **Gravação silenciosa.** A execução das 15:19 de 2026-09-23 recolheu 1 936
  registos e nenhum dos seis slots BLUE/GREEN ficou atualizado. O log não tem
  uma única linha de armazenamento, nem de sucesso nem de falha.
- **`KPI_MSSQL_DISK_USAGE_AGG_VIEW` conta linhas.** Uma instância com 31
  volumes pesa dez vezes mais na contagem da frota do que uma com 3, sem estar
  pior. E um LUN de 4 TB a 12% livre (480 GB de folga) conta igual a um `C:` de
  80 GB a 12% (9,6 GB).
