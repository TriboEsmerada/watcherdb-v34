/* ============================================================================
   PATCH — Wave reparação de fresh install (FIND-20260805-109) · CORRIGIDO
   Gate v1-intel 2026-08-06: VETO ao draft original (7 famílias) -> GO-com-condições
   à versão restrita. As 5 famílias SELECT-INTO JÁ estão cobertas (loop @2201 +
   callers @2620 + Wave C). O gap real é SÓ 2 famílias (o EXEC foi adicionado
   30/07 mas as _BLUE/_GREEN fonte nunca foram criadas).
   ----------------------------------------------------------------------------
   ESTADO : DRAFT gatado. Requer TESTE DE FRESH INSTALL numa BD limpa antes de commit.
   NÃO cria view aqui (a obsoleta 2-way ficaria vazia pós-Wave-C); as views env-aware
   são criadas pelas procs em BLOCO B via usp_create_active_view/usp_create_stg_alias.
   ============================================================================ */

-- ####################  BLOCO A — tabelas base das 2 famílias em falta  ####################
-- Verbatim de CREATE_BACKUP_HEALTH_STG_TABLES.sql (tabelas+índices+ACTIVE, SEM a view 1.6/2.6).
-- INSERIR no canonical ANTES de :2638 (o EXEC usp_setup_environment_tables destas 2).

-- ===== 1. BACKUP_EXEC_FAILURES =====
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_BLUE')
CREATE TABLE dbo.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_BLUE (
    Id BIGINT IDENTITY(1,1) NOT NULL, Instance NVARCHAR(128) NOT NULL, [Database] NVARCHAR(128) NULL,
    Job_Name NVARCHAR(256) NOT NULL, Job_Id UNIQUEIDENTIFIER NOT NULL, Step_Id INT NOT NULL,
    Step_Name NVARCHAR(256) NULL, Run_Status TINYINT NOT NULL, Run_Datetime DATETIME2 NOT NULL,
    Run_Duration_Sec INT NULL, Message NVARCHAR(MAX) NULL,
    Failure_Source NVARCHAR(20) NOT NULL CONSTRAINT CHK_BKPFAIL_BLUE_SOURCE CHECK (Failure_Source IN ('sysjobhistory','is_damaged','no_checksum')),
    Backup_Type_Classified NVARCHAR(20) NULL, Env NVARCHAR(10) NULL,
    Update_TS DATETIME2 NOT NULL CONSTRAINT DF_BKPFAIL_BLUE_TS DEFAULT GETDATE(),
    CONSTRAINT PK_BACKUP_EXEC_FAIL_BLUE PRIMARY KEY CLUSTERED (Id));
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_BKPFAIL_BLUE_INST_DB_DT' AND object_id=OBJECT_ID('dbo.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_BLUE'))
CREATE NONCLUSTERED INDEX IX_BKPFAIL_BLUE_INST_DB_DT ON dbo.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_BLUE (Instance,[Database],Run_Datetime DESC) INCLUDE (Job_Name,Run_Status,Failure_Source);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_BKPFAIL_BLUE_DT' AND object_id=OBJECT_ID('dbo.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_BLUE'))
CREATE NONCLUSTERED INDEX IX_BKPFAIL_BLUE_DT ON dbo.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_BLUE (Run_Datetime DESC) INCLUDE (Instance,Failure_Source);
GO
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_GREEN')
CREATE TABLE dbo.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_GREEN (
    Id BIGINT IDENTITY(1,1) NOT NULL, Instance NVARCHAR(128) NOT NULL, [Database] NVARCHAR(128) NULL,
    Job_Name NVARCHAR(256) NOT NULL, Job_Id UNIQUEIDENTIFIER NOT NULL, Step_Id INT NOT NULL,
    Step_Name NVARCHAR(256) NULL, Run_Status TINYINT NOT NULL, Run_Datetime DATETIME2 NOT NULL,
    Run_Duration_Sec INT NULL, Message NVARCHAR(MAX) NULL,
    Failure_Source NVARCHAR(20) NOT NULL CONSTRAINT CHK_BKPFAIL_GREEN_SOURCE CHECK (Failure_Source IN ('sysjobhistory','is_damaged','no_checksum')),
    Backup_Type_Classified NVARCHAR(20) NULL, Env NVARCHAR(10) NULL,
    Update_TS DATETIME2 NOT NULL CONSTRAINT DF_BKPFAIL_GREEN_TS DEFAULT GETDATE(),
    CONSTRAINT PK_BACKUP_EXEC_FAIL_GREEN PRIMARY KEY CLUSTERED (Id));
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_BKPFAIL_GREEN_INST_DB_DT' AND object_id=OBJECT_ID('dbo.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_GREEN'))
CREATE NONCLUSTERED INDEX IX_BKPFAIL_GREEN_INST_DB_DT ON dbo.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_GREEN (Instance,[Database],Run_Datetime DESC) INCLUDE (Job_Name,Run_Status,Failure_Source);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_BKPFAIL_GREEN_DT' AND object_id=OBJECT_ID('dbo.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_GREEN'))
CREATE NONCLUSTERED INDEX IX_BKPFAIL_GREEN_DT ON dbo.KPI_MSSQL_BACKUP_EXEC_FAILURES_STG_GREEN (Run_Datetime DESC) INCLUDE (Instance,Failure_Source);
GO
IF NOT EXISTS (SELECT 1 FROM dbo.KPI_STG_ACTIVE_TABLE WHERE Table_Name='KPI_MSSQL_BACKUP_EXEC_FAILURES_STG')
INSERT INTO dbo.KPI_STG_ACTIVE_TABLE (Table_Name,Active_Slot) VALUES ('KPI_MSSQL_BACKUP_EXEC_FAILURES_STG','BLUE');
GO

-- ===== 2. BACKUP_JOBS_DISABLED =====
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_BACKUP_JOBS_DISABLED_STG_BLUE')
CREATE TABLE dbo.KPI_MSSQL_BACKUP_JOBS_DISABLED_STG_BLUE (
    Id INT IDENTITY(1,1) NOT NULL, Instance NVARCHAR(128) NOT NULL, Job_Id UNIQUEIDENTIFIER NOT NULL,
    Job_Name NVARCHAR(256) NOT NULL, Job_Category NVARCHAR(128) NULL, Date_Last_Modified DATETIME2 NULL,
    Approx_Disabled_Since DATETIME2 NULL, Last_Run_Date DATETIME2 NULL, Last_Run_Status NVARCHAR(20) NULL,
    Owner_Login NVARCHAR(256) NULL, Env NVARCHAR(10) NULL,
    Update_TS DATETIME2 NOT NULL CONSTRAINT DF_BKPJOBDIS_BLUE_TS DEFAULT GETDATE(),
    CONSTRAINT PK_BKPJOBDIS_BLUE PRIMARY KEY CLUSTERED (Id));
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_BKPJOBDIS_BLUE_INST_JOB' AND object_id=OBJECT_ID('dbo.KPI_MSSQL_BACKUP_JOBS_DISABLED_STG_BLUE'))
CREATE NONCLUSTERED INDEX IX_BKPJOBDIS_BLUE_INST_JOB ON dbo.KPI_MSSQL_BACKUP_JOBS_DISABLED_STG_BLUE (Instance,Job_Id) INCLUDE (Job_Name,Last_Run_Status);
GO
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'KPI_MSSQL_BACKUP_JOBS_DISABLED_STG_GREEN')
CREATE TABLE dbo.KPI_MSSQL_BACKUP_JOBS_DISABLED_STG_GREEN (
    Id INT IDENTITY(1,1) NOT NULL, Instance NVARCHAR(128) NOT NULL, Job_Id UNIQUEIDENTIFIER NOT NULL,
    Job_Name NVARCHAR(256) NOT NULL, Job_Category NVARCHAR(128) NULL, Date_Last_Modified DATETIME2 NULL,
    Approx_Disabled_Since DATETIME2 NULL, Last_Run_Date DATETIME2 NULL, Last_Run_Status NVARCHAR(20) NULL,
    Owner_Login NVARCHAR(256) NULL, Env NVARCHAR(10) NULL,
    Update_TS DATETIME2 NOT NULL CONSTRAINT DF_BKPJOBDIS_GREEN_TS DEFAULT GETDATE(),
    CONSTRAINT PK_BKPJOBDIS_GREEN PRIMARY KEY CLUSTERED (Id));
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_BKPJOBDIS_GREEN_INST_JOB' AND object_id=OBJECT_ID('dbo.KPI_MSSQL_BACKUP_JOBS_DISABLED_STG_GREEN'))
CREATE NONCLUSTERED INDEX IX_BKPJOBDIS_GREEN_INST_JOB ON dbo.KPI_MSSQL_BACKUP_JOBS_DISABLED_STG_GREEN (Instance,Job_Id) INCLUDE (Job_Name,Last_Run_Status);
GO
IF NOT EXISTS (SELECT 1 FROM dbo.KPI_STG_ACTIVE_TABLE WHERE Table_Name='KPI_MSSQL_BACKUP_JOBS_DISABLED_STG')
INSERT INTO dbo.KPI_STG_ACTIVE_TABLE (Table_Name,Active_Slot) VALUES ('KPI_MSSQL_BACKUP_JOBS_DISABLED_STG','BLUE');
GO

-- ####################  BLOCO B — registar as 2 famílias nas listas de views  ####################
-- Sem legado a bloquear o guard do alias, funcionam (ao contrário das 12-14 do gap separado).
-- Acrescentar a seguir a :10193 (usp_create_active_view) e :10213 (usp_create_stg_alias):
EXEC dbo.usp_create_active_view 'KPI_MSSQL_BACKUP_EXEC_FAILURES_STG';
EXEC dbo.usp_create_active_view 'KPI_MSSQL_BACKUP_JOBS_DISABLED_STG';
GO
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_BACKUP_EXEC_FAILURES_STG';
EXEC dbo.usp_create_stg_alias 'KPI_MSSQL_BACKUP_JOBS_DISABLED_STG';
GO

/* ----------------------------------------------------------------------------
   FORA DESTE PATCH (do gate):
   - As 5 famílias SELECT-INTO: JÁ cobertas (loop @2201 + callers @2620 + Wave C). Removidas.
   - Gap do alias que SKIPa por a legada ainda ser tabela (~12-14 famílias) = separado,
     liga ao finding PROCESSES/DISK_USAGE de 04/08 (Opção 1 Python-side). NÃO bundlar aqui.
   - VERIFICAR antes de dar fresh install por completo: GRANT ALTER só existe no nome legado
     (:6764-6773), não nas físicas _BLUE_PRD/QA/TST + _GREEN_*. Confirmar por que mecanismo o
     collector/sql_monitoring escreve nessas 2 famílias novas.
   TESTE OBRIGATÓRIO: fresh install numa BD limpa -> as 2 famílias recolhem sem erro.
   ---------------------------------------------------------------------------- */
