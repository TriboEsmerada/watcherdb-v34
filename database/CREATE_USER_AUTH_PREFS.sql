-- ============================================================================
-- WatcherDB V3.1 — Tabelas de Autenticacao, Auditoria e Preferencias
-- Executar na base: WatcherDB_Intelligence
-- ============================================================================

USE WatcherDB_Intelligence;
GO

-- 1. Tabela de Users
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'WatcherDB_Users')
BEGIN
    CREATE TABLE dbo.WatcherDB_Users (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        username        NVARCHAR(100)  NOT NULL UNIQUE,
        password_hash   NVARCHAR(500)  NOT NULL,
        role            NVARCHAR(50)   NOT NULL DEFAULT 'viewer',  -- admin, analyst, viewer, operator
        email           NVARCHAR(200)  NULL,
        full_name       NVARCHAR(200)  NULL,
        disabled        BIT            NOT NULL DEFAULT 0,
        failed_attempts INT            NOT NULL DEFAULT 0,
        locked_until    DATETIME2      NULL,
        last_login      DATETIME2      NULL,
        created_at      DATETIME2      NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Tabela WatcherDB_Users criada.';
END
GO

-- 2. Tabela de Auth Log
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'WatcherDB_Auth_Log')
BEGIN
    CREATE TABLE dbo.WatcherDB_Auth_Log (
        id          INT IDENTITY(1,1) PRIMARY KEY,
        username    NVARCHAR(100)  NOT NULL,
        action      NVARCHAR(50)   NOT NULL,  -- LOGIN_SUCCESS, LOGIN_FAILED, PASSWORD_CHANGE, USER_ENABLED, USER_DISABLED
        ip_address  NVARCHAR(50)   NULL,
        details     NVARCHAR(500)  NULL,
        created_at  DATETIME2      NOT NULL DEFAULT GETDATE()
    );

    CREATE NONCLUSTERED INDEX IX_AuthLog_Username
        ON dbo.WatcherDB_Auth_Log (username, created_at DESC);

    PRINT 'Tabela WatcherDB_Auth_Log criada.';
END
GO

-- 3. Tabela de Preferencias por Utilizador
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'WatcherDB_User_Preferences')
BEGIN
    CREATE TABLE dbo.WatcherDB_User_Preferences (
        id               INT IDENTITY(1,1) PRIMARY KEY,
        username         NVARCHAR(100)  NOT NULL,
        preference_key   NVARCHAR(100)  NOT NULL,
        preference_value NVARCHAR(MAX)  NULL,  -- Valor ENCRIPTADO com Fernet
        updated_at       DATETIME2      NOT NULL DEFAULT GETDATE(),

        CONSTRAINT UQ_UserPref_Key UNIQUE (username, preference_key)
    );

    CREATE NONCLUSTERED INDEX IX_UserPref_Username
        ON dbo.WatcherDB_User_Preferences (username)
        INCLUDE (preference_key, preference_value);

    PRINT 'Tabela WatcherDB_User_Preferences criada.';
END
GO

-- 4. Inserir Users Default (password: admin123)
-- Hash bcrypt gerado com: python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('admin123'))"
-- Hash bcrypt para "admin123" (gerado com passlib)
DECLARE @hash NVARCHAR(500) = '$2b$12$w8ge4gtxBD2xEtacbiNssuctD4y3YqFtK5XMVYBjOEkiWUj20.VlS';

IF NOT EXISTS (SELECT 1 FROM dbo.WatcherDB_Users WHERE username = 'admin')
    INSERT INTO dbo.WatcherDB_Users (username, password_hash, role, full_name)
    VALUES ('admin', @hash, 'admin', 'Administrador');

IF NOT EXISTS (SELECT 1 FROM dbo.WatcherDB_Users WHERE username = 'salomao')
    INSERT INTO dbo.WatcherDB_Users (username, password_hash, role, full_name)
    VALUES ('salomao', @hash, 'admin', 'Salomao');

IF NOT EXISTS (SELECT 1 FROM dbo.WatcherDB_Users WHERE username = 'ricardo')
    INSERT INTO dbo.WatcherDB_Users (username, password_hash, role, full_name)
    VALUES ('ricardo', @hash, 'admin', 'Ricardo');

IF NOT EXISTS (SELECT 1 FROM dbo.WatcherDB_Users WHERE username = 'viewer')
    INSERT INTO dbo.WatcherDB_Users (username, password_hash, role, full_name)
    VALUES ('viewer', @hash, 'viewer', 'Utilizador Viewer');
GO

PRINT 'Users default inseridos (password: admin123).';
PRINT 'IMPORTANTE: Alterar passwords apos primeiro login!';
GO
