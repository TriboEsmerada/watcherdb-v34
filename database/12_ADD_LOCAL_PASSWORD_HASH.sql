-- ============================================================================
-- WatcherDB V3.2 — Adicionar coluna local_password_hash (Dual auth AD + local)
-- ============================================================================
-- Adiciona uma coluna opcional `local_password_hash` a `dbo.WatcherDB_Users` na
-- BD WatcherDB_Intelligence. Permite que users marcados como AD-only (campo
-- `password_hash` com prefixo 'ad_auth:') tenham TAMBEM uma password local de
-- fallback, usada apenas quando o Active Directory estiver inalcancavel.
--
-- Caso de uso real (2026-04-09):
-- ------------------------------
-- O user `ue_e-snetto` foi auto-provisionado por AD com `password_hash =
-- 'ad_auth:tapnet.tap.pt'`. Quando o DC `dchqprd02.tapnet.tap.pt:389` esta
-- inalcancavel (rede TAP fora, VPN desligada, firewall, etc), o login falha
-- com a mensagem "Utilize as credenciais Windows/AD" — sem alternativa.
--
-- Esta coluna permite associar um bcrypt local opcional ao mesmo user. O
-- fluxo de authenticate() passa a ser:
--
--   1. Tentar AD/LDAP (preferencial — se DC alcancavel, AD ganha sempre)
--   2. Se AD falha (timeout/DC down/credenciais invalidas):
--      a) Se user.local_password_hash existe → tentar bcrypt verify
--      b) Senao se user.password_hash for legacy bcrypt (sem prefixo) → usar
--      c) Senao se user.password_hash for 'ad_auth:...' → "AD indisponivel"
--
-- Backwards compatibility:
-- ------------------------
-- - Os 8 users locais existentes (admin, salomao, ricardo, etc) que tem
--   `password_hash = '$2b$12$...'` continuam a funcionar sem mudancas — o
--   ramo 2b apanha-os.
-- - Users AD-only existentes (`ad_auth:...`) ficam inalterados ate' alguem
--   correr `tools/set_local_password.py` para definir a fallback password.
-- - A coluna e' NULL por defeito; ninguem e' forcado a mudar.
--
-- Permissoes:
-- -----------
-- sql_monitoring e' db_owner desta BD, pode correr este script ele proprio.
--
-- Idempotencia:
-- -------------
-- Idempotente (IF NOT EXISTS via sys.columns). Pode ser corrido N vezes.
--
-- Rollback:
-- ---------
-- Ver bloco -- ROLLBACK no final do ficheiro (comentado).
-- ============================================================================

USE WatcherDB_Intelligence;
GO

SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
GO

PRINT '====================================================================';
PRINT 'Adding local_password_hash to dbo.WatcherDB_Users (dual auth fallback)';
PRINT '====================================================================';
GO

-- ----------------------------------------------------------------------------
-- 1. Adicionar a coluna se nao existir
-- ----------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users')
      AND name = 'local_password_hash'
)
BEGIN
    ALTER TABLE dbo.WatcherDB_Users
        ADD local_password_hash NVARCHAR(500) NULL;
    PRINT 'Column dbo.WatcherDB_Users.local_password_hash added.';
END
ELSE
    PRINT 'Column dbo.WatcherDB_Users.local_password_hash already exists — skipping.';
GO

-- ----------------------------------------------------------------------------
-- 2. (Opcional) Coluna timestamp para auditoria de quando foi definida
-- ----------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users')
      AND name = 'local_password_set_at'
)
BEGIN
    ALTER TABLE dbo.WatcherDB_Users
        ADD local_password_set_at DATETIME2(0) NULL;
    PRINT 'Column dbo.WatcherDB_Users.local_password_set_at added.';
END
ELSE
    PRINT 'Column dbo.WatcherDB_Users.local_password_set_at already exists — skipping.';
GO

-- ----------------------------------------------------------------------------
-- 3. Permissoes (defensivo — sql_monitoring ja' e' db_owner)
-- ----------------------------------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'sql_monitoring' AND type IN ('S','U'))
BEGIN
    -- O grant aplica-se a tabela inteira; nada novo a fazer ao nivel coluna.
    PRINT 'sql_monitoring ja tem db_owner — nenhum grant adicional necessario.';
END
ELSE
    PRINT 'WARNING: user "sql_monitoring" nao existe — sem grants.';
GO

-- ============================================================================
-- VERIFICACAO POST-DEPLOY
-- ============================================================================
PRINT '====================================================================';
PRINT 'Post-deploy verification:';
PRINT '====================================================================';

-- Listar todas as colunas da tabela (deve agora ter 13 colunas: 11 originais + 2 novas)
SELECT
    ORDINAL_POSITION,
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'WatcherDB_Users'
ORDER BY ORDINAL_POSITION;

-- Quantos users tem cada tipo de credencial
SELECT
    'AD-only (sem local fallback)' AS user_type,
    COUNT(*) AS cnt
FROM dbo.WatcherDB_Users
WHERE password_hash LIKE 'ad_auth:%' AND local_password_hash IS NULL
UNION ALL
SELECT
    'AD com local fallback',
    COUNT(*)
FROM dbo.WatcherDB_Users
WHERE password_hash LIKE 'ad_auth:%' AND local_password_hash IS NOT NULL
UNION ALL
SELECT
    'Local-only (legacy bcrypt em password_hash)',
    COUNT(*)
FROM dbo.WatcherDB_Users
WHERE password_hash NOT LIKE 'ad_auth:%' AND password_hash IS NOT NULL;
GO

PRINT '====================================================================';
PRINT 'Done. A coluna esta criada e pronta para uso pelo authenticate().';
PRINT 'Para definir uma fallback password local para um user AD:';
PRINT '    python tools/set_local_password.py';
PRINT '====================================================================';
GO

-- ============================================================================
-- ROLLBACK (so executar manualmente se for preciso desfazer)
-- ============================================================================
-- IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'local_password_set_at')
--     ALTER TABLE dbo.WatcherDB_Users DROP COLUMN local_password_set_at;
-- GO
-- IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'local_password_hash')
--     ALTER TABLE dbo.WatcherDB_Users DROP COLUMN local_password_hash;
-- GO
