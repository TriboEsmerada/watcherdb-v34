-- ============================================================================
-- CRIACAO: Sistema de Autenticação de Usuários
-- ============================================================================
-- Data: 2026-01-27
-- Descrição: Cria tabelas e procedures para autenticação de usuários
--            com senhas criptografadas e gestão completa de usuários
-- ============================================================================

USE [WatcherDB_Intelligence];
GO

PRINT '============================================================================';
PRINT 'CRIACAO: Sistema de Autenticação de Usuários';
PRINT '============================================================================';
PRINT 'Iniciando em: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
PRINT '';

-- ============================================================================
-- 1. CRIAR SCHEMA AUTH (se não existir)
-- ============================================================================

PRINT '-- [1/5] Verificando schema AUTH...';

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'auth')
BEGIN
    EXEC('CREATE SCHEMA auth');
    PRINT '  [OK] Schema AUTH criado';
END
ELSE
BEGIN
    PRINT '  [OK] Schema AUTH já existe';
END
GO

-- ============================================================================
-- 2. CRIAR TABELA DE USUÁRIOS
-- ============================================================================

PRINT '';
PRINT '-- [2/5] Criando tabela auth.Users...';

IF OBJECT_ID('auth.Users', 'U') IS NOT NULL
BEGIN
    PRINT '  [INFO] Tabela auth.Users já existe - dropando para recriar';
    DROP TABLE auth.Users;
END
GO

CREATE TABLE auth.Users (
    UserID INT IDENTITY(1,1) PRIMARY KEY,
    Username NVARCHAR(50) NOT NULL UNIQUE,
    PasswordHash NVARCHAR(255) NOT NULL,  -- Hash bcrypt da senha
    Email NVARCHAR(100) NULL UNIQUE,
    FullName NVARCHAR(100) NULL,
    Role NVARCHAR(20) NOT NULL DEFAULT 'viewer',  -- admin, operator, viewer

    -- Controle de conta
    IsActive BIT NOT NULL DEFAULT 1,
    IsLocked BIT NOT NULL DEFAULT 0,
    FailedLoginAttempts INT NOT NULL DEFAULT 0,
    LastFailedLogin DATETIME NULL,

    -- Auditoria
    CreatedAt DATETIME NOT NULL DEFAULT GETDATE(),
    CreatedBy NVARCHAR(50) NULL,
    ModifiedAt DATETIME NULL,
    ModifiedBy NVARCHAR(50) NULL,
    LastLoginAt DATETIME NULL,
    LastPasswordChange DATETIME NULL,

    -- Segurança adicional
    PasswordExpiryDays INT NULL DEFAULT 90,  -- NULL = nunca expira
    MustChangePassword BIT NOT NULL DEFAULT 0,

    CONSTRAINT CK_Users_Role CHECK (Role IN ('admin', 'operator', 'viewer'))
);
GO

-- Índices para performance
CREATE INDEX IX_Users_Username ON auth.Users(Username);
CREATE INDEX IX_Users_Email ON auth.Users(Email);
CREATE INDEX IX_Users_IsActive ON auth.Users(IsActive);
GO

PRINT '  [OK] Tabela auth.Users criada';

-- ============================================================================
-- 3. CRIAR TABELA DE HISTÓRICO DE LOGINS
-- ============================================================================

PRINT '';
PRINT '-- [3/5] Criando tabela auth.LoginHistory...';

IF OBJECT_ID('auth.LoginHistory', 'U') IS NOT NULL
BEGIN
    DROP TABLE auth.LoginHistory;
END
GO

CREATE TABLE auth.LoginHistory (
    LoginID INT IDENTITY(1,1) PRIMARY KEY,
    UserID INT NOT NULL,
    Username NVARCHAR(50) NOT NULL,
    LoginTime DATETIME NOT NULL DEFAULT GETDATE(),
    LoginSuccess BIT NOT NULL,
    IPAddress NVARCHAR(50) NULL,
    UserAgent NVARCHAR(500) NULL,
    FailureReason NVARCHAR(200) NULL,

    FOREIGN KEY (UserID) REFERENCES auth.Users(UserID)
);
GO

CREATE INDEX IX_LoginHistory_UserID ON auth.LoginHistory(UserID);
CREATE INDEX IX_LoginHistory_LoginTime ON auth.LoginHistory(LoginTime DESC);
GO

PRINT '  [OK] Tabela auth.LoginHistory criada';

-- ============================================================================
-- 4. CRIAR STORED PROCEDURES
-- ============================================================================

PRINT '';
PRINT '-- [4/5] Criando stored procedures...';

-- ============================================================================
-- 4.1. Procedure: Obter Usuário por Username
-- ============================================================================

IF OBJECT_ID('auth.sp_GetUserByUsername', 'P') IS NOT NULL
    DROP PROCEDURE auth.sp_GetUserByUsername;
GO

CREATE PROCEDURE auth.sp_GetUserByUsername
    @Username NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        UserID,
        Username,
        PasswordHash,
        Email,
        FullName,
        Role,
        IsActive,
        IsLocked,
        FailedLoginAttempts,
        MustChangePassword,
        LastLoginAt,
        CreatedAt
    FROM auth.Users
    WHERE Username = @Username;
END
GO

PRINT '  [OK] Procedure auth.sp_GetUserByUsername criada';

-- ============================================================================
-- 4.2. Procedure: Criar Novo Usuário
-- ============================================================================

IF OBJECT_ID('auth.sp_CreateUser', 'P') IS NOT NULL
    DROP PROCEDURE auth.sp_CreateUser;
GO

CREATE PROCEDURE auth.sp_CreateUser
    @Username NVARCHAR(50),
    @PasswordHash NVARCHAR(255),
    @Email NVARCHAR(100) = NULL,
    @FullName NVARCHAR(100) = NULL,
    @Role NVARCHAR(20) = 'viewer',
    @CreatedBy NVARCHAR(50) = NULL,
    @UserID INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        -- Verificar se username já existe
        IF EXISTS (SELECT 1 FROM auth.Users WHERE Username = @Username)
        BEGIN
            RAISERROR('Username já existe', 16, 1);
            RETURN;
        END

        -- Verificar se email já existe (se fornecido)
        IF @Email IS NOT NULL AND EXISTS (SELECT 1 FROM auth.Users WHERE Email = @Email)
        BEGIN
            RAISERROR('Email já cadastrado', 16, 1);
            RETURN;
        END

        -- Inserir novo usuário
        INSERT INTO auth.Users (
            Username,
            PasswordHash,
            Email,
            FullName,
            Role,
            CreatedBy,
            LastPasswordChange
        )
        VALUES (
            @Username,
            @PasswordHash,
            @Email,
            @FullName,
            @Role,
            @CreatedBy,
            GETDATE()
        );

        SET @UserID = SCOPE_IDENTITY();

    END TRY
    BEGIN CATCH
        THROW;
    END CATCH
END
GO

PRINT '  [OK] Procedure auth.sp_CreateUser criada';

-- ============================================================================
-- 4.3. Procedure: Registrar Login
-- ============================================================================

IF OBJECT_ID('auth.sp_RegisterLogin', 'P') IS NOT NULL
    DROP PROCEDURE auth.sp_RegisterLogin;
GO

CREATE PROCEDURE auth.sp_RegisterLogin
    @UserID INT,
    @Username NVARCHAR(50),
    @Success BIT,
    @IPAddress NVARCHAR(50) = NULL,
    @UserAgent NVARCHAR(500) = NULL,
    @FailureReason NVARCHAR(200) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- Registrar no histórico
    INSERT INTO auth.LoginHistory (
        UserID,
        Username,
        LoginSuccess,
        IPAddress,
        UserAgent,
        FailureReason
    )
    VALUES (
        @UserID,
        @Username,
        @Success,
        @IPAddress,
        @UserAgent,
        @FailureReason
    );

    -- Se sucesso, atualizar LastLoginAt e resetar falhas
    IF @Success = 1
    BEGIN
        UPDATE auth.Users
        SET LastLoginAt = GETDATE(),
            FailedLoginAttempts = 0,
            LastFailedLogin = NULL
        WHERE UserID = @UserID;
    END
    ELSE
    BEGIN
        -- Se falha, incrementar contador
        UPDATE auth.Users
        SET FailedLoginAttempts = FailedLoginAttempts + 1,
            LastFailedLogin = GETDATE(),
            IsLocked = CASE
                WHEN FailedLoginAttempts + 1 >= 5 THEN 1
                ELSE IsLocked
            END
        WHERE UserID = @UserID;
    END
END
GO

PRINT '  [OK] Procedure auth.sp_RegisterLogin criada';

-- ============================================================================
-- 4.4. Procedure: Alterar Senha
-- ============================================================================

IF OBJECT_ID('auth.sp_ChangePassword', 'P') IS NOT NULL
    DROP PROCEDURE auth.sp_ChangePassword;
GO

CREATE PROCEDURE auth.sp_ChangePassword
    @UserID INT,
    @NewPasswordHash NVARCHAR(255),
    @ModifiedBy NVARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE auth.Users
    SET PasswordHash = @NewPasswordHash,
        LastPasswordChange = GETDATE(),
        MustChangePassword = 0,
        ModifiedAt = GETDATE(),
        ModifiedBy = @ModifiedBy
    WHERE UserID = @UserID;
END
GO

PRINT '  [OK] Procedure auth.sp_ChangePassword criada';

-- ============================================================================
-- 4.5. Procedure: Listar Usuários
-- ============================================================================

IF OBJECT_ID('auth.sp_ListUsers', 'P') IS NOT NULL
    DROP PROCEDURE auth.sp_ListUsers;
GO

CREATE PROCEDURE auth.sp_ListUsers
    @IncludeInactive BIT = 0
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        UserID,
        Username,
        Email,
        FullName,
        Role,
        IsActive,
        IsLocked,
        FailedLoginAttempts,
        CreatedAt,
        LastLoginAt,
        LastPasswordChange
    FROM auth.Users
    WHERE (@IncludeInactive = 1 OR IsActive = 1)
    ORDER BY CreatedAt DESC;
END
GO

PRINT '  [OK] Procedure auth.sp_ListUsers criada';

-- ============================================================================
-- 5. INSERIR USUÁRIO ADMIN PADRÃO
-- ============================================================================

PRINT '';
PRINT '-- [5/5] Criando usuário admin padrão...';

-- Verificar se já existe usuário admin
IF NOT EXISTS (SELECT 1 FROM auth.Users WHERE Username = 'admin')
BEGIN
    -- Senha padrão: admin123
    -- Hash bcrypt: $2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIw.HpKgai

    INSERT INTO auth.Users (
        Username,
        PasswordHash,
        Email,
        FullName,
        Role,
        CreatedBy
    )
    VALUES (
        'admin',
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIw.HpKgai',
        'admin@watcherdb.local',
        'Administrator',
        'admin',
        'SYSTEM'
    );

    PRINT '  [OK] Usuário admin criado';
    PRINT '      Username: admin';
    PRINT '      Senha: admin123';
    PRINT '      IMPORTANTE: Altere a senha após primeiro login!';
END
ELSE
BEGIN
    PRINT '  [INFO] Usuário admin já existe';
END

-- Verificar se existe usuário viewer
IF NOT EXISTS (SELECT 1 FROM auth.Users WHERE Username = 'viewer')
BEGIN
    -- Senha padrão: viewer123
    -- Hash bcrypt: $2b$12$7ZiQ6C5LD7QzPqQKZ4DpOeKqN0/fF1GwqZJ6LhfF.qiJ7Q8F9H1yy

    INSERT INTO auth.Users (
        Username,
        PasswordHash,
        Email,
        FullName,
        Role,
        CreatedBy
    )
    VALUES (
        'viewer',
        '$2b$12$7ZiQ6C5LD7QzPqQKZ4DpOeKqN0/fF1GwqZJ6LhfF.qiJ7Q8F9H1yy',
        'viewer@watcherdb.local',
        'Viewer User',
        'viewer',
        'SYSTEM'
    );

    PRINT '  [OK] Usuário viewer criado';
    PRINT '      Username: viewer';
    PRINT '      Senha: viewer123';
END
ELSE
BEGIN
    PRINT '  [INFO] Usuário viewer já existe';
END

-- ============================================================================
-- 6. CRIAR VIEWS ÚTEIS
-- ============================================================================

PRINT '';
PRINT '-- Criando views auxiliares...';

-- View de usuários ativos
IF OBJECT_ID('auth.vw_ActiveUsers', 'V') IS NOT NULL
    DROP VIEW auth.vw_ActiveUsers;
GO

CREATE VIEW auth.vw_ActiveUsers
AS
SELECT
    UserID,
    Username,
    Email,
    FullName,
    Role,
    LastLoginAt,
    CreatedAt,
    DATEDIFF(DAY, LastLoginAt, GETDATE()) AS DaysSinceLastLogin
FROM auth.Users
WHERE IsActive = 1 AND IsLocked = 0;
GO

PRINT '  [OK] View auth.vw_ActiveUsers criada';

-- View de histórico recente de logins
IF OBJECT_ID('auth.vw_RecentLogins', 'V') IS NOT NULL
    DROP VIEW auth.vw_RecentLogins;
GO

CREATE VIEW auth.vw_RecentLogins
AS
SELECT TOP 100
    lh.LoginID,
    lh.Username,
    u.FullName,
    lh.LoginTime,
    lh.LoginSuccess,
    lh.IPAddress,
    lh.FailureReason
FROM auth.LoginHistory lh
LEFT JOIN auth.Users u ON lh.UserID = u.UserID
ORDER BY lh.LoginTime DESC;
GO

PRINT '  [OK] View auth.vw_RecentLogins criada';

-- ============================================================================
-- 7. VALIDAÇÃO FINAL
-- ============================================================================

PRINT '';
PRINT '-- Validando criação...';

-- Contar objetos criados
DECLARE @TableCount INT, @ProcCount INT, @ViewCount INT, @UserCount INT;

SELECT @TableCount = COUNT(*)
FROM sys.tables
WHERE schema_id = SCHEMA_ID('auth');

SELECT @ProcCount = COUNT(*)
FROM sys.procedures
WHERE schema_id = SCHEMA_ID('auth');

SELECT @ViewCount = COUNT(*)
FROM sys.views
WHERE schema_id = SCHEMA_ID('auth');

SELECT @UserCount = COUNT(*)
FROM auth.Users;

PRINT '  Tabelas criadas: ' + CAST(@TableCount AS VARCHAR(10));
PRINT '  Procedures criadas: ' + CAST(@ProcCount AS VARCHAR(10));
PRINT '  Views criadas: ' + CAST(@ViewCount AS VARCHAR(10));
PRINT '  Usuários cadastrados: ' + CAST(@UserCount AS VARCHAR(10));

-- Listar usuários
PRINT '';
PRINT '-- Usuários cadastrados:';
SELECT
    Username,
    Email,
    Role,
    IsActive,
    CreatedAt
FROM auth.Users
ORDER BY UserID;

PRINT '';
PRINT '============================================================================';
PRINT 'CRIACAO CONCLUIDA COM SUCESSO!';
PRINT '============================================================================';
PRINT 'Finalizado em: ' + CONVERT(VARCHAR(23), GETDATE(), 121);
PRINT '';
PRINT 'Sistema de Autenticação criado com sucesso!';
PRINT '';
PRINT 'CREDENCIAIS PADRÃO:';
PRINT '==================';
PRINT 'Admin:';
PRINT '  Username: admin';
PRINT '  Senha: admin123';
PRINT '';
PRINT 'Viewer:';
PRINT '  Username: viewer';
PRINT '  Senha: viewer123';
PRINT '';
PRINT 'IMPORTANTE: Altere as senhas padrão após primeiro login!';
PRINT '';
PRINT 'PRÓXIMOS PASSOS:';
PRINT '1. Alterar senhas padrão';
PRINT '2. Configurar web service para usar banco de dados';
PRINT '3. Testar login na interface web';
PRINT '============================================================================';
GO
