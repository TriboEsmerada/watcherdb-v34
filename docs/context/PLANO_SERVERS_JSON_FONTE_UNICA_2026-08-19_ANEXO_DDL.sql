-- =============================================================================
-- ANEXO A do PLANO_SERVERS_JSON_FONTE_UNICA_2026-08-19.md
-- DDL DRAFT (parecer sql-deep-reviewer 2026-08-19) -- PARA REVISAO, NAO EXECUTAR
-- Estado: proposta. Exige GO do owner ao E2 + handoff V1 (veto holder deu
-- GO-COM-CONDICOES ao modelo) + SECAO nova no canonical + standalone.
-- Piso da casa: SQL Server 2014+ -> antes de aplicar, substituir CREATE OR ALTER
-- por IF OBJECT_ID ... DROP + CREATE, e FOR JSON PATH (2016+) por alternativa,
-- OU confirmar a versao do host da Intelligence (SQLHDSTST505\I01).
-- Identidade de escrita: a mesma que hoje escreve em metadata.server_config
-- (credenciais master_server do servers.json canonico do collector V1).
-- =============================================================================

-- ===== 1. Inventario de servidores (1 row por instancia; SEM password) =====
IF OBJECT_ID('metadata.monitored_server','U') IS NULL
CREATE TABLE metadata.monitored_server (
    server_id               INT IDENTITY(1,1) NOT NULL,
    tenant_id               VARCHAR(50)   NOT NULL CONSTRAINT DF_ms_tenant DEFAULT 'default',
    instance_id             VARCHAR(64)   NOT NULL,        -- = KPI_MSSQL_INST_ENVS.Instance (>64 = REJECT)
    host                    VARCHAR(255)  NOT NULL,
    instance_name           VARCHAR(50)   NULL,
    port                    INT           NULL,
    environment             VARCHAR(20)   NOT NULL,        -- production/quality/test/development
    priority                INT           NOT NULL CONSTRAINT DF_ms_priority DEFAULT 1,
    description             NVARCHAR(500) NULL,
    enabled                 BIT           NOT NULL CONSTRAINT DF_ms_enabled DEFAULT 1,   -- flag do JSON
    is_active               BIT           NOT NULL CONSTRAINT DF_ms_active  DEFAULT 1,   -- presente na fonte
    auth_mode               VARCHAR(10)   NOT NULL CONSTRAINT DF_ms_auth DEFAULT 'SQL',  -- SQL|WINDOWS
    login_name              VARCHAR(128)  NULL,            -- sem password: segredo fica local (Fernet/DPAPI)
    driver                  VARCHAR(100)  NULL,
    has_alwayson            BIT           NOT NULL CONSTRAINT DF_ms_ao DEFAULT 0,
    ag_name                 VARCHAR(128)  NULL,
    ag_listener             VARCHAR(255)  NULL,
    sql_servername_alias    VARCHAR(128)  NULL,
    source_hash             CHAR(64)      NOT NULL,        -- SHA-256 do objecto servidor (sem databases[] e sem volateis)
    first_seen_at           DATETIME2(0)  NOT NULL CONSTRAINT DF_ms_first DEFAULT SYSUTCDATETIME(),
    last_seen_in_source_at  DATETIME2(0)  NOT NULL CONSTRAINT DF_ms_last  DEFAULT SYSUTCDATETIME(),
    removed_at              DATETIME2(0)  NULL,
    last_sync_run_id        BIGINT        NULL,
    updated_at              DATETIME2(0)  NOT NULL CONSTRAINT DF_ms_upd DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_monitored_server PRIMARY KEY CLUSTERED (server_id),
    CONSTRAINT UQ_monitored_server_instance UNIQUE (tenant_id, instance_id),
    CONSTRAINT FK_monitored_server_tenant FOREIGN KEY (tenant_id) REFERENCES metadata.tenants(tenant_id),
    CONSTRAINT CK_ms_env  CHECK (environment IN ('production','quality','test','development')),
    CONSTRAINT CK_ms_port CHECK (port IS NULL OR port BETWEEN 1 AND 65535),
    CONSTRAINT CK_ms_auth CHECK (auth_mode IN ('SQL','WINDOWS')),
    CONSTRAINT CK_ms_removed CHECK ((is_active = 1 AND removed_at IS NULL) OR (is_active = 0))
);
-- Unico indice extra: "activos por ambiente" (driving do portal/collector)
CREATE NONCLUSTERED INDEX IX_monitored_server_active
    ON metadata.monitored_server (is_active, environment)
    INCLUDE (instance_id, host, port, enabled);

-- ===== 2. Databases por servidor (catalogo de inventario; NAO scope de coleta -- veto V1) =====
IF OBJECT_ID('metadata.monitored_server_database','U') IS NULL
CREATE TABLE metadata.monitored_server_database (
    server_id               INT           NOT NULL,
    database_name           NVARCHAR(128) NOT NULL,        -- collation default da BD (CI), igual a KPI_*
    database_id             INT           NULL,            -- atributo (muda em drop/restore), nao chave
    state                   VARCHAR(30)   NULL,
    recovery_model          VARCHAR(12)   NULL,
    is_read_only            BIT           NULL,
    is_accessible           BIT           NULL,
    compatibility_level     SMALLINT      NULL,
    is_active               BIT           NOT NULL CONSTRAINT DF_msd_active DEFAULT 1,
    first_seen_at           DATETIME2(0)  NOT NULL CONSTRAINT DF_msd_first DEFAULT SYSUTCDATETIME(),
    last_seen_in_source_at  DATETIME2(0)  NOT NULL CONSTRAINT DF_msd_last  DEFAULT SYSUTCDATETIME(),
    removed_at              DATETIME2(0)  NULL,
    updated_at              DATETIME2(0)  NOT NULL CONSTRAINT DF_msd_upd DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_monitored_server_database PRIMARY KEY CLUSTERED (server_id, database_name),
    CONSTRAINT FK_msd_server FOREIGN KEY (server_id) REFERENCES metadata.monitored_server(server_id)
);
CREATE NONCLUSTERED INDEX IX_msd_database_name ON metadata.monitored_server_database (database_name) INCLUDE (is_active, state);
CREATE NONCLUSTERED INDEX IX_msd_removed ON metadata.monitored_server_database (removed_at) WHERE removed_at IS NOT NULL;

-- ===== 3. Runs + audit =====
IF OBJECT_ID('metadata.server_sync_run','U') IS NULL
CREATE TABLE metadata.server_sync_run (
    run_id              BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_server_sync_run PRIMARY KEY CLUSTERED,
    started_at          DATETIME2(0)  NOT NULL CONSTRAINT DF_ssr_start DEFAULT SYSUTCDATETIME(),
    finished_at         DATETIME2(0)  NULL,
    last_checked_at     DATETIME2(0)  NULL,               -- avancado pelos SKIP (sem row nova)
    source_path         NVARCHAR(400) NOT NULL,
    source_hash         CHAR(64)      NOT NULL,
    source_mtime        DATETIME2(0)  NULL,
    servers_in_source   INT NULL, servers_inserted INT NULL, servers_updated INT NULL,
    servers_deactivated INT NULL, servers_reactivated INT NULL, servers_rejected INT NULL,
    dbs_in_source       INT NULL, dbs_inserted INT NULL, dbs_updated INT NULL, dbs_deactivated INT NULL,
    status              VARCHAR(20)   NOT NULL CONSTRAINT DF_ssr_status DEFAULT 'RUNNING',
    error_message       NVARCHAR(2000) NULL,
    host_name           VARCHAR(128)  NULL,
    pid                 INT           NULL,
    dry_run             BIT           NOT NULL CONSTRAINT DF_ssr_dry DEFAULT 1,
    CONSTRAINT CK_ssr_status CHECK (status IN ('RUNNING','OK','PARTIAL','FAILED','SKIPPED_UNCHANGED'))
);
CREATE NONCLUSTERED INDEX IX_ssr_status_started ON metadata.server_sync_run (status, started_at DESC) INCLUDE (source_hash);

IF OBJECT_ID('metadata.server_sync_audit','U') IS NULL
CREATE TABLE metadata.server_sync_audit (
    audit_id     BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_server_sync_audit PRIMARY KEY CLUSTERED,
    run_id       BIGINT        NOT NULL CONSTRAINT FK_ssa_run REFERENCES metadata.server_sync_run(run_id),
    entity_type  VARCHAR(10)   NOT NULL,   -- SERVER | DATABASE
    entity_key   NVARCHAR(200) NOT NULL,   -- instance_id | instance_id + '|' + database_name
    action       VARCHAR(12)   NOT NULL,   -- INSERT|UPDATE|DEACTIVATE|REACTIVATE|REJECT
    changed_cols VARCHAR(500)  NULL,       -- lista de colunas (UPDATE)
    before_json  NVARCHAR(MAX) NULL,       -- so SERVER + UPDATE
    after_json   NVARCHAR(MAX) NULL,
    reason       NVARCHAR(400) NULL,       -- REJECT: ID_TOO_LONG, DUP_ID, BAD_ENV, CASE_COLLISION, MASS_DEACTIVATE_GUARD...
    logged_at    DATETIME2(0)  NOT NULL CONSTRAINT DF_ssa_at DEFAULT SYSUTCDATETIME(),
    CONSTRAINT CK_ssa_action CHECK (action IN ('INSERT','UPDATE','DEACTIVATE','REACTIVATE','REJECT'))
);
CREATE NONCLUSTERED INDEX IX_ssa_run ON metadata.server_sync_audit (run_id, entity_type);
CREATE NONCLUSTERED INDEX IX_ssa_entity ON metadata.server_sync_audit (entity_type, entity_key, logged_at DESC);

-- ===== 4. Staging (pyodbc fast_executemany; keyed por run_id, sem TRUNCATE) =====
IF OBJECT_ID('metadata.monitored_server_stg','U') IS NULL
CREATE TABLE metadata.monitored_server_stg (
    run_id BIGINT NOT NULL, instance_id VARCHAR(200) NOT NULL,   -- 200 de proposito: validacao de tamanho na sproc
    host VARCHAR(255) NULL, instance_name VARCHAR(50) NULL, port INT NULL, environment VARCHAR(50) NULL,
    priority INT NULL, description NVARCHAR(500) NULL, enabled BIT NULL, auth_mode VARCHAR(10) NULL,
    login_name VARCHAR(128) NULL, driver VARCHAR(100) NULL, has_alwayson BIT NULL, ag_name VARCHAR(128) NULL,
    ag_listener VARCHAR(255) NULL, sql_servername_alias VARCHAR(128) NULL, source_hash CHAR(64) NOT NULL,
    CONSTRAINT PK_ms_stg PRIMARY KEY CLUSTERED (run_id, instance_id)   -- DUP_ID: Python valida antes
);
IF OBJECT_ID('metadata.monitored_server_database_stg','U') IS NULL
CREATE TABLE metadata.monitored_server_database_stg (
    run_id BIGINT NOT NULL, instance_id VARCHAR(200) NOT NULL, database_name NVARCHAR(128) NOT NULL,
    database_id INT NULL, state VARCHAR(30) NULL, recovery_model VARCHAR(12) NULL, is_read_only BIT NULL,
    is_accessible BIT NULL, compatibility_level SMALLINT NULL,
    CONSTRAINT PK_msd_stg PRIMARY KEY CLUSTERED (run_id, instance_id, database_name)
);

-- ===== 5. Sproc de sync (ESQUELETO -- passos 5a-5k por escrever na implementacao) =====
-- (2014+: trocar CREATE OR ALTER por IF OBJECT_ID(...) DROP PROCEDURE + CREATE)
CREATE OR ALTER PROCEDURE metadata.usp_sync_monitored_servers
    @RunId                  BIGINT,          -- criado pelo Python (INSERT server_sync_run status=RUNNING)
    @DryRun                 BIT = 1,
    @AllowMassDeactivatePct INT = 20,
    @MinServersInSource     INT = 1,
    @ProjectToServerConfig  BIT = 1,         -- transicao: escreve row base (config_key IS NULL) em server_config
    @RetentionRunDays       INT = 180,
    @RetentionAuditDays     INT = 90
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON; SET DEADLOCK_PRIORITY LOW;
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME(), @lock INT, @status VARCHAR(20) = 'OK', @reason NVARCHAR(400);

    -- 0) Guardas de fonte (antes de qualquer lock)
    DECLARE @in_src INT = (SELECT COUNT(*) FROM metadata.monitored_server_stg WHERE run_id = @RunId);
    IF @in_src < @MinServersInSource
    BEGIN UPDATE metadata.server_sync_run SET status='FAILED', finished_at=@now,
              error_message='staging vazia (JSON vazio/corrompido) - nada mutado' WHERE run_id=@RunId; RETURN 1; END

    -- 1) Candidatos SERVER (uma unica leitura staging x alvo)
    ;WITH s AS (SELECT * FROM metadata.monitored_server_stg WHERE run_id=@RunId)
    SELECT s.instance_id AS src_id, t.server_id, t.instance_id AS tgt_id,
           CASE WHEN LEN(s.instance_id) > 64 THEN 'REJECT:ID_TOO_LONG'
                WHEN s.environment NOT IN ('production','quality','test','development') THEN 'REJECT:BAD_ENV'
                WHEN t.server_id IS NULL THEN 'INSERT'
                WHEN t.is_active = 0 THEN 'REACTIVATE'
                WHEN t.source_hash <> s.source_hash THEN 'UPDATE'
                ELSE 'NOOP' END AS action
    INTO #srv
    FROM s FULL OUTER JOIN metadata.monitored_server t
           ON t.tenant_id='default' AND t.instance_id = s.instance_id
    WHERE s.instance_id IS NOT NULL;
    -- ausentes da fonte (so activos) -- REGRA: "ausente da run processada", NUNCA por idade
    INSERT #srv (src_id, server_id, tgt_id, action)
    SELECT NULL, t.server_id, t.instance_id, 'DEACTIVATE'
    FROM metadata.monitored_server t
    WHERE t.is_active = 1 AND NOT EXISTS (SELECT 1 FROM metadata.monitored_server_stg s WHERE s.run_id=@RunId AND s.instance_id = t.instance_id);

    -- 2) Guarda de frota
    DECLARE @active INT = (SELECT COUNT(*) FROM metadata.monitored_server WHERE is_active=1),
            @deact  INT = (SELECT COUNT(*) FROM #srv WHERE action='DEACTIVATE');
    IF @active > 0 AND @deact * 100 > @active * @AllowMassDeactivatePct
    BEGIN SET @status='PARTIAL'; SET @reason = CONCAT('MASS_DEACTIVATE_GUARD: ', @deact, '/', @active);
          UPDATE #srv SET action='REJECT:MASS_DEACTIVATE_GUARD' WHERE action='DEACTIVATE'; END

    -- 3) Candidatos DATABASE (mesmo padrao -> #db; REJECT:CASE_COLLISION quando
    --    COUNT(*) OVER (PARTITION BY instance_id, database_name COLLATE DATABASE_DEFAULT) > 1;
    --    DEACTIVATE so para servidores PRESENTES na run)

    -- 4) DryRun: resumo + candidatos, sem lock, sem transacao
    IF @DryRun = 1 BEGIN SELECT action, COUNT(*) n FROM #srv GROUP BY action; SELECT * FROM #srv WHERE action<>'NOOP'; RETURN 0; END

    -- 5) Execucao: transacao curta so-DML + applock (convencao da reconcile)
    BEGIN TRAN;
    EXEC @lock = sp_getapplock @Resource='WDB_SYNC_MONITORED_SERVERS', @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=5000;
    IF @lock < 0 BEGIN ROLLBACK; RAISERROR('usp_sync_monitored_servers: applock nao obtido (%d)',16,1,@lock); RETURN 2; END
    -- 5a) audit BEFORE (UPDATE/DEACTIVATE/REACTIVATE de SERVER)
    -- 5b) UPDATE changed  (SET ..., source_hash, last_seen_in_source_at=@now, last_sync_run_id=@RunId, updated_at=@now)
    -- 5c) REACTIVATE      (is_active=1, removed_at=NULL, + colunas)
    -- 5d) INSERT new
    -- 5e) DEACTIVATE      (is_active=0, removed_at=@now)   -- removed_at e' a fonte da reconcile (grace 30d)
    -- 5f) NOOP: UPDATE last_seen_in_source_at=@now, last_sync_run_id=@RunId
    -- 5g) DATABASES: idem por #db (server_id+database_name)
    -- 5h) Projeccao KPI_MSSQL_INST_ENVS (UPDATE/INSERT; SEM DELETE -- e' da usp_reconcile_inst_envs)
    --     CASE environment WHEN 'production' THEN 'PRD' WHEN 'quality' THEN 'QLT' WHEN 'test' THEN 'TST' WHEN 'development' THEN 'DEV' END
    -- 5i) IF @ProjectToServerConfig=1: UPDATE/INSERT row base (config_key IS NULL) em metadata.server_config
    --     (host LEFT(...,100) explicito + REJECT se perder informacao) + is_active=0 para DEACTIVATE
    -- 5j) audit AFTER + REJECT rows + contadores na server_sync_run; status=@status
    -- 5k) limpeza: DELETE stg WHERE run_id < @RunId ; purge runs/audit > retencao em lotes TOP (5000) -- SO na run das 03h
    COMMIT;
    RETURN 0;
END
GO

-- GRANTs (mesma identidade que escreve server_config hoje):
-- GRANT SELECT, INSERT, UPDATE, DELETE ON metadata.monitored_server            TO [<login_collector>];
-- GRANT SELECT, INSERT, UPDATE, DELETE ON metadata.monitored_server_database   TO [<login_collector>];
-- GRANT SELECT, INSERT, UPDATE, DELETE ON metadata.server_sync_run             TO [<login_collector>];
-- GRANT SELECT, INSERT, UPDATE, DELETE ON metadata.server_sync_audit           TO [<login_collector>];
-- GRANT SELECT, INSERT, UPDATE, DELETE ON metadata.monitored_server_stg        TO [<login_collector>];
-- GRANT SELECT, INSERT, UPDATE, DELETE ON metadata.monitored_server_database_stg TO [<login_collector>];
-- GRANT EXECUTE ON metadata.usp_sync_monitored_servers TO [<login_collector>];
-- Portal V3.3/V6 (sql_monitoring): GRANT SELECT nas 4 tabelas de inventario/run/audit.

-- Alteracoes colaterais (nao incluidas aqui): usp_reconcile_inst_envs passa a ler
-- monitored_server(is_active, removed_at) em vez de dedupar server_config;
-- bloco canonical :6250-6280 ("[13/13] Inserindo 5 Servidores") -> "primeira run da sync";
-- seed WDB_COLLECTION_SCHEDULE_META ('metadata.monitored_server','sync_monitored_servers',10,'HEARTBEAT').
