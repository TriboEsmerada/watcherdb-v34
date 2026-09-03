#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DBA Copilot Service — Rule-Based Engine
========================================

Business logic for the DBA Copilot feature.
Provides expert-level SQL Server DBA knowledge through pattern matching
and pre-defined knowledge bases.

Tier gating (Standard Edition vs Pro Edition)
---------------------------------------------
The rule-based engine (this module) is a Standard Edition feature — available
in both V3.3 Std and V5 Pro. The LLM delegation path is a Pro Edition feature
and is gated in services/llm_client.py: is_llm_enabled() returns False whenever
WATCHERDB_EDITION != "pro", regardless of LLM_ENABLED. See
watcherdb-council/docs/FEATURE_MATRIX.md for the canonical tier matrix.

Behaviour summary:
  * V3.3 Standard client (WATCHERDB_EDITION=standard, default)
      → rule-based answers only; LLM branch never invoked.
  * V3.3 dev/test (WATCHERDB_EDITION=pro + LLM_ENABLED=true)
      → LLM branch eligible for internal validation.

Knowledge domains:
- Backup: FULL/DIFF/LOG best practices, RPO/RTO, backup chain integrity
- Performance: Wait stats, missing indexes, parameter sniffing, statistics
- AlwaysOn: AG health, replica lag, failover, synchronization modes
- Space: Filegroup growth, autogrow, log management, TempDB
- Jobs: Schedule conflicts, job chains, failed job troubleshooting
- Security: TDE, audit, permissions, SQL injection prevention

Author: WatcherDB Team
Date: 2026-03-31
Version: 1.1.0 (FIND-20260417-004 Fase 1 — edition gating documented)
"""

import re
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from services.llm_client import get_llm_client, is_llm_enabled, get_llm_provider

logger = logging.getLogger(__name__)


# ========================================
# QUICK ANSWERS — Pre-defined Q&A pairs
# ========================================
QUICK_ANSWERS: List[Dict[str, str]] = [
    {
        "question": "Como verificar o estado dos backups?",
        "answer": (
            "Execute a query abaixo para ver o ultimo backup de cada base:\n\n"
            "```sql\n"
            "SELECT d.name AS database_name,\n"
            "       MAX(CASE WHEN b.type = 'D' THEN b.backup_finish_date END) AS last_full,\n"
            "       MAX(CASE WHEN b.type = 'I' THEN b.backup_finish_date END) AS last_diff,\n"
            "       MAX(CASE WHEN b.type = 'L' THEN b.backup_finish_date END) AS last_log\n"
            "FROM sys.databases d\n"
            "LEFT JOIN msdb.dbo.backupset b ON d.name = b.database_name\n"
            "WHERE d.database_id > 4\n"
            "GROUP BY d.name\n"
            "ORDER BY last_full;\n"
            "```"
        ),
    },
    {
        "question": "Quais os wait stats mais criticos?",
        "answer": (
            "Para identificar os top wait stats:\n\n"
            "```sql\n"
            "SELECT TOP 10\n"
            "    wait_type,\n"
            "    wait_time_ms / 1000.0 AS wait_time_s,\n"
            "    signal_wait_time_ms / 1000.0 AS signal_wait_s,\n"
            "    waiting_tasks_count,\n"
            "    100.0 * wait_time_ms / SUM(wait_time_ms) OVER() AS pct\n"
            "FROM sys.dm_os_wait_stats\n"
            "WHERE wait_type NOT IN (\n"
            "    'SLEEP_TASK','BROKER_TO_FLUSH','SQLTRACE_BUFFER_FLUSH',\n"
            "    'CLR_AUTO_EVENT','CLR_MANUAL_EVENT','LAZYWRITER_SLEEP',\n"
            "    'CHECKPOINT_QUEUE','WAITFOR','XE_TIMER_EVENT',\n"
            "    'BROKER_EVENTHANDLER','FT_IFTS_SCHEDULER_IDLE_WAIT',\n"
            "    'XE_DISPATCHER_WAIT','HADR_FILESTREAM_IOMGR_IOCOMPLETION'\n"
            ")\n"
            "ORDER BY wait_time_ms DESC;\n"
            "```\n\n"
            "Waits criticos: CXPACKET (paralelismo), LCK_M_X (locks), PAGEIOLATCH (I/O disco), "
            "RESOURCE_SEMAPHORE (memoria)."
        ),
    },
    {
        "question": "Como verificar o AlwaysOn AG?",
        "answer": (
            "Para verificar a saude do Availability Group:\n\n"
            "```sql\n"
            "SELECT ag.name AS ag_name,\n"
            "       ar.replica_server_name,\n"
            "       ars.role_desc,\n"
            "       ars.synchronization_health_desc,\n"
            "       ars.connected_state_desc,\n"
            "       drs.synchronization_state_desc,\n"
            "       drs.log_send_queue_size,\n"
            "       drs.redo_queue_size\n"
            "FROM sys.availability_groups ag\n"
            "JOIN sys.availability_replicas ar ON ag.group_id = ar.group_id\n"
            "JOIN sys.dm_hadr_availability_replica_states ars\n"
            "     ON ar.replica_id = ars.replica_id\n"
            "LEFT JOIN sys.dm_hadr_database_replica_states drs\n"
            "     ON ar.replica_id = drs.replica_id\n"
            "ORDER BY ag.name, ar.replica_server_name;\n"
            "```"
        ),
    },
    {
        "question": "Como encontrar indexes em falta?",
        "answer": (
            "O SQL Server sugere indexes automaticamente via DMVs:\n\n"
            "```sql\n"
            "SELECT TOP 20\n"
            "    CONVERT(DECIMAL(18,2), migs.avg_user_impact\n"
            "        * (migs.user_seeks + migs.user_scans)) AS improvement_measure,\n"
            "    DB_NAME(mid.database_id) AS db_name,\n"
            "    mid.statement AS table_name,\n"
            "    mid.equality_columns,\n"
            "    mid.inequality_columns,\n"
            "    mid.included_columns,\n"
            "    migs.user_seeks, migs.user_scans\n"
            "FROM sys.dm_db_missing_index_groups mig\n"
            "JOIN sys.dm_db_missing_index_group_stats migs\n"
            "     ON mig.index_group_handle = migs.group_handle\n"
            "JOIN sys.dm_db_missing_index_details mid\n"
            "     ON mig.index_handle = mid.index_handle\n"
            "ORDER BY improvement_measure DESC;\n"
            "```\n\n"
            "Cuidado: nem todos os indexes sugeridos devem ser criados. Avalie o custo de manutencao."
        ),
    },
    {
        "question": "Como verificar espaco em disco?",
        "answer": (
            "Para ver espaco livre por volume:\n\n"
            "```sql\n"
            "SELECT DISTINCT\n"
            "    vs.volume_mount_point AS drive,\n"
            "    CONVERT(DECIMAL(18,2), vs.total_bytes / 1073741824.0) AS total_gb,\n"
            "    CONVERT(DECIMAL(18,2), vs.available_bytes / 1073741824.0) AS free_gb,\n"
            "    CONVERT(DECIMAL(5,2), vs.available_bytes * 100.0 / vs.total_bytes) AS free_pct\n"
            "FROM sys.master_files mf\n"
            "CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs\n"
            "ORDER BY free_pct;\n"
            "```\n\n"
            "Alerta se free_pct < 15%. Acao imediata se < 5%."
        ),
    },
    {
        "question": "Como analisar jobs com falha?",
        "answer": (
            "Para listar jobs que falharam nas ultimas 24h:\n\n"
            "```sql\n"
            "SELECT j.name AS job_name,\n"
            "       h.step_name,\n"
            "       h.run_date,\n"
            "       h.run_time,\n"
            "       h.run_duration,\n"
            "       h.message\n"
            "FROM msdb.dbo.sysjobs j\n"
            "JOIN msdb.dbo.sysjobhistory h ON j.job_id = h.job_id\n"
            "WHERE h.run_status = 0  -- Failed\n"
            "  AND CONVERT(DATE, CAST(h.run_date AS VARCHAR), 112)\n"
            "      >= DATEADD(DAY, -1, GETDATE())\n"
            "ORDER BY h.run_date DESC, h.run_time DESC;\n"
            "```"
        ),
    },
    {
        "question": "Como verificar sessoes bloqueadas?",
        "answer": (
            "Para identificar blocking chains:\n\n"
            "```sql\n"
            "SELECT\n"
            "    r.session_id AS blocked_spid,\n"
            "    r.blocking_session_id AS blocker_spid,\n"
            "    r.wait_type,\n"
            "    r.wait_time / 1000.0 AS wait_seconds,\n"
            "    DB_NAME(r.database_id) AS db_name,\n"
            "    t.text AS blocked_query,\n"
            "    (SELECT text FROM sys.dm_exec_sql_text(\n"
            "        (SELECT most_recent_sql_handle FROM sys.dm_exec_connections\n"
            "         WHERE session_id = r.blocking_session_id)\n"
            "    )) AS blocker_query\n"
            "FROM sys.dm_exec_requests r\n"
            "CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t\n"
            "WHERE r.blocking_session_id > 0\n"
            "ORDER BY r.wait_time DESC;\n"
            "```"
        ),
    },
    {
        "question": "Best practices para TempDB?",
        "answer": (
            "Recomendacoes para TempDB:\n\n"
            "1. **Ficheiros**: criar 1 ficheiro por core (max 8) com tamanho igual\n"
            "2. **Trace flag**: TF 1118 (pre-2016) para evitar mixed extents\n"
            "3. **Disco dedicado**: colocar TempDB em SSD/NVMe separado\n"
            "4. **Autogrow**: configurar em tamanho fixo (512MB-1GB), nunca percentual\n\n"
            "```sql\n"
            "-- Ver configuracao atual do TempDB\n"
            "SELECT name, physical_name,\n"
            "       size * 8 / 1024 AS size_mb,\n"
            "       growth * 8 / 1024 AS growth_mb,\n"
            "       CASE WHEN is_percent_growth = 1 THEN 'PERCENT' ELSE 'MB' END AS growth_type\n"
            "FROM sys.master_files\n"
            "WHERE database_id = 2;\n"
            "```\n\n"
            "```sql\n"
            "-- Adicionar ficheiro TempDB (exemplo)\n"
            "ALTER DATABASE tempdb\n"
            "ADD FILE (NAME = tempdev2,\n"
            "          FILENAME = 'T:\\TempDB\\tempdev2.ndf',\n"
            "          SIZE = 4096MB, FILEGROWTH = 512MB);\n"
            "```"
        ),
    },
    {
        "question": "Como configurar TDE (encryption)?",
        "answer": (
            "Passos para ativar Transparent Data Encryption:\n\n"
            "```sql\n"
            "-- 1. Criar Master Key no master\n"
            "USE master;\n"
            "CREATE MASTER KEY ENCRYPTION BY PASSWORD = 'StrongPassword123!';\n\n"
            "-- 2. Criar certificado\n"
            "CREATE CERTIFICATE TDECert WITH SUBJECT = 'TDE Certificate';\n\n"
            "-- 3. Criar DEK na base alvo\n"
            "USE [MinhaBase];\n"
            "CREATE DATABASE ENCRYPTION KEY\n"
            "WITH ALGORITHM = AES_256\n"
            "ENCRYPTION BY SERVER CERTIFICATE TDECert;\n\n"
            "-- 4. Ativar TDE\n"
            "ALTER DATABASE [MinhaBase] SET ENCRYPTION ON;\n\n"
            "-- 5. BACKUP DO CERTIFICADO (CRITICO!)\n"
            "BACKUP CERTIFICATE TDECert\n"
            "TO FILE = 'C:\\Backup\\TDECert.cer'\n"
            "WITH PRIVATE KEY (\n"
            "    FILE = 'C:\\Backup\\TDECert.pvk',\n"
            "    ENCRYPTION BY PASSWORD = 'BackupPassword!'\n"
            ");\n"
            "```\n\n"
            "IMPORTANTE: Sem o backup do certificado, nao e possivel restaurar a base noutro servidor!"
        ),
    },
    {
        "question": "Como atualizar estatisticas?",
        "answer": (
            "Atualizar estatisticas melhora a qualidade dos planos de execucao:\n\n"
            "```sql\n"
            "-- Atualizar todas as estatisticas de uma base\n"
            "EXEC sp_updatestats;\n\n"
            "-- Atualizar estatisticas de uma tabela especifica com full scan\n"
            "UPDATE STATISTICS dbo.MinhaTabela WITH FULLSCAN;\n\n"
            "-- Ver estatisticas desatualizadas\n"
            "SELECT OBJECT_NAME(s.object_id) AS table_name,\n"
            "       s.name AS stats_name,\n"
            "       STATS_DATE(s.object_id, s.stats_id) AS last_updated,\n"
            "       sp.modification_counter AS rows_modified\n"
            "FROM sys.stats s\n"
            "CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp\n"
            "WHERE sp.modification_counter > 1000\n"
            "ORDER BY sp.modification_counter DESC;\n"
            "```\n\n"
            "Regra: atualizar quando modification_counter > 20% do total de linhas."
        ),
    },
    {
        "question": "Como diagnosticar parameter sniffing?",
        "answer": (
            "Parameter sniffing causa planos sub-otimos quando o plano compilado nao serve para todos os valores:\n\n"
            "```sql\n"
            "-- Identificar queries com variancia alta no tempo de execucao\n"
            "SELECT TOP 20\n"
            "    qs.plan_handle,\n"
            "    SUBSTRING(qt.text, (qs.statement_start_offset/2)+1,\n"
            "        (CASE WHEN qs.statement_end_offset = -1\n"
            "             THEN LEN(CONVERT(NVARCHAR(MAX), qt.text)) * 2\n"
            "             ELSE qs.statement_end_offset END\n"
            "         - qs.statement_start_offset) / 2 + 1) AS query_text,\n"
            "    qs.execution_count,\n"
            "    qs.min_elapsed_time / 1000 AS min_ms,\n"
            "    qs.max_elapsed_time / 1000 AS max_ms,\n"
            "    (qs.max_elapsed_time - qs.min_elapsed_time) / 1000 AS variance_ms\n"
            "FROM sys.dm_exec_query_stats qs\n"
            "CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt\n"
            "WHERE qs.execution_count > 10\n"
            "  AND qs.max_elapsed_time > qs.min_elapsed_time * 10\n"
            "ORDER BY variance_ms DESC;\n"
            "```\n\n"
            "Solucoes: OPTION(RECOMPILE), OPTIMIZE FOR UNKNOWN, ou Query Store forced plan."
        ),
    },
    {
        "question": "Como verificar o log de transacoes?",
        "answer": (
            "Para monitorizar o log de transacoes:\n\n"
            "```sql\n"
            "-- Uso do log por base de dados\n"
            "DBCC SQLPERF(LOGSPACE);\n\n"
            "-- Motivo pelo qual o log nao pode ser reutilizado\n"
            "SELECT name, log_reuse_wait_desc\n"
            "FROM sys.databases\n"
            "WHERE log_reuse_wait_desc <> 'NOTHING';\n\n"
            "-- VLFs (Virtual Log Files) — muitos VLFs = performance degradada\n"
            "DBCC LOGINFO;\n"
            "```\n\n"
            "Se log_reuse_wait = LOG_BACKUP: executar backup de log.\n"
            "Se log_reuse_wait = ACTIVE_TRANSACTION: investigar transacao aberta."
        ),
    },
]


# ========================================
# KNOWLEDGE BASE — Pattern matching rules
# ========================================
KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "backup": {
        "keywords": [
            "backup", "restore", "recovery", "rpo", "rto", "backup chain",
            "full backup", "diff", "differential", "log backup", "copia",
            "recuperacao", "restaurar", "ponto no tempo", "point in time",
        ],
        "answer": (
            "**Estrategia de Backup Recomendada:**\n\n"
            "- **FULL**: Semanal (domingos) ou diario para bases criticas\n"
            "- **DIFFERENTIAL**: Diario (reduz janela de restore)\n"
            "- **LOG**: A cada 15-30 minutos (RPO < 30 min)\n\n"
            "Verificar integridade do backup chain:\n"
            "```sql\n"
            "-- Verificar se ha gaps no backup chain\n"
            "SELECT database_name,\n"
            "       type AS backup_type,\n"
            "       backup_start_date,\n"
            "       backup_finish_date,\n"
            "       first_lsn, last_lsn\n"
            "FROM msdb.dbo.backupset\n"
            "WHERE database_name = 'MinhaBase'\n"
            "ORDER BY backup_start_date DESC;\n"
            "```\n\n"
            "Testar restore regularmente! Backup sem teste nao e backup."
        ),
        "recommendations": [
            "Configurar backup de log a cada 15 minutos para bases criticas",
            "Testar restore de producao em ambiente de DR mensalmente",
            "Monitorizar backup chain integrity com alertas automaticos",
            "Usar CHECKSUM nos backups para validar integridade",
            "Considerar backup compression para reduzir espaco e tempo",
        ],
    },
    "performance": {
        "keywords": [
            "performance", "lento", "slow", "wait", "cpu", "memoria",
            "memory", "bloqueio", "lock", "deadlock", "query lenta",
            "slow query", "tunning", "tuning", "otimizar", "optimize",
            "desempenho", "plan cache", "execution plan",
        ],
        "answer": (
            "**Diagnostico de Performance SQL Server:**\n\n"
            "1. **Wait Stats** — identifique o bottleneck principal\n"
            "2. **Top Queries** — encontre as queries mais caras\n"
            "3. **Missing Indexes** — verifique sugestoes das DMVs\n"
            "4. **Statistics** — garanta que estao atualizadas\n\n"
            "```sql\n"
            "-- Top 10 queries por CPU\n"
            "SELECT TOP 10\n"
            "    qs.total_worker_time / qs.execution_count AS avg_cpu_us,\n"
            "    qs.execution_count,\n"
            "    SUBSTRING(qt.text, (qs.statement_start_offset/2)+1,\n"
            "        (CASE WHEN qs.statement_end_offset = -1\n"
            "             THEN LEN(CONVERT(NVARCHAR(MAX), qt.text)) * 2\n"
            "             ELSE qs.statement_end_offset END\n"
            "         - qs.statement_start_offset) / 2 + 1) AS query_text\n"
            "FROM sys.dm_exec_query_stats qs\n"
            "CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt\n"
            "ORDER BY qs.total_worker_time DESC;\n"
            "```"
        ),
        "recommendations": [
            "Usar Query Store para identificar regressoes de plano",
            "Verificar se auto-update statistics esta ativo",
            "Analisar wait stats antes de tomar accoes",
            "Considerar Resource Governor para workloads concorrentes",
            "Rever indexes fragmentados (> 30% = REBUILD, 5-30% = REORGANIZE)",
        ],
    },
    "alwayson": {
        "keywords": [
            "alwayson", "always on", "availability group", "ag", "replica",
            "failover", "synchronous", "asynchronous", "listener",
            "secondary", "primary", "hadr", "high availability", "ha",
            "disponibilidade", "replicacao", "lag", "redo queue",
            "log send queue",
        ],
        "answer": (
            "**AlwaysOn Availability Groups — Verificacao:**\n\n"
            "```sql\n"
            "-- Estado geral das replicas\n"
            "SELECT ag.name AS ag_name,\n"
            "       ar.replica_server_name,\n"
            "       ars.role_desc,\n"
            "       ars.synchronization_health_desc AS health,\n"
            "       drs.synchronization_state_desc AS sync_state,\n"
            "       drs.log_send_queue_size AS log_send_kb,\n"
            "       drs.redo_queue_size AS redo_kb,\n"
            "       drs.last_commit_time\n"
            "FROM sys.availability_groups ag\n"
            "JOIN sys.availability_replicas ar ON ag.group_id = ar.group_id\n"
            "JOIN sys.dm_hadr_availability_replica_states ars\n"
            "     ON ar.replica_id = ars.replica_id\n"
            "LEFT JOIN sys.dm_hadr_database_replica_states drs\n"
            "     ON ar.replica_id = drs.replica_id\n"
            "ORDER BY ag.name, ar.replica_server_name;\n"
            "```\n\n"
            "**Alertas criticos:**\n"
            "- log_send_queue_size > 100 MB: rede lenta ou secundario sobrecarregado\n"
            "- redo_queue_size > 500 MB: secundario nao consegue aplicar logs\n"
            "- synchronization_health != HEALTHY: investigar imediatamente"
        ),
        "recommendations": [
            "Monitorizar log_send_queue e redo_queue continuamente",
            "Configurar automatic failover apenas entre replicas synchronous-commit",
            "Testar failover manual em janela de manutencao trimestral",
            "Usar readable secondary para offload de reports/backups",
            "Configurar alertas para synchronization_health != HEALTHY",
        ],
    },
    "space": {
        "keywords": [
            "espaco", "space", "disco", "disk", "filegroup", "autogrow",
            "growth", "log file", "shrink", "tempdb", "ficheiro", "file",
            "volume", "storage", "armazenamento", "crescimento",
        ],
        "answer": (
            "**Gestao de Espaco SQL Server:**\n\n"
            "```sql\n"
            "-- Espaco por base de dados\n"
            "SELECT DB_NAME(database_id) AS db_name,\n"
            "       type_desc,\n"
            "       name AS file_name,\n"
            "       physical_name,\n"
            "       size * 8 / 1024 AS size_mb,\n"
            "       FILEPROPERTY(name, 'SpaceUsed') * 8 / 1024 AS used_mb,\n"
            "       (size - FILEPROPERTY(name, 'SpaceUsed')) * 8 / 1024 AS free_mb\n"
            "FROM sys.database_files;\n\n"
            "-- Autogrow settings (ATENCAO: evitar percentual!)\n"
            "SELECT DB_NAME(database_id) AS db_name, name,\n"
            "       growth * 8 / 1024 AS growth_mb,\n"
            "       is_percent_growth,\n"
            "       max_size\n"
            "FROM sys.master_files\n"
            "WHERE is_percent_growth = 1;  -- Bases com growth percentual\n"
            "```\n\n"
            "**Best practices:**\n"
            "- Autogrow em tamanho fixo (256MB-1GB), nunca percentual\n"
            "- NUNCA fazer SHRINK de data files em producao (causa fragmentacao)\n"
            "- Log file: manter pre-dimensionado, evitar autogrow frequente\n"
            "- TempDB: pre-dimensionar com 1 ficheiro por core (max 8)"
        ),
        "recommendations": [
            "Alterar autogrow de percentual para tamanho fixo (256MB-1GB)",
            "Monitorizar volumes com menos de 15% livre",
            "Pre-dimensionar data files para evitar autogrow frequente",
            "Configurar alertas de espaco em disco no WatcherDB",
            "Nunca usar SHRINKDATABASE em producao — causa fragmentacao massiva",
        ],
    },
    "jobs": {
        "keywords": [
            "job", "jobs", "agendamento", "schedule", "falha", "failed",
            "agent", "sql agent", "step", "tarefa", "execucao", "automation",
            "manutencao", "maintenance", "ola hallengren",
        ],
        "answer": (
            "**Gestao de SQL Agent Jobs:**\n\n"
            "```sql\n"
            "-- Jobs com falha recente\n"
            "SELECT j.name, jh.step_name, jh.run_status,\n"
            "       msdb.dbo.agent_datetime(jh.run_date, jh.run_time) AS run_datetime,\n"
            "       jh.run_duration, jh.message\n"
            "FROM msdb.dbo.sysjobs j\n"
            "JOIN msdb.dbo.sysjobhistory jh ON j.job_id = jh.job_id\n"
            "WHERE jh.run_status = 0\n"
            "  AND jh.step_id > 0\n"
            "ORDER BY msdb.dbo.agent_datetime(jh.run_date, jh.run_time) DESC;\n\n"
            "-- Jobs sobrepostos (mesmo horario)\n"
            "SELECT j.name, s.name AS schedule_name,\n"
            "       s.active_start_time, s.freq_type, s.freq_interval\n"
            "FROM msdb.dbo.sysjobs j\n"
            "JOIN msdb.dbo.sysjobschedules js ON j.job_id = js.job_id\n"
            "JOIN msdb.dbo.sysschedules s ON js.schedule_id = s.schedule_id\n"
            "WHERE j.enabled = 1\n"
            "ORDER BY s.active_start_time;\n"
            "```\n\n"
            "**Recomendacao:** usar Ola Hallengren Maintenance Solution para backups, "
            "index maintenance e DBCC CHECKDB."
        ),
        "recommendations": [
            "Implementar Ola Hallengren Maintenance Solution",
            "Evitar sobreposicao de jobs de manutencao pesados",
            "Configurar notificacao por email para falhas de jobs criticos",
            "Separar janela de CHECKDB da janela de index rebuild",
            "Documentar dependencias entre jobs (job chains)",
        ],
    },
    "security": {
        "keywords": [
            "security", "seguranca", "tde", "encryption", "encriptacao",
            "audit", "auditoria", "permissao", "permission", "login",
            "role", "sql injection", "vulnerabilidade", "acesso",
            "privilegio", "sa", "sysadmin",
        ],
        "answer": (
            "**Seguranca SQL Server — Checklist:**\n\n"
            "```sql\n"
            "-- 1. Verificar logins com sysadmin\n"
            "SELECT name, type_desc, is_disabled\n"
            "FROM sys.server_principals\n"
            "WHERE IS_SRVROLEMEMBER('sysadmin', name) = 1\n"
            "ORDER BY name;\n\n"
            "-- 2. Verificar bases sem TDE\n"
            "SELECT name, is_encrypted\n"
            "FROM sys.databases\n"
            "WHERE database_id > 4 AND is_encrypted = 0;\n\n"
            "-- 3. Verificar logins sem politica de password\n"
            "SELECT name, is_policy_checked, is_expiration_checked\n"
            "FROM sys.sql_logins\n"
            "WHERE is_policy_checked = 0 OR is_expiration_checked = 0;\n\n"
            "-- 4. Verificar permissoes excessivas\n"
            "SELECT dp.name, dp.type_desc,\n"
            "       pe.permission_name, pe.state_desc\n"
            "FROM sys.database_principals dp\n"
            "JOIN sys.database_permissions pe ON dp.principal_id = pe.grantee_principal_id\n"
            "WHERE pe.permission_name IN ('CONTROL','ALTER','ALTER ANY USER')\n"
            "ORDER BY dp.name;\n"
            "```\n\n"
            "**Regras de ouro:**\n"
            "- Desativar login 'sa' ou renomea-lo\n"
            "- Usar Windows Authentication sempre que possivel\n"
            "- Principio do minimo privilegio: GRANT apenas o necessario\n"
            "- Ativar SQL Server Audit para compliance"
        ),
        "recommendations": [
            "Ativar TDE em todas as bases de producao",
            "Desativar ou renomear o login 'sa'",
            "Implementar SQL Server Audit para rastreabilidade",
            "Rever permissoes trimestralmente — remover acessos desnecessarios",
            "Usar contained database users para reduzir dependencia de logins de instancia",
            "Parametrizar todas as queries — nunca concatenar input do utilizador",
        ],
    },
    "index": {
        "keywords": [
            "index", "indice", "fragmentacao", "fragmentation", "rebuild",
            "reorganize", "fill factor", "missing index", "unused index",
            "duplicate index", "columnstore",
        ],
        "answer": (
            "**Manutencao de Indexes:**\n\n"
            "```sql\n"
            "-- Fragmentacao de indexes\n"
            "SELECT OBJECT_NAME(ips.object_id) AS table_name,\n"
            "       i.name AS index_name,\n"
            "       ips.index_type_desc,\n"
            "       ips.avg_fragmentation_in_percent,\n"
            "       ips.page_count\n"
            "FROM sys.dm_db_index_physical_stats(\n"
            "    DB_ID(), NULL, NULL, NULL, 'LIMITED') ips\n"
            "JOIN sys.indexes i ON ips.object_id = i.object_id\n"
            "    AND ips.index_id = i.index_id\n"
            "WHERE ips.avg_fragmentation_in_percent > 10\n"
            "    AND ips.page_count > 1000\n"
            "ORDER BY ips.avg_fragmentation_in_percent DESC;\n"
            "```\n\n"
            "**Regras:**\n"
            "- 5-30% fragmentacao: ALTER INDEX REORGANIZE\n"
            "- > 30% fragmentacao: ALTER INDEX REBUILD\n"
            "- page_count < 1000: ignorar (tabelas pequenas)\n"
            "- Usar ONLINE = ON em Enterprise Edition para evitar locks"
        ),
        "recommendations": [
            "Implementar manutencao de indexes com Ola Hallengren",
            "Usar ONLINE rebuild em Enterprise Edition",
            "Remover indexes duplicados e nao utilizados",
            "Considerar Columnstore para tabelas de facto/analytics",
            "Monitorizar index usage stats para identificar indexes inuteis",
        ],
    },
}


# ========================================
# RULE-BASED INSIGHTS (default tips)
# ========================================
DEFAULT_INSIGHTS: List[Dict[str, str]] = [
    {
        "severity": "info",
        "title": "Verificacao de Backup Chain",
        "description": "Verifique regularmente se a cadeia de backups esta intacta para garantir restauracao point-in-time.",
        "suggested_action": "Executar validacao de backup chain semanalmente com RESTORE VERIFYONLY.",
    },
    {
        "severity": "warning",
        "title": "Estatisticas Desatualizadas",
        "description": "Estatisticas desatualizadas podem causar planos de execucao sub-otimos e degradacao de performance.",
        "suggested_action": "Verificar sys.dm_db_stats_properties para tabelas com modification_counter elevado.",
    },
    {
        "severity": "info",
        "title": "Index Maintenance Pendente",
        "description": "Indexes com fragmentacao > 30% devem ser reconstruidos para manter performance de leitura.",
        "suggested_action": "Implementar Ola Hallengren IndexOptimize com schedule semanal.",
    },
    {
        "severity": "info",
        "title": "Autogrow Percentual Detectado",
        "description": "Bases com autogrow percentual podem ter crescimentos imprevistos e causar pausa no servico.",
        "suggested_action": "Alterar autogrow de percentual para tamanho fixo (256MB-1GB).",
    },
    {
        "severity": "warning",
        "title": "Rever Permissoes Sysadmin",
        "description": "Logins com permissao sysadmin devem ser minimizados. Audite regularmente quem tem este privilegio.",
        "suggested_action": "Executar SELECT name FROM sys.server_principals WHERE IS_SRVROLEMEMBER('sysadmin', name) = 1.",
    },
]


class CopilotService:
    """
    Business logic for the DBA Copilot.
    Operates in rule-based mode by default; delegates to LLM when available.
    """

    def __init__(self):
        self._llm_client = get_llm_client()
        if self._llm_client:
            logger.info(
                f"CopilotService initialized with LLM: {self._llm_client.provider_name()}"
            )
        else:
            logger.info("CopilotService initialized in rule-based mode")

    # --------------------------------------------------
    # Status
    # --------------------------------------------------
    def get_status(self) -> Dict[str, Any]:
        """Return current copilot status."""
        llm_available = self._llm_client is not None and self._llm_client.is_available()
        return {
            "llm_available": llm_available,
            "provider": self._llm_client.provider_name() if llm_available else "Rule-Based Engine",
            "mode": "llm" if llm_available else "rule-based",
            "knowledge_domains": list(KNOWLEDGE_BASE.keys()),
            "quick_answers_count": len(QUICK_ANSWERS),
            "version": "1.0.0",
        }

    # --------------------------------------------------
    # Quick Answers
    # --------------------------------------------------
    def get_quick_answers(self) -> List[Dict[str, str]]:
        """Return pre-defined Q&A pairs for quick action buttons."""
        return QUICK_ANSWERS

    # --------------------------------------------------
    # Insights
    # --------------------------------------------------
    def get_insights(self, kpi_data: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
        """
        Generate proactive insights.
        If kpi_data is provided (from intelligence_kpis cache), generate data-driven insights.
        Otherwise, return rule-based default tips.
        """
        insights: List[Dict[str, str]] = []

        if kpi_data:
            insights.extend(self._insights_from_kpi_data(kpi_data))

        # Always include rule-based tips if we have fewer than 5 insights
        if len(insights) < 5:
            remaining = 5 - len(insights)
            for tip in DEFAULT_INSIGHTS[:remaining]:
                if not any(i["title"] == tip["title"] for i in insights):
                    insights.append(tip)

        return insights

    def _insights_from_kpi_data(self, kpi_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Generate insights from real KPI monitoring data."""
        insights = []

        # Check backup KPIs
        backup_issues = kpi_data.get("backup_issues", 0)
        if backup_issues and int(backup_issues) > 0:
            insights.append({
                "severity": "critical",
                "title": f"Backups em Falha: {backup_issues} bases",
                "description": (
                    f"Foram detectadas {backup_issues} bases de dados com problemas de backup. "
                    "Isto pode comprometer o RPO e a capacidade de recuperacao."
                ),
                "suggested_action": "Verificar msdb.dbo.backupset e corrigir jobs de backup em falha.",
            })

        # Check AlwaysOn health
        ag_unhealthy = kpi_data.get("ag_unhealthy", 0)
        if ag_unhealthy and int(ag_unhealthy) > 0:
            insights.append({
                "severity": "critical",
                "title": f"AlwaysOn AG Unhealthy: {ag_unhealthy} replicas",
                "description": (
                    f"{ag_unhealthy} replicas do Availability Group estao com estado nao saudavel. "
                    "Failover automatico pode estar comprometido."
                ),
                "suggested_action": "Verificar sys.dm_hadr_availability_replica_states e resolver problemas de sincronizacao.",
            })

        # Check disk space
        disk_critical = kpi_data.get("disk_critical", 0)
        if disk_critical and int(disk_critical) > 0:
            insights.append({
                "severity": "critical",
                "title": f"Espaco em Disco Critico: {disk_critical} volumes",
                "description": (
                    f"{disk_critical} volumes estao com espaco livre abaixo do limiar critico (< 5%). "
                    "Risco de paragem de servico."
                ),
                "suggested_action": "Libertar espaco, expandir volumes ou mover ficheiros para outros discos.",
            })

        # Check blocked sessions
        blocked = kpi_data.get("blocked_sessions", 0)
        if blocked and int(blocked) > 0:
            insights.append({
                "severity": "warning",
                "title": f"Sessoes Bloqueadas: {blocked} activas",
                "description": (
                    f"Existem {blocked} sessoes bloqueadas no ambiente. "
                    "Isto pode causar timeouts e degradacao de performance."
                ),
                "suggested_action": "Investigar blocking chains com sys.dm_exec_requests e considerar intervencao.",
            })

        # Check failed jobs
        failed_jobs = kpi_data.get("failed_jobs", 0)
        if failed_jobs and int(failed_jobs) > 0:
            insights.append({
                "severity": "warning",
                "title": f"Jobs em Falha: {failed_jobs} nas ultimas 24h",
                "description": (
                    f"{failed_jobs} SQL Agent jobs falharam nas ultimas 24 horas. "
                    "Tarefas de manutencao podem estar comprometidas."
                ),
                "suggested_action": "Rever msdb.dbo.sysjobhistory para identificar e corrigir falhas.",
            })

        return insights

    # --------------------------------------------------
    # Ask Question — Pattern matching + optional LLM
    # --------------------------------------------------
    async def ask_question(
        self,
        question: str,
        include_recommendations: bool = True,
    ) -> Dict[str, Any]:
        """
        Answer a DBA question using pattern matching or LLM.
        """
        question_lower = question.lower().strip()

        # First: try to match a quick answer exactly
        for qa in QUICK_ANSWERS:
            if self._text_similarity(question_lower, qa["question"].lower()) > 0.7:
                return {
                    "answer": qa["answer"],
                    "recommendations": [],
                    "source": "quick_answers",
                }

        # Second: try knowledge base pattern matching
        best_match = self._match_knowledge_base(question_lower)
        if best_match:
            kb = KNOWLEDGE_BASE[best_match]
            result = {
                "answer": kb["answer"],
                "source": "knowledge_base",
                "topic": best_match,
            }
            if include_recommendations:
                result["recommendations"] = kb.get("recommendations", [])
            return result

        # Third: try LLM if available
        if self._llm_client and self._llm_client.is_available():
            try:
                llm_answer = await self._llm_client.ask(question)
                return {
                    "answer": llm_answer,
                    "recommendations": [],
                    "source": "llm",
                }
            except Exception as e:
                logger.error(f"LLM error, falling back to rule-based: {e}")

        # Fallback: generic helpful response
        return {
            "answer": (
                "Nao encontrei uma resposta especifica para essa pergunta na base de conhecimento. "
                "Tente perguntar sobre um destes topicos:\n\n"
                "- **Backups**: estrategias, restore, RPO/RTO\n"
                "- **Performance**: wait stats, queries lentas, tuning\n"
                "- **AlwaysOn**: AG health, replicas, failover\n"
                "- **Espaco**: disco, filegroups, autogrow, TempDB\n"
                "- **Jobs**: SQL Agent, falhas, schedules\n"
                "- **Seguranca**: TDE, audit, permissoes\n"
                "- **Indexes**: fragmentacao, missing, rebuild\n\n"
                "Ou consulte as perguntas rapidas no painel lateral."
            ),
            "recommendations": [
                "Tente reformular a pergunta com termos mais especificos",
                "Use as perguntas rapidas para topicos comuns",
                "Ative o modo LLM para respostas mais flexiveis (requer configuracao)",
            ],
            "source": "fallback",
        }

    def _match_knowledge_base(self, question: str) -> Optional[str]:
        """Find the best matching knowledge base topic for a question."""
        scores: Dict[str, int] = {}
        for topic, kb in KNOWLEDGE_BASE.items():
            score = sum(1 for kw in kb["keywords"] if kw in question)
            if score > 0:
                scores[topic] = score

        if not scores:
            return None
        return max(scores, key=scores.get)

    def _text_similarity(self, a: str, b: str) -> float:
        """Simple word-overlap similarity between two strings."""
        words_a = set(re.findall(r'\w+', a))
        words_b = set(re.findall(r'\w+', b))
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        return len(intersection) / max(len(words_a), len(words_b))

    # --------------------------------------------------
    # Generate Report
    # --------------------------------------------------
    async def generate_report(
        self,
        report_type: str,
        kpi_data: Optional[Dict[str, Any]] = None,
        period_hours: int = 24,
    ) -> Dict[str, Any]:
        """Generate a summary report from monitoring data."""
        now = datetime.now()

        if report_type == "daily_summary":
            return self._generate_daily_summary(now, kpi_data, period_hours)
        elif report_type == "health_check":
            return self._generate_health_check(now, kpi_data)
        else:
            return {
                "title": "Tipo de Relatorio Desconhecido",
                "content": f"O tipo de relatorio '{report_type}' nao e suportado.\n\nTipos disponiveis:\n- daily_summary\n- health_check",
                "key_findings": [],
            }

    def _generate_daily_summary(
        self,
        now: datetime,
        kpi_data: Optional[Dict[str, Any]],
        period_hours: int,
    ) -> Dict[str, Any]:
        """Generate daily summary report."""
        date_str = now.strftime("%d/%m/%Y %H:%M")
        findings = []

        content_lines = [
            f"=== RESUMO DIARIO — {date_str} ===",
            f"Periodo: ultimas {period_hours} horas",
            "",
        ]

        if kpi_data:
            # Server health
            total_servers = kpi_data.get("total_servers", "N/A")
            servers_online = kpi_data.get("servers_online", "N/A")
            content_lines.append(f"SERVIDORES: {servers_online}/{total_servers} online")

            # Backups
            backup_ok = kpi_data.get("backup_ok", "N/A")
            backup_issues = kpi_data.get("backup_issues", 0)
            content_lines.append(f"BACKUPS: {backup_ok} OK | {backup_issues} com problemas")
            if backup_issues and int(backup_issues) > 0:
                findings.append(f"{backup_issues} bases com problemas de backup — investigar imediatamente")

            # AlwaysOn
            ag_healthy = kpi_data.get("ag_healthy", "N/A")
            ag_unhealthy = kpi_data.get("ag_unhealthy", 0)
            content_lines.append(f"ALWAYSON: {ag_healthy} saudaveis | {ag_unhealthy} com problemas")
            if ag_unhealthy and int(ag_unhealthy) > 0:
                findings.append(f"{ag_unhealthy} replicas AG nao saudaveis")

            # Disk
            disk_ok = kpi_data.get("disk_ok", "N/A")
            disk_warning = kpi_data.get("disk_warning", 0)
            disk_critical = kpi_data.get("disk_critical", 0)
            content_lines.append(f"DISCO: {disk_ok} OK | {disk_warning} warning | {disk_critical} critico")
            if disk_critical and int(disk_critical) > 0:
                findings.append(f"{disk_critical} volumes com espaco critico (< 5%)")

            # Jobs
            failed_jobs = kpi_data.get("failed_jobs", 0)
            content_lines.append(f"JOBS: {failed_jobs} falhas nas ultimas 24h")
            if failed_jobs and int(failed_jobs) > 0:
                findings.append(f"{failed_jobs} jobs SQL Agent falharam")

            # Alerts
            total_alerts = kpi_data.get("total_alerts", 0)
            content_lines.append(f"ALERTAS: {total_alerts} total")
        else:
            content_lines.extend([
                "NOTA: Dados de monitoring nao disponiveis.",
                "O relatorio sera mais completo quando ligado ao WatcherDB Intelligence.",
                "",
                "Recomendacoes gerais para verificacao diaria:",
                "1. Verificar estado dos backups (FULL + LOG)",
                "2. Verificar saude do AlwaysOn AG",
                "3. Verificar espaco em disco (alertas < 15%)",
                "4. Rever jobs com falha nas ultimas 24h",
                "5. Verificar alertas pendentes no dashboard",
            ])
            findings.append("Ligar ao WatcherDB Intelligence para relatorios com dados reais")

        if not findings:
            findings.append("Nenhum problema critico detectado no periodo analisado")

        content_lines.append("")
        content_lines.append(f"Relatorio gerado: {date_str}")
        content_lines.append("Modo: Rule-Based" if not (self._llm_client and self._llm_client.is_available()) else "Modo: LLM-Assisted")

        return {
            "title": f"Resumo Diario — {now.strftime('%d/%m/%Y')}",
            "content": "\n".join(content_lines),
            "key_findings": findings,
            "report_type": "daily_summary",
            "generated_at": now.isoformat(),
        }

    def _generate_health_check(
        self,
        now: datetime,
        kpi_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate deep health assessment with scores."""
        date_str = now.strftime("%d/%m/%Y %H:%M")
        findings = []

        # Calculate health scores (0-100)
        scores = {
            "backup": 100,
            "availability": 100,
            "performance": 100,
            "space": 100,
            "security": 85,  # Always slightly below 100 as reminder to audit
            "jobs": 100,
        }

        if kpi_data:
            # Adjust scores based on real data
            backup_issues = int(kpi_data.get("backup_issues", 0) or 0)
            if backup_issues > 0:
                scores["backup"] = max(0, 100 - (backup_issues * 15))
                findings.append(f"Backup score reduzido: {backup_issues} bases com problemas")

            ag_unhealthy = int(kpi_data.get("ag_unhealthy", 0) or 0)
            if ag_unhealthy > 0:
                scores["availability"] = max(0, 100 - (ag_unhealthy * 20))
                findings.append(f"Availability score reduzido: {ag_unhealthy} replicas unhealthy")

            disk_critical = int(kpi_data.get("disk_critical", 0) or 0)
            disk_warning = int(kpi_data.get("disk_warning", 0) or 0)
            if disk_critical > 0 or disk_warning > 0:
                scores["space"] = max(0, 100 - (disk_critical * 25) - (disk_warning * 10))
                findings.append(f"Space score: {disk_critical} volumes criticos, {disk_warning} em warning")

            blocked = int(kpi_data.get("blocked_sessions", 0) or 0)
            if blocked > 0:
                scores["performance"] = max(0, 100 - (blocked * 10))

            failed_jobs = int(kpi_data.get("failed_jobs", 0) or 0)
            if failed_jobs > 0:
                scores["jobs"] = max(0, 100 - (failed_jobs * 5))
                findings.append(f"Jobs score reduzido: {failed_jobs} falhas")
        else:
            findings.append("Dados de monitoring nao disponiveis — scores baseados em defaults")

        # Overall score
        overall = sum(scores.values()) / len(scores)

        # Health grade
        if overall >= 90:
            grade = "A (Excelente)"
        elif overall >= 75:
            grade = "B (Bom)"
        elif overall >= 60:
            grade = "C (Aceitavel)"
        elif overall >= 40:
            grade = "D (Preocupante)"
        else:
            grade = "F (Critico)"

        content_lines = [
            f"=== HEALTH CHECK — {date_str} ===",
            "",
            f"NOTA GLOBAL: {overall:.0f}/100 — {grade}",
            "",
            "--- SCORES POR AREA ---",
        ]

        for area, score in scores.items():
            bar_len = score // 5
            bar = "█" * bar_len + "░" * (20 - bar_len)
            status = "OK" if score >= 80 else ("ATENCAO" if score >= 60 else "CRITICO")
            content_lines.append(f"  {area.upper():15s} [{bar}] {score:3d}/100  {status}")

        content_lines.extend([
            "",
            "--- RECOMENDACOES ---",
        ])

        if scores["backup"] < 100:
            content_lines.append("• BACKUP: Corrigir jobs de backup em falha. Testar restore.")
        if scores["availability"] < 100:
            content_lines.append("• ALWAYSON: Investigar replicas nao saudaveis. Verificar rede.")
        if scores["space"] < 100:
            content_lines.append("• ESPACO: Libertar espaco em volumes criticos. Rever autogrow.")
        if scores["performance"] < 100:
            content_lines.append("• PERFORMANCE: Investigar sessoes bloqueadas. Rever wait stats.")
        if scores["security"] < 100:
            content_lines.append("• SEGURANCA: Auditar permissoes sysadmin. Verificar TDE.")
        if scores["jobs"] < 100:
            content_lines.append("• JOBS: Corrigir SQL Agent jobs em falha.")

        if all(s >= 90 for s in scores.values()):
            content_lines.append("• Ambiente saudavel. Manter monitorizacao ativa.")

        content_lines.extend([
            "",
            f"Relatorio gerado: {date_str}",
            "Modo: Rule-Based" if not (self._llm_client and self._llm_client.is_available()) else "Modo: LLM-Assisted",
        ])

        if not findings:
            findings.append("Todos os indicadores dentro dos limiares normais")

        return {
            "title": f"Health Check — {now.strftime('%d/%m/%Y')} — {grade}",
            "content": "\n".join(content_lines),
            "key_findings": findings,
            "scores": scores,
            "overall_score": round(overall, 1),
            "grade": grade,
            "report_type": "health_check",
            "generated_at": now.isoformat(),
        }
