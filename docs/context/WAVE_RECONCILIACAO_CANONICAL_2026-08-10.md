# Wave Reconciliação Canonical ↔ BD Viva — 2026-08-10

Origem: pareceres challenger + v1-intel-specialist (2026-08-10) + verificação na BD
viva pelo owner (`sys.sql_modules` em SQLHDSTST505\I01, WatcherDB_Intelligence).
Decisão owner: GO à reconciliação; configurabilidade dos 5 KPIs continua GATED
(secção 6.1 do DESIGN_THRESHOLDS_CLIENTE_2026-08-04.md por preencher).

## Prova viva (owner correu, 2026-08-10)

| View | Canonical (INSTALACAO) | BD viva | Drift |
|---|---|---|---|
| KPI_MSSQL_PROCESSES_AGG_VIEW | 500/1000 sessões totais, sem Runnable_Count, lê _STG sem NOLOCK | 20/50 runnable + Total/Runnable/Suspended/Sleeping + Last_Check, lê _STG WITH (NOLOCK) | SIM — thresholds + colunas |
| KPI_MSSQL_TLOG_USAGE_AGG_VIEW | 70/90, lê _STG | 85/95 + Total_Databases + Last_Check, lê _ACTIVE WITH (NOLOCK) | SIM — thresholds + fonte |
| KPI_MSSQL_BACKUPS_AGG_VIEW | 24/48h, lê _STG | 24/48h, lê _ACTIVE WITH (NOLOCK) | Só fonte (_STG→_ACTIVE) |

As definições vivas coincidem carácter-a-carácter com `SPRINT5_FIX_ALL_VIEWS_NOLOCK.sql`
(secções 1, 13, 16) ⇒ SPRINT5 é a fonte fidedigna para as DET também (não verificadas
individualmente na BD — ver pergunta Q1 abaixo).

Consumo verificado (grep V3.3 + V6, 2026-08-10):
- BACKUPS_AGG_VIEW: **zero consumidores** nos dois produtos (colunas Critical/Warning mortas).
- PROCESSES_AGG_VIEW: V3.3 (helpers/intelligence_kpis) + V6 (4 sítios).
- TLOG_USAGE_AGG_VIEW: V3.3 + V6 (6 sítios).
- DEADLOCKS/DISK/INTEGRITY: V6 consome em 8/13/22 sítios respectivamente — relevante
  para a decisão FUTURA de configurabilidade (Padrão A teria blast radius V6), não
  para esta wave.

## Edits propostos ao canonical `WATCHERDB INTELLIGENCE V1/database/INSTALACAO_COMPLETA_UNIFICADA.sql`

E1. PROCESSES_AGG_VIEW (~linha 3455): substituir pela definição viva (20/50 runnable,
    colunas novas, NOLOCK; mantém _STG — é assim que está vivo).
E2. TLOG_USAGE_AGG_VIEW (~3507): substituir pela viva (85/95, _ACTIVE, NOLOCK,
    Total_Databases, Last_Check).
E3. TLOG_USAGE_DET_VIEW (~3528): substituir pela SPRINT5 §17 (85/95, _ACTIVE, SEM
    WHERE >=70; colunas Log_Size_MB/Log_Used_MB em vez de Current_MB/Used_MB).
E4. BACKUPS_AGG_VIEW (~3560): FROM _STG → _ACTIVE + NOLOCK (thresholds inalterados).
E5. BACKUPS_DET_VIEW (~3583): substituir pela SPRINT5 §2 (_ACTIVE, sem WHERE,
    Backup_Size_MB cru em vez de Backup_Size_GB).
E6. DEADLOCKS: bloco morto AGG (~3764-3786) — a definição é superseded pela SECÇÃO
    18.2 (~11388, com State/Severity) que corre depois no mesmo script. Substituir o
    bloco morto por comentário-ponteiro para a 18.2. Verificar se o DET (~3788) está
    na mesma situação face à 18.3 (~11422).

## Perguntas ao V1 specialist (bloqueiam aplicação)

Q1. TLOG_DET e BACKUPS_DET não foram verificadas na BD viva — aceitas SPRINT5 como
    fonte, ou exigimos SELECT de confirmação antes? Há consumidores V3.3/V6 das DET
    cujas colunas mudam (Available%/Available_GB desaparecem na TLOG_DET;
    Backup_Size_GB na BACKUPS_DET)?
Q2. ORDEM DO SCRIPT: as views passam a referenciar KPI_MSSQL_TLOG_USAGE_ACTIVE e
    KPI_MSSQL_BACKUPS_ACTIVE. Em que secção do INSTALACAO são criados os
    synonyms/objectos _ACTIVE? Se for DEPOIS da secção de views (~3500), o fresh
    install parte (CREATE VIEW exige objecto existente). Solução preferida se sim?
Q3. DEADLOCKS DET: o bloco ~3788 também é morto face à 18.3? Ponteiro nos dois?
Q4. PROCESSES_DET fica intocado (SPRINT5 não o redefine) — confirmas?

## Estado da aplicação (2026-08-10)

Parecer 2ª ronda do V1 specialist: GO em todos os edits, com 2 condições
estruturais, ambas acatadas:
- Q2: `_ACTIVE` nasce na SECÇÃO 10 (`usp_create_active_view`, ~linha 10180) —
  ~6500 linhas DEPOIS das views. `CREATE VIEW` não tem deferred name resolution
  ⇒ TLOG/BACKUPS redefinidas numa **SECÇÃO 10.5 nova** (pós-SECÇÃO 10), stubs
  originais mantidos com comentário ATENCAO. Padrão stub-cedo/redefinição-tarde
  que o script já usava para DEADLOCKS.
- Q1: `TLOG_USAGE_DET_VIEW` tem consumidor real (V6 `report_service.py:379-386`
  selecciona `[Used%]` e `Available_GB`; `_safe_query` engole erros ⇒ vazio
  silencioso). A redefinição inclui os dois **aliases de compatibilidade** além
  das colunas cruas.

Aplicado: canonical V1 (E1 in-place, ponteiros TLOG/BACKUPS, SECÇÃO 10.5,
bloco morto DEADLOCKS removido com ponteiro para a 18.2) · cópia V6 (idem +
DEADLOCKS substituído in-place — V6 não tinha a SECÇÃO 18) · registry V3.3
(`filegroup_usage.source` = embedded-sql, sem partir `is_mirror`) · nota
explicada à AI do V6 (`WATCHERDB_V6/docs/context/PROPAGACAO_RECONCILIACAO_
CANONICAL_2026-08-10.md`) · FIND-20260810-101.

## Execução do owner — BD viva — ✅ EXECUTADA 2026-08-11

**Fecho:** PASSO 0 confirmou o schema real (7 colunas, `Current_MB`/`Used_MB`);
CREATE VIEW aplicado; PASSO 2 devolveu dados vivos (top 5 CRITICAL, incl.
`ctrlm_tap_report` @ SQLHDSPRD405_I01 PRD a 99.12% — sinal operacional entregue
ao owner). Canonical == BD viva nas 4 famílias. O bloco abaixo fica como
registo histórico do procedimento.

**REVISTO 2026-08-11 após execução real do owner.** Descoberta que muda o passo 2:

- A `KPI_MSSQL_TLOG_USAGE_DET_VIEW` **não existe** na BD viva (ausente do passo 1;
  `Msg 208` no passo 3). O SPRINT5 fez `DROP` e o `CREATE` seguinte **falhou** com
  `Msg 207: Invalid column name 'Log_Size_MB'/'Log_Used_MB'` — o §17 foi escrito
  para um schema que nunca existiu (o real é `Current_MB`/`Used_MB`/`Max_Available_MB`,
  confirmado no DDL da STG e pelo Msg 207 ao vivo). A view está perdida desde o
  SPRINT5 e o report TLOG do V6 está mudo porque **o objecto nem existe**.
- O ALTER original desta secção falhou pelo MESMO motivo (colunas SPRINT5) — sem
  alterar nada. A SECÇÃO 10.5 dos dois canonicals foi corrigida a 2026-08-11 para
  o schema real.
- `BACKUPS_DET_VIEW` existe e "SEM aliases" é apenas informativo — sem consumidores,
  sem acção.

Identidades: passos 0 e 2 são SELECT (sql_monitoring); o passo 1 é DDL — exige
conta com CREATE VIEW. Impacto: cria um objecto novo (nada a sobrescrever — não
existe). Rollback: `DROP VIEW dbo.KPI_MSSQL_TLOG_USAGE_DET_VIEW` (volta ao estado
actual, inexistente).

```sql
-- PASSO 0 (sql_monitoring) - confirmar o schema real do _ACTIVE:
SELECT c.column_id, c.name AS coluna, ty.name AS tipo
FROM sys.objects o
JOIN sys.columns c ON c.object_id = o.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE o.name = 'KPI_MSSQL_TLOG_USAGE_ACTIVE'
ORDER BY c.column_id;
-- Esperado: Instance, Database, Current_MB, Used_MB, Max_Available_MB,
-- Percent_Used, Update_TS. Se diferente, PARAR e reportar.
```

```sql
-- PASSO 1 (conta DDL, janela propria, primeiro statement do batch)
-- So' se o PASSO 0 mostrou Current_MB/Used_MB:
CREATE VIEW dbo.KPI_MSSQL_TLOG_USAGE_DET_VIEW
AS
SELECT
    t.Instance,
    ISNULL(e.Env, 'Undefined') AS Env,
    t.[Database],
    t.Current_MB,
    t.Used_MB,
    t.Percent_Used,
    100 - t.Percent_Used AS [Available%],
    CAST((t.Current_MB - t.Used_MB) / 1024.0 AS DECIMAL(12,2)) AS Available_GB,
    t.Percent_Used AS [Used%],
    t.Update_TS,
    CASE
        WHEN t.Percent_Used > 95 THEN 'CRITICAL'
        WHEN t.Percent_Used > 85 THEN 'WARNING'
        ELSE 'OK'
    END AS Status
FROM dbo.KPI_MSSQL_TLOG_USAGE_ACTIVE t WITH (NOLOCK)
LEFT JOIN dbo.KPI_MSSQL_INST_ENVS e WITH (NOLOCK) ON e.Instance = t.Instance;
```

```sql
-- PASSO 2 (sql_monitoring) - verificar:
SELECT TOP 5 Instance, [Database], [Used%], Available_GB, Status
FROM dbo.KPI_MSSQL_TLOG_USAGE_DET_VIEW WITH (NOLOCK)
ORDER BY [Used%] DESC;
```

## Fora desta wave (registado)

- Configurabilidade dos 5 GO — gated 6.1 + segunda ronda com o facto novo do consumo V6.
- Memória (4 camadas) e Filegroups (registry errado + 2 modelos) — waves próprias.
- Registry V3.3: fix do `filegroup_usage.source` entra NESTA wave (metadado, sem
  comportamento).
