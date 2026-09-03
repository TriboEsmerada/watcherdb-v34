-- Script para testar detecção de TDE no servidor SQLHDSPRD214\I01
-- Execute este script conectado ao servidor para ver o resultado

-- ======================================
-- 1. Ver TODOS os certificados (exceto sistema)
-- ======================================
SELECT
    '1. TODOS OS CERTIFICADOS' AS secao,
    name as certificate_name,
    pvt_key_encryption_type_desc,
    issuer_name,
    subject,
    expiry_date,
    start_date,
    thumbprint
FROM sys.certificates WITH(NOLOCK)
WHERE name NOT LIKE '##%'  -- Excluir certificados de sistema
ORDER BY name;

-- ======================================
-- 2. Certificados com 'TDE' no nome
-- ======================================
SELECT
    '2. CERTIFICADOS COM TDE NO NOME' AS secao,
    name as certificate_name
FROM sys.certificates WITH(NOLOCK)
WHERE name LIKE '%TDE%';

-- ======================================
-- 3. Certificados com 'Cert' no nome
-- ======================================
SELECT
    '3. CERTIFICADOS COM CERT NO NOME' AS secao,
    name as certificate_name
FROM sys.certificates WITH(NOLOCK)
WHERE name LIKE '%Cert%';

-- ======================================
-- 4. Certificados ATIVAMENTE USADOS para criptografia
-- ======================================
SELECT
    '4. CERTIFICADOS USADOS PARA CRIPTOGRAFIA' AS secao,
    c.name as certificate_name,
    COUNT(DISTINCT dek.database_id) as databases_encrypted
FROM sys.certificates c WITH(NOLOCK)
INNER JOIN sys.dm_database_encryption_keys dek ON dek.encryptor_thumbprint = c.thumbprint
GROUP BY c.name;

-- ======================================
-- 5. Databases encriptadas e seus certificados
-- ======================================
SELECT
    '5. DATABASES ENCRIPTADAS' AS secao,
    d.name AS database_name,
    d.is_encrypted,
    c.name AS certificate_name,
    CASE dek.encryption_state
        WHEN 0 THEN 'Nenhum'
        WHEN 1 THEN 'Não criptografado'
        WHEN 2 THEN 'Criptografia em progresso'
        WHEN 3 THEN 'Criptografado'
        WHEN 4 THEN 'Chave em progresso'
        WHEN 5 THEN 'Chave de criptografia em progresso'
        WHEN 6 THEN 'Proteção em progresso'
        ELSE 'Desconhecido'
    END AS encryption_state
FROM sys.databases d WITH(NOLOCK)
LEFT JOIN sys.dm_database_encryption_keys dek ON d.database_id = dek.database_id
LEFT JOIN sys.certificates c ON dek.encryptor_thumbprint = c.thumbprint
WHERE d.database_id > 4  -- Excluir system databases
  AND d.state = 0  -- Apenas databases ONLINE
  AND d.is_encrypted = 1
ORDER BY d.name;

-- ======================================
-- 6. Testar EXATAMENTE a query corrigida (COM EXCLUSAO DE CERTIFICADOS DE SISTEMA)
-- ======================================
SELECT
    '6. QUERY CORRIGIDA (DEVE RETORNAR APENAS TDECert_TAP)' AS secao,
    CONVERT(CHAR(100), SERVERPROPERTY('Servername')) AS Server,
    name as certificate,
    pvt_key_encryption_type_desc,
    issuer_name,
    subject,
    expiry_date,
    start_date
FROM sys.certificates WITH(NOLOCK)
WHERE name NOT LIKE '##%'  -- Excluir certificados de sistema
  AND (
      name LIKE '%TDE%'
      OR EXISTS (
          SELECT 1
          FROM sys.dm_database_encryption_keys dek
          WHERE dek.encryptor_thumbprint = sys.certificates.thumbprint
      )
  );

-- ======================================
-- 7. Verificar se Always On está habilitado
-- ======================================
SELECT
    '7. ALWAYS ON STATUS' AS secao,
    SERVERPROPERTY('IsHadrEnabled') AS IsAlwaysOnEnabled,
    SERVERPROPERTY('HadrManagerStatus') AS HadrManagerStatus;

-- ======================================
-- 8. Availability Groups e Réplicas
-- ======================================
SELECT
    '8. AVAILABILITY GROUPS' AS secao,
    ag.name AS ag_name,
    ar.replica_server_name,
    ar.availability_mode_desc,
    ar.failover_mode_desc,
    ars.role_desc,
    ars.synchronization_health_desc
FROM sys.availability_groups ag
INNER JOIN sys.availability_replicas ar ON ag.group_id = ar.group_id
INNER JOIN sys.dm_hadr_availability_replica_states ars ON ar.replica_id = ars.replica_id
WHERE ars.is_local = 1;  -- Apenas réplica local
