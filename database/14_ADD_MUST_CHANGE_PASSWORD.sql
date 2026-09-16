-- ============================================================================
-- 14: coluna must_change_password em dbo.WatcherDB_Users
-- ----------------------------------------------------------------------------
-- Data: 2026-09-16 | Gate: watcherdb-v1-intel-specialist (sem veto)
-- Identidade: owner/deploy da BD (NUNCA sql_monitoring, NUNCA utilizador de dominio)
-- Onde: servidor da Intelligence, base WatcherDB_Intelligence
--
-- PORQUE EXISTE: a coluna nunca foi criada na base viva. O script 07 punha o UPDATE a' coluna nova no MESMO
-- batch do ALTER, sem EXEC(), e o SQL Server recusava a batch inteira com o erro 207 (Invalid column name)
-- antes de correr o ALTER. Resultado: cada login escrevia "Invalid column name 'must_change_password'" no log
-- e a obrigacao de trocar a password no proximo login nao fazia nada.
--
-- Este ficheiro e' copia fiel do bloco ja canonico em INSTALACAO_COMPLETA_UNIFICADA.sql:10137-10142.
-- Substitui o 07 para efeitos de execucao (o 07 fica como registo historico).
--
-- EFEITO NESTA BASE (medido a 16/09: 11 utilizadores, 1 desactivado, 0 com o hash-semente admin123):
--   os 10 activos ficam a 0 (nao sao incomodados); o desactivado (viewer) fica a 1, e so lhe sera pedido
--   se algum dia for reactivado -- que e' o comportamento pretendido.
-- Custo: alteracao de metadados. BIT NOT NULL com DEFAULT constante nao reescreve a tabela.
--
-- Idempotente: se a coluna ja existir, nao faz nada.
-- ROLLBACK: ALTER TABLE dbo.WatcherDB_Users DROP COLUMN must_change_password;  (a restricao DEFAULT sai junto
--           em SQL Server 2016+; em versoes anteriores, largar primeiro a DEFAULT constraint pelo nome).
-- ============================================================================
USE [WatcherDB_Intelligence];
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WatcherDB_Users') AND name = 'must_change_password')
BEGIN
    ALTER TABLE dbo.WatcherDB_Users ADD must_change_password BIT NOT NULL DEFAULT 1;
    -- EXEC() obrigatorio: sem ele, esta batch nao compila (erro 207) porque a coluna ainda nao existe
    -- no momento em que o SQL Server compila o UPDATE. Foi exactamente esse o defeito do script 07.
    EXEC('UPDATE dbo.WatcherDB_Users SET must_change_password = 0 WHERE disabled = 0');
    PRINT '  [OK] must_change_password criada; utilizadores activos isentos.';
END
ELSE
    PRINT '  [SKIP] must_change_password ja existe.';
GO

-- Verificacao (leitura): a coluna existe e ninguem activo ficou obrigado sem querer.
SELECT COUNT(*) AS total,
       SUM(CASE WHEN must_change_password = 1 THEN 1 ELSE 0 END) AS obrigados,
       SUM(CASE WHEN must_change_password = 1 AND disabled = 0 THEN 1 ELSE 0 END) AS obrigados_activos
FROM dbo.WatcherDB_Users;
GO
