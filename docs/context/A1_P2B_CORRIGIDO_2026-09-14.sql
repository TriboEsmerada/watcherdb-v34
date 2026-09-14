/* =============================================================================
   A1 -- P2b CORRIGIDO. Correr na WatcherDB_Intelligence da 8434.
   Data: 2026-09-14

   PORQUE FALHOU A PRIMEIRA VEZ (erro meu, nao teu):
   gerei as 3 vistas a partir da definicao VIVA (regra de 31/08) mas fui buscar o texto da
   PROCEDURE ao canonico. E o canonico esta a frente da base viva:

     canonico : 7 parametros, com @Service_Check_Attempted e @Service_Check_Method
     base viva: 5 parametros, e a TABELA nao tem essas duas colunas

   Dai os 4 erros 207 "Invalid column name 'Service_Check_Attempted' / 'Service_Check_Method'".
   O ALTER falhou por inteiro, logo a procedure ANTIGA continua em vigor e intacta -- nada
   ficou meio aplicado. O "procedure actualizada" que apareceu a seguir era um PRINT num lote
   proprio, que corre mesmo quando o lote anterior falha: corrigido aqui com verificacao real.

   ESTADO DEPOIS DA TUA CORRIDA:
     P1a  OK  -- 5 orfaos fechados
     P2   OK  -- coluna First_Event_Time criada
     P2b  FALHOU -- e' o que este script repara
     P3   OK  -- as 3 vistas recriadas (funcionam; COALESCE cobre o First_Event_Time a NULL)

   Enquanto o P2b nao correr, eventos novos nascem com First_Event_Time a NULL e o "desde"
   continua a mostrar a ultima confirmacao. Nada parte; so' nao melhora.
   ============================================================================= */
SET NOCOUNT ON;

IF DB_NAME() <> 'WatcherDB_Intelligence'
BEGIN
    RAISERROR('PARA: liga-te a WatcherDB_Intelligence antes de correr isto.', 16, 1);
    SET NOEXEC ON;
END
GO

PRINT '=== P2b (corrigido). Texto a partir da procedure VIVA, nao do canonico ===';
GO
ALTER PROCEDURE dbo.usp_MSSQL_Server_Offline_Upsert
    @Server_Name NVARCHAR(256),
    @Diagnosis NVARCHAR(50),
    @Ping_OK BIT,
    @Ping_Message NVARCHAR(500) = NULL,
    @Services_Down NVARCHAR(1000) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- MERGE: Se existe, atualiza. Se nao existe, insere.
    --
    -- A1 2026-09-14: Event_Time continua a ser reescrito a cada ciclo. E' a ULTIMA
    -- confirmacao, e e' assim que o auto-resolve e a frescura funcionam. O que muda e'
    -- First_Event_Time: gravado UMA vez, no INSERT, nunca tocado no UPDATE. Sem isto o
    -- "desde" da modal mostrava 1 minuto num servidor em baixo ha 6 horas (episodio 10/09).
    MERGE dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS AS target
    USING (SELECT @Server_Name AS Server_Name) AS source
    ON target.Server_Name = source.Server_Name AND target.Is_Resolved = 0
    WHEN MATCHED THEN
        UPDATE SET
            Diagnosis = @Diagnosis,
            Ping_OK = @Ping_OK,
            Ping_Message = @Ping_Message,
            Services_Down = @Services_Down,
            Event_Time = GETDATE()
    WHEN NOT MATCHED THEN
        INSERT (Server_Name, Diagnosis, Ping_OK, Ping_Message, Services_Down,
                Event_Time, First_Event_Time, Is_Resolved)
        VALUES (@Server_Name, @Diagnosis, @Ping_OK, @Ping_Message, @Services_Down,
                GETDATE(), GETDATE(), 0);
END;
GO

PRINT '=== Verificacao real (nao um PRINT optimista) ===';
IF OBJECT_DEFINITION(OBJECT_ID('dbo.usp_MSSQL_Server_Offline_Upsert')) LIKE '%First_Event_Time%'
    PRINT '  OK: a procedure viva ja grava First_Event_Time';
ELSE
BEGIN
    RAISERROR('FALHOU: a procedure NAO tem First_Event_Time. Nao continues, diz-me.', 16, 1);
END
GO

PRINT '=== Estado das 4 pecas ===';
SELECT 'eventos abertos' AS metrica, CAST(COUNT(*) AS VARCHAR(20)) AS valor
  FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS WHERE Is_Resolved = 0
UNION ALL SELECT 'orfaos fechados hoje',
  CAST(COUNT(*) AS VARCHAR(20)) FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS
  WHERE Resolved_By = 'auto-orphan-cleanup'
UNION ALL SELECT 'coluna First_Event_Time',
  CASE WHEN COL_LENGTH('dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS', 'First_Event_Time') IS NULL
       THEN 'EM FALTA' ELSE 'existe' END
UNION ALL SELECT 'procedure grava a hora de inicio',
  CASE WHEN OBJECT_DEFINITION(OBJECT_ID('dbo.usp_MSSQL_Server_Offline_Upsert')) LIKE '%First_Event_Time%'
       THEN 'sim' ELSE 'NAO' END
UNION ALL SELECT 'vistas ainda com a janela de 15 min',
  CAST((SELECT COUNT(*) FROM sys.sql_modules m
        WHERE m.object_id IN (OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_AGG_VIEW'),
                              OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_DET_VIEW'),
                              OBJECT_ID('dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW'))
          AND m.definition LIKE '%DATEADD(MINUTE, -15%') AS VARCHAR(20))
UNION ALL SELECT 'linhas na GROUPED_VIEW',
  CAST((SELECT COUNT(*) FROM dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW) AS VARCHAR(20));
-- Esperado: 0 abertos | 5 orfaos | existe | sim | 0 vistas com janela | 0 linhas
GO

/* =============================================================================
   ENSAIO -- prova P2 e P3 em minutos, sem tocar em nenhum servidor real.
   Corre isto DEPOIS do bloco acima dar tudo verde.
   ============================================================================= */
/*
EXEC dbo.usp_MSSQL_Server_Offline_Upsert
     @Server_Name = 'ZZZ_TEST_OFFLINE_SIM', @Diagnosis = 'offline', @Ping_OK = 0,
     @Ping_Message = 'ensaio A1 2026-09-14';

UPDATE dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS
   SET Event_Time = DATEADD(MINUTE, -20, GETDATE())
 WHERE Server_Name = 'ZZZ_TEST_OFFLINE_SIM' AND Is_Resolved = 0;

SELECT Server_Name, Env, First_Event_Time, Last_Seen_Time,
       Minutes_Since_First_Event, Minutes_Since_Last_Seen
  FROM dbo.KPI_MSSQL_SERVER_OFFLINE_GROUPED_VIEW WHERE Server_Name = 'ZZZ_TEST_OFFLINE_SIM';
-- Esperado: 1 linha; Minutes_Since_First_Event perto de 0 (a hora de inicio ficou gravada)
-- e Minutes_Since_Last_Seen perto de 20 (a ultima confirmacao envelheceu).
-- ANTES do A1 esta consulta devolvia 0 linhas: era esse o falso "Offline 0".

DELETE FROM dbo.KPI_MSSQL_SERVER_OFFLINE_EVENTS WHERE Server_Name = 'ZZZ_TEST_OFFLINE_SIM';
*/
