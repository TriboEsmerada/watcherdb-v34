# DESIGN — Reconcile diário de tabelas de instâncias (usp_reconcile_inst_envs)

Data: 2026-07-23 | Gate: watcherdb-v1-intel-specialist GO-COM-CONDIÇÕES (sem veto) + sql-deep-reviewer (sproc draft)
Decisão owner: 1×/dia o serviço collector verifica servers.json e faz merge nas tabelas de instâncias.

## Problema (verificado)

- `KPI_MSSQL_INST_ENVS` é append-only (~101 rows órfãs desde migração 25/03); 33 servers disabled no config.
- Dois configs V1 divergentes: `config/servers.json` vs `services/collector_service/config/servers.json`.
  Caso real: SQLHDSTST014_I03 `enabled:false` no primeiro, SEM chave no segundo → `server_manager.py:156`
  default True → "1 OFF" permanente. FIX imediato: acrescentar `"enabled": false,` à entrada no config
  do serviço (linha ~1313) + Restart-Service.
- Script canónico `scripts/sync_servers_from_json.py` já existe (JSON → [metadata].[server_config] →
  INST_ENVS) mas é upsert-only, e tem 2 red flags: Trusted_Connection no caminho master (linha 51) e
  driver swap legacy "SQL Server" (linhas 80-81).

## Descobertas dos specialists (mudam o desenho)

1. **OVERVIEW_INSTANCE_SNAPSHOT já tem reconcile automático** — `usp_refresh_overview_all`
   (INSTALACAO:10388) apaga órfãos vs INST_ENVS, corre em job de 5 min (CRIAR_JOBS_OVERVIEW_DASHBOARD.sql).
   → A sproc nova só toca em INST_ENVS; o cascade do snapshot é de graça. (Condição v1-intel a.)
2. **`WDB_KPI_FRESHNESS` não existe**; `OVERVIEW.Last_Collection` vem de path legado morto
   (STG base sem sufixo BLUE/GREEN — parecer v1-intel 2026-07-21). Fonte de "última coleta" para a
   guarda de idade = MAX de fontes vivas/duráveis (ver sproc): `KPI_MSSQL_INST_AVAILABILITY_ACTIVE`
   (view UNION dos 6 BLUE/GREEN — prova presença actual) + `KPI_MSSQL_INST_AVAILABILITY_HIST` +
   `KPI_OS_CPU_HIST` (append-only — provam ausência prolongada). (Condição v1-intel b + análise sql-deep.)
3. **CRÍTICO (finding novo, HIGH)**: o master_server do config DO SERVIÇO tem `use_windows_auth: true`
   sem credenciais → o serviço live liga HOJE à WatcherDB_Intelligence com Trusted_Connection implícito
   (viola Regra de Ouro #2, pior que o red flag do script standalone). A unificação de configs TEM de
   fixar `use_windows_auth: false` + credencial SQL Fernet no ficheiro sobrevivente — mesma wave.
   (Condição v1-intel c.)
4. **Consumidores**: 100% dos JOINs V3.3 a INST_ENVS são LEFT JOIN (16 sites) — DELETE não parte nada;
   `V_DASHBOARD_BY_ENV` INNER JOIN é comportamento desejado (instância removida sai da contagem);
   `live_monitoring.py:925,1235` usa INST_ENVS como driving table → fantasmas desaparecem da UI
   (é exactamente o sintoma que motivou o pedido).
5. **Sem mecanismo de alias** (typo SS301): rename = delete+insert; reseta learning WDB_KPI_BASELINE.
   Backlog, não bloqueia. Se recorrente: campo `aliases: []` no servers.json resolvido no ServerManager.
6. **V_DASHBOARD_SUMMARY** (global, sem JOIN INST_ENVS) continua a contar STG órfão — issue conhecida
   separada, fora de scope.

## Arbitragens (conflitos entre os dois pareceres)

- Snapshot na sproc: sql-deep incluía DELETE do snapshot na mesma txn ("redundância benigna");
  v1-intel (veto holder) pediu scope reduzido. DECISÃO: sproc só INST_ENVS — job de 5 min limpa o resto.
- Fonte de evidência: sql-deep usava OVERVIEW.Last_Collection como fonte "viva"; v1-intel demonstrou
  que é path legado. DECISÃO: substituir por MAX(Update_TS) da view `KPI_MSSQL_INST_AVAILABILITY_ACTIVE`.
  As duas HIST mantêm-se (provam silêncio >30d; STG/_ACTIVE não provam ausência — truncam no swap).
- Identidade do GRANT EXECUTE: mesma identidade master que hoje executa usp_swap_kpi_stg_tables +
  heartbeat (precedente; canonical :15337-15339). Nota: regra "sql_monitoring SELECT-only" aplica-se aos
  servidores MONITORIZADOS; na Intelligence esse login já é o escritor V1. Alternativa (login dedicado
  ao serviço) fica como decisão owner.

## Sproc final (draft consolidado — aplicar via SSMS pelo owner, SECAO nova no canonical)

Características: UPDATE+INSERT+DELETE separados (sem MERGE — bugs conhecidos + guarda condicional no
DELETE), transação curta só-DML, sp_getapplock 'WDB_RECONCILE_INST_ENVS' (padrão da casa),
SET DEADLOCK_PRIORITY LOW (em conflito morre a reconcile, nunca o portal), @DryRun BIT = 1 POR DEFEITO
(EXEC acidental não muta; serviço passa @DryRun=0 explícito), @GraceDays=30, @PurgeNeverCollected=0
(único caminho destrutivo real — só manual pós-auditoria, nunca no YAML), idempotente (2ª corrida = 0/0/0),
result sets com contagens + detalhe por candidato (audit trail no log do serviço).

```sql
IF OBJECT_ID('dbo.usp_reconcile_inst_envs', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_reconcile_inst_envs;
GO

CREATE PROCEDURE dbo.usp_reconcile_inst_envs
    @GraceDays           INT = 30,
    @DryRun              BIT = 1,
    @PurgeNeverCollected BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET DEADLOCK_PRIORITY LOW;

    DECLARE @Now    DATETIME2 = GETDATE();
    DECLARE @Cutoff DATETIME2 = DATEADD(DAY, -ABS(@GraceDays), @Now);
    DECLARE @rc_upd INT = 0, @rc_ins INT = 0, @rc_del INT = 0;
    DECLARE @lock_result INT;

    -- 1) Fonte canonica deduplicada (server_config pode ter N rows por instancia:
    --    UQ = tenant+instance+config_key). LEN>64 excluido e reportado (PK INST_ENVS
    --    e' VARCHAR(64) -- nunca truncar PK silenciosamente).
    DECLARE @src TABLE (
        Instance VARCHAR(64)  NOT NULL PRIMARY KEY,
        Env      VARCHAR(32)  NOT NULL,
        Descr    VARCHAR(500) NULL
    );

    INSERT INTO @src (Instance, Env, Descr)
    SELECT x.instance_id, x.Env, x.Descr
    FROM (
        SELECT
            CAST(sc.instance_id AS VARCHAR(64)) AS instance_id,
            CASE sc.environment
                WHEN 'production'  THEN 'PROD'
                WHEN 'development' THEN 'DEV'
                WHEN 'test'        THEN 'TEST'
                WHEN 'quality'     THEN 'QLT'
                WHEN 'uat'         THEN 'UAT'
                WHEN 'staging'     THEN 'STG'
                ELSE 'PROD'
            END AS Env,
            CAST(sc.description AS VARCHAR(500)) AS Descr,
            ROW_NUMBER() OVER (
                PARTITION BY sc.instance_id
                ORDER BY CASE WHEN sc.config_key IS NULL THEN 0 ELSE 1 END,
                         sc.updated_at DESC, sc.config_id DESC
            ) AS rn
        FROM [metadata].[server_config] sc
        WHERE sc.tenant_id = 'default'
          AND sc.is_active = 1
          AND LEN(sc.instance_id) <= 64
    ) x
    WHERE x.rn = 1;

    DECLARE @skipped_invalid INT = (
        SELECT COUNT(DISTINCT sc.instance_id)
        FROM [metadata].[server_config] sc
        WHERE sc.tenant_id = 'default' AND sc.is_active = 1
          AND LEN(sc.instance_id) > 64);

    -- 2) Candidatos a remocao = rows INST_ENVS fora do conjunto activo
    DECLARE @cand TABLE (
        Instance          VARCHAR(64) NOT NULL PRIMARY KEY,
        In_Config         BIT         NOT NULL,
        Config_Last_Touch DATETIME2   NULL,  -- informativo: sync diario toca updated_at em todas
        Last_Evidence     DATETIME2   NULL,
        Action            VARCHAR(20) NULL
    );

    INSERT INTO @cand (Instance, In_Config, Config_Last_Touch)
    SELECT e.Instance,
           CASE WHEN cfg.instance_id IS NOT NULL THEN 1 ELSE 0 END,
           cfg.updated_at
    FROM dbo.KPI_MSSQL_INST_ENVS e
    LEFT JOIN @src s ON s.Instance = e.Instance
    OUTER APPLY (
        SELECT TOP (1) sc.instance_id, sc.updated_at
        FROM [metadata].[server_config] sc
        WHERE sc.tenant_id = 'default' AND sc.instance_id = e.Instance
        ORDER BY sc.updated_at DESC
    ) cfg
    WHERE s.Instance IS NULL;

    -- 2b) Evidencia de ultima coleta = MAX de 3 fontes (so p/ candidatos, seeks):
    --     a) KPI_MSSQL_INST_AVAILABILITY_ACTIVE (view UNION BLUE/GREEN reais --
    --        prova coleta ACTUAL; substitui OVERVIEW.Last_Collection que vem de
    --        path legado morto, parecer v1-intel 2026-07-21/23)
    --     b) KPI_MSSQL_INST_AVAILABILITY_HIST (append-only -- prova silencio longo)
    --     c) KPI_OS_CPU_HIST (append-only, 2a familia independente)
    UPDATE c
    SET Last_Evidence = ev.ts
    FROM @cand c
    CROSS APPLY (
        SELECT MAX(v.ts) AS ts
        FROM (VALUES
            ((SELECT MAX(a.Update_TS)
              FROM dbo.KPI_MSSQL_INST_AVAILABILITY_ACTIVE a WITH (NOLOCK)
              WHERE a.Instance = c.Instance)),
            ((SELECT MAX(h.Collection_Time)
              FROM dbo.KPI_MSSQL_INST_AVAILABILITY_HIST h WITH (NOLOCK)
              WHERE h.Instance_Name = c.Instance)),
            ((SELECT MAX(ch.Update_TS)
              FROM dbo.KPI_OS_CPU_HIST ch WITH (NOLOCK)
              WHERE ch.Instance = c.Instance))
        ) v(ts)
    ) ev;
    -- NOTA: validar no 1o DryRun a coluna Instance da view _ACTIVE (Instance vs
    -- Instance_Name) e a vivacidade das 3 fontes (sweep 2026-07-23 achou familias
    -- HIST paradas desde 13/05).

    UPDATE @cand
    SET Action = CASE
        WHEN Last_Evidence >= @Cutoff  THEN 'SKIP_GRACE'
        WHEN Last_Evidence IS NOT NULL THEN 'DELETE'
        WHEN @PurgeNeverCollected = 1  THEN 'DELETE'
        ELSE 'SKIP_NO_EVIDENCE'   -- fail-safe: nunca coletou -> nao apagar
    END;

    -- 3) DryRun: reporta e sai
    IF @DryRun = 1
    BEGIN
        SELECT 'DRYRUN' AS Mode, @Now AS Run_TS, @Cutoff AS Grace_Cutoff,
            (SELECT COUNT(*) FROM @src s
             INNER JOIN dbo.KPI_MSSQL_INST_ENVS e ON e.Instance = s.Instance
             WHERE e.Env <> s.Env
                OR (s.Descr IS NOT NULL
                    AND (e.Description IS NULL OR e.Description <> s.Descr)))
                                                                    AS Would_Update,
            (SELECT COUNT(*) FROM @src s
             WHERE NOT EXISTS (SELECT 1 FROM dbo.KPI_MSSQL_INST_ENVS e
                               WHERE e.Instance = s.Instance))      AS Would_Insert,
            (SELECT COUNT(*) FROM @cand WHERE Action = 'DELETE')           AS Would_Delete,
            (SELECT COUNT(*) FROM @cand WHERE Action = 'SKIP_GRACE')       AS Skipped_By_Grace,
            (SELECT COUNT(*) FROM @cand WHERE Action = 'SKIP_NO_EVIDENCE') AS Skipped_No_Evidence,
            @skipped_invalid AS Skipped_Invalid_Len;

        SELECT Instance, In_Config, Last_Evidence, Config_Last_Touch, Action
        FROM @cand ORDER BY Action, Instance;
        RETURN 0;
    END

    -- 4) Execucao real: transacao curta so-DML + applock
    BEGIN TRY
        BEGIN TRANSACTION;

        EXEC @lock_result = sp_getapplock
             @Resource    = 'WDB_RECONCILE_INST_ENVS',
             @LockMode    = 'Exclusive',
             @LockOwner   = 'Transaction',
             @LockTimeout = 5000;
        IF @lock_result < 0
        BEGIN
            ROLLBACK TRANSACTION;
            RAISERROR('usp_reconcile_inst_envs: applock nao obtido (codigo %d)', 16, 1, @lock_result);
            RETURN 1;
        END

        UPDATE e
        SET e.Env = s.Env,
            e.Description = ISNULL(s.Descr, e.Description)
        FROM dbo.KPI_MSSQL_INST_ENVS e
        INNER JOIN @src s ON s.Instance = e.Instance
        WHERE e.Env <> s.Env
           OR (s.Descr IS NOT NULL
               AND (e.Description IS NULL OR e.Description <> s.Descr));
        SET @rc_upd = @@ROWCOUNT;

        INSERT INTO dbo.KPI_MSSQL_INST_ENVS (Instance, Env, Description)
        SELECT s.Instance, s.Env, ISNULL(s.Descr, 'Servidor nao descrito')
        FROM @src s
        WHERE NOT EXISTS (SELECT 1 FROM dbo.KPI_MSSQL_INST_ENVS e
                          WHERE e.Instance = s.Instance);
        SET @rc_ins = @@ROWCOUNT;

        DELETE e
        FROM dbo.KPI_MSSQL_INST_ENVS e
        INNER JOIN @cand c ON c.Instance = e.Instance
        WHERE c.Action = 'DELETE';
        SET @rc_del = @@ROWCOUNT;

        -- OVERVIEW_INSTANCE_SNAPSHOT: NAO tocar aqui -- usp_refresh_overview_all
        -- (INSTALACAO:10388, job 5 min) limpa orfaos vs INST_ENVS sozinho.
        -- (Condicao v1-intel: scope minimo.)

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        DECLARE @ErrorMessage NVARCHAR(4000) = ERROR_MESSAGE();
        RAISERROR(@ErrorMessage, 16, 1);
        RETURN 1;
    END CATCH

    -- 5) Result sets para o log do servico
    SELECT 'EXECUTE' AS Mode, @Now AS Run_TS, @Cutoff AS Grace_Cutoff,
           @rc_upd AS Updated, @rc_ins AS Inserted, @rc_del AS Deleted,
           (SELECT COUNT(*) FROM @cand WHERE Action = 'SKIP_GRACE')       AS Skipped_By_Grace,
           (SELECT COUNT(*) FROM @cand WHERE Action = 'SKIP_NO_EVIDENCE') AS Skipped_No_Evidence,
           @skipped_invalid AS Skipped_Invalid_Len;

    SELECT Instance, In_Config, Last_Evidence, Config_Last_Touch, Action
    FROM @cand ORDER BY Action, Instance;

    RETURN 0;
END
GO

-- Identidade: MESMO login master do collector que executa usp_swap_kpi_stg_tables
-- (canonical :15337-15339). Ownership chaining dispensa grants DML directos.
GRANT EXECUTE ON dbo.usp_reconcile_inst_envs TO [sql_monitoring];
GO
```

## Integração Python/YAML (diffs a produzir na implementação, handshake por edit)

1. `services/collector_service/collectors/reconcile_inst_envs.py` (novo adapter): date-gate diário
   (precedente `collect_deadlocks.py:68-73`: `_last_run_date != today` + `hour >= run_after_hour`);
   passo 1 reutiliza `sync_servers_to_database()` importado do script canónico (grep-first — não duplicar);
   passo 2 EXEC sproc com @DryRun do YAML; loga os 2 result sets integralmente (audit trail).
2. `services/collector_service/config.yaml`: entry nova `reconcile_inst_envs` — `interval_minutes: 60`,
   `enabled: true`, `run_after_hour: 3` (depois do job Cleanup History das 02:00), `dry_run: true`
   no arranque (flip para false = 1 linha pós-auditoria). Scheduler é IntervalTrigger — gate vive no adapter.
3. `scripts/sync_servers_from_json.py`: corrigir red flags (Trusted_Connection linha 51; driver legacy
   80-81) + passo 5 opcional EXEC da sproc (para uso manual; atenção autocommit=False → commit no fim).
4. Canonical `INSTALACAO_COMPLETA_UNIFICADA.sql`: SECAO nova (pós-16) com sproc + GRANT; standalone em
   `database/` (padrão FRESHNESS_GUARD). Fecho = 5 surfaces (skill wave-close).

## Rollout

0. Backup: `SELECT * INTO dbo.KPI_MSSQL_INST_ENVS_BAK_20260723 FROM dbo.KPI_MSSQL_INST_ENVS;`
1. Owner aplica DDL da sproc (SSMS) → `EXEC dbo.usp_reconcile_inst_envs @DryRun=1` manual → rever detalhe.
2. Serviço com `dry_run: true` ~1 semana (logs mostram o que faria).
3. Flip `dry_run: false`.
Rollback de deleção errada: re-INSERT do _BAK (snapshot reconstrói-se no próximo refresh de 5 min).

## Decisões em aberto (owner)

- D1: qual servers.json sobrevive (recomendação: conteúdo do `config/servers.json` raiz — já tem SQL auth
  Fernet; o config.yaml do serviço passa a apontar-lhe, eliminando a 2ª cópia). CONSTRAINT não-negociável
  do gate: o master do ficheiro sobrevivente fica `use_windows_auth: false` — mesma wave.
- D2: identidade do GRANT EXECUTE (recomendação: mesma do swap; alternativa login dedicado).
- D3: sidebar V3.3 (`/api/v3/servers` ler da INST_ENVS reconciliada) — design review separado.

## Riscos residuais (sql-deep)

Fontes HIST podem estar paradas (sweep 13/05) → validar vivacidade no 1º DryRun; janela candidato→DML
(segundos) aceite por desenho; corrida com script manual benigna (evitar runs manuais às 03:00);
@GraceDays deve ficar ≪ retenção HIST 90d; NVARCHAR→VARCHAR degrada p/ '?' (paridade com sync actual);
GETDATE vs UTC erro máx ~1h irrelevante p/ 30d.
