# -*- coding: utf-8 -*-
"""
GET /api/queries/tlog-diagnosis/{server_id}?database=...   (2026-09-02)

Drill-down de diagnostico do TRANSACTION LOG de uma base (layout "Diagnostico":
O que se passa / Diagnostico principal / O que fazer / Porque / Contexto /
Evidencia / Historico / Errorlog / Dados brutos), a partir do card por base do
modal "DB Transaction Logs". Replica a arquitectura do drill de mirroring
(mirroring_diagnosis.py) com o motor de regras do pacote T-Log do owner
(01-Coletor severidade/motivos; 02-Diagnostico secoes; 03 ordem de remediacao:
1 cadeia de backup -> 2 causa de retencao -> 3 shrink ate ao alvo -> 4 growth).
A pergunta nao e' "o log esta grande?" — e' "PORQUE nao trunca, QUEM segura e
QUANTO tempo ate o disco encher".

Identidade: pool (sql_monitoring: VIEW SERVER STATE + VIEW ANY DEFINITION +
VIEW DATABASE STATE + SELECT msdb). Sem sysadmin/db_owner/ALTER TRACE, logo:
  - VLFs via sys.dm_db_log_stats/dm_db_log_info (2016 SP2+; em 2012/2014 so'
    DBCC LOGINFO = db_owner -> nota, nao alarme);
  - transacoes abertas via dm_tran_* (sem DBCC OPENTRAN);
  - autogrow historico do default trace OMITIDO (fn_trace_gettable exige
    ALTER TRACE) — proxy: contador "Log Growths" + perfil de VLFs;
  - xp_readerrorlog corre em ULTIMO, com timeout proprio; sem GRANT explicito
    falha com Msg 229 (precedente 2026-06-23) e degrada com nota.
Thresholds: registry (tlog_usage 85/95, backup_delay_log 1h/2h) + constantes
documentadas em kpi_thresholds_registry['tlog_diagnosis'].
Capacidade EFECTIVA (owner 02/09): com max_size ilimitado o tecto real e' o
disco — o % do FICHEIRO continua a ser a metrica do card/registry; a urgencia
e' graduada por usado / (ficheiro + margem de crescimento).
Nada e' executado/alterado. DDL/BACKUP/KILL/SHRINK so' comentado. Nunca 500
por um bloco: cada fonte falha isoladamente e o texto diz o que faltou.
Gate sql-deep-reviewer 2026-09-02: msdb filtrado por backup_finish_date (indice
backupsetDate; backup_start_date = scan); dm_exec_requests.database_id e' o
CONTEXTO (backups correm de master -> filtrar pelo texto); 9002 ocupa duas
linhas no errorlog (pesquisar pelo nome entre apostrofes).
Formato de numeros (mockup owner 02/09): virgula decimal e ponto de milhares
(pt), tamanhos em GB com 2 decimais.
"""
from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from api.async_db import async_execute_on_server
from api.threshold_overrides import resolve as _th

logger = logging.getLogger(__name__)
router = APIRouter()

# Nenhum bloco usa identificador dinamico (so' literais N'..' com apostrofe
# duplicada por _esc), logo apostrofe/brackets sao nomes validos aqui.
_DBNAME = re.compile(r"^[^\x00-\x1f]{1,128}$")

# Constantes do motor (documentadas no registry 'tlog_diagnosis', nao configuraveis F1)
TRAN_MIN_WARN, TRAN_MIN_CRIT = 15, 120
VLF_WARN = 300
RUNWAY_DAYS_CRIT, RUNWAY_DAYS_WARN = 2.0, 7.0
TARGET_X_WARN, TARGET_X_CRIT = 3, 10
GROWTH_MIN_MB = 64
LOG_MIN_MB = 512
HEADROOM_MIN_MB = 1024
LOG_GROWTHS_WARN = 10
_TO = {"fast": 5, "mid": 10, "msdb": 15, "errorlog": 20}  # command timeout por bloco (s)

_RETAINED_OK = ("NOTHING", "LOG_BACKUP", "CHECKPOINT")
_REASON_TEXT = {
    "ACTIVE_TRANSACTION": ("Transação aberta segura o log", "rec_open_tran"),
    "DATABASE_MIRRORING": ("Fila do mirror segura o log", "rec_replica"),
    "AVAILABILITY_REPLICA": ("Fila do AG (réplica atrasada/suspensa) segura o log", "rec_replica"),
    "REPLICATION": ("Replication/CDC ainda não leu o log (log reader / capture job)", "rec_replication"),
    "ACTIVE_BACKUP_OR_RESTORE": ("Backup/restore em curso segura o log", "rec_wait_backup"),
    "OLDEST_PAGE": ("Checkpoint indirecto atrasado (página suja antiga) segura o log", "rec_checkpoint"),
    "XTP_CHECKPOINT": ("Checkpoint In-Memory OLTP pendente segura o log", "rec_checkpoint"),
    "LOG_SCAN": ("Log scan em curso (transitório)", "rec_recheck"),
    "OTHER_TRANSIENT": ("Motivo transitório (ver de novo em minutos)", "rec_recheck"),
    "AVAILABILITY_REPLICA_UNKNOWN": ("Réplica AG em estado desconhecido segura o log", "rec_replica"),
}


def _sid(instance: str) -> str:
    return (instance or "").strip().replace("\\", "_")


def _esc(v: str) -> str:
    return (v or "").replace("'", "''")


def _n(v, d=None):
    try:
        return float(v) if v is not None else d
    except (TypeError, ValueError):
        return d


def _i(v, d="?") -> str:
    """Inteiro sem '.0' (o executor converte ints em float via __float__)."""
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return d


def _num(v, nd: int = 1, d: str = "n/d") -> str:
    """Formato pt: ponto de milhares, vírgula decimal."""
    if v is None:
        return d
    try:
        s = f"{float(v):,.{nd}f}"
    except (TypeError, ValueError):
        return d
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _gb(mb, nd: int = 2) -> str:
    return "n/d" if mb is None else f"{_num(float(mb) / 1024.0, nd)} GB"


def _mb(mb) -> str:
    return "n/d" if mb is None else f"{_num(mb, 0)} MB"


def _dt(v) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v
    if v is None:
        return None
    try:
        return datetime.fromisoformat(str(v)[:19])
    except Exception:
        return None


def _fmt_dt(v) -> str:
    d = _dt(v)
    return d.strftime("%d/%m/%Y %H:%M") if d else (str(v)[:16] if v else "n/d")


def _fmt_dt_full(v) -> str:
    d = _dt(v)
    return d.strftime("%d/%m/%Y %H:%M:%S") if d else (str(v)[:19] if v else "n/d")


def _clean(s) -> str:
    return str(s or "").replace("\x00", "").strip()


async def _try(server_id: str, query: str, notes: List[str], label: str, timeout_s: int = 10,
               database: str = "master") -> List[Dict[str, Any]]:
    try:
        return await async_execute_on_server(server_id, query, database, timeout_s) or []
    except Exception as e:  # degradacao graciosa por bloco
        msg = str(e)[:180]
        logger.info(f"tlog-diagnosis {server_id} {label}: {msg}")
        notes.append(f"{label}: {msg}")
        return []


# ---------------------------------------------------------------- queries (gate sql-deep 02/09)
_Q_CAPS = """
SET NOCOUNT ON;
SELECT CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(32)) AS product_version,
       CAST(PARSENAME(CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(32)), 4) AS INT) AS major_version,
       CAST(SERVERPROPERTY('Edition') AS NVARCHAR(64)) AS edition,
       CAST(@@SERVERNAME AS NVARCHAR(128)) AS server_name,
       si.sqlserver_start_time,
       DATEDIFF(HOUR, si.sqlserver_start_time, GETDATE()) AS uptime_hours,
       GETDATE() AS server_now,
       CASE WHEN OBJECT_ID(N'sys.dm_db_log_stats') IS NOT NULL THEN 1 ELSE 0 END AS has_log_stats,
       CASE WHEN OBJECT_ID(N'sys.dm_db_log_info') IS NOT NULL THEN 1 ELSE 0 END AS has_log_info,
       CASE WHEN OBJECT_ID(N'sys.dm_exec_input_buffer') IS NOT NULL THEN 1 ELSE 0 END AS has_input_buffer
FROM sys.dm_os_sys_info si;
"""


def _q_state(db: str) -> str:
    return f"""
SET NOCOUNT ON;
SET LOCK_TIMEOUT 3000;
SELECT d.database_id, d.name AS database_name, d.state_desc, d.user_access_desc,
       d.recovery_model_desc, d.log_reuse_wait_desc,
       d.is_read_only, d.is_in_standby, d.is_auto_shrink_on,
       d.is_published, d.is_subscribed, d.is_cdc_enabled,
       HAS_DBACCESS(N'{_esc(db)}') AS has_db_access,
       (SELECT COUNT(*) FROM sys.master_files c WITH (NOLOCK) WHERE c.database_id = d.database_id AND c.type = 1) AS log_file_count,
       mf.file_id, mf.name AS log_logical_name, mf.physical_name AS log_physical_name, mf.state_desc AS log_file_state,
       CAST(mf.size AS BIGINT) * 8 / 1024 AS log_size_mb,
       CASE WHEN mf.max_size IN (-1, 268435456) THEN 1 ELSE 0 END AS log_unlimited,
       CASE WHEN mf.max_size IN (-1, 268435456) THEN NULL ELSE CAST(mf.max_size AS BIGINT) * 8 / 1024 END AS log_max_size_mb,
       CASE WHEN mf.growth = 0 THEN 1 ELSE 0 END AS log_growth_disabled,
       mf.is_percent_growth,
       CASE WHEN mf.is_percent_growth = 1 THEN mf.growth ELSE CAST(mf.growth AS BIGINT) * 8 / 1024 END AS log_growth_value,
       (SELECT SUM(CAST(r.size AS BIGINT)) * 8 / 1024 FROM sys.master_files r WITH (NOLOCK) WHERE r.database_id = d.database_id AND r.type = 0) AS data_size_mb
FROM sys.databases d WITH (NOLOCK)
LEFT JOIN sys.master_files mf WITH (NOLOCK) ON mf.database_id = d.database_id AND mf.type = 1
WHERE d.name = N'{_esc(db)}'
ORDER BY mf.file_id;
"""


def _q_counters(db: str) -> str:
    return f"""
SET NOCOUNT ON;
SELECT RTRIM(pc.counter_name) AS counter_name, pc.cntr_value
FROM sys.dm_os_performance_counters pc
WHERE pc.object_name LIKE N'%:Databases%'
  AND RTRIM(pc.instance_name) = N'{_esc(db)}'
  AND RTRIM(pc.counter_name) IN (N'Log File(s) Size (KB)', N'Log File(s) Used Size (KB)', N'Percent Log Used',
                                 N'Log Growths', N'Log Shrinks', N'Log Truncations', N'Log Bytes Flushed/sec', N'Active Transactions');
"""


_Q_LOGSPACE = "DBCC SQLPERF(LOGSPACE) WITH NO_INFOMSGS;"


def _q_log_stats(db: str) -> str:
    e = _esc(db)
    return f"""
SET NOCOUNT ON;
IF NOT EXISTS (SELECT 1 FROM sys.databases WITH (NOLOCK) WHERE name = N'{e}' AND state = 0)
    SELECT N'not_online' AS status, N'base nao esta ONLINE: dm_db_log_stats indisponivel' AS note;
ELSE IF HAS_DBACCESS(N'{e}') <> 1
    SELECT N'no_access' AS status, N'sem acesso a base (secundaria AG nao legivel ou sem user): dm_db_log_stats indisponivel' AS note;
ELSE
    SELECT N'ok' AS status, CAST(NULL AS NVARCHAR(200)) AS note,
           ls.recovery_model, ls.total_vlf_count, ls.active_vlf_count,
           ls.total_log_size_mb, ls.active_log_size_mb, ls.log_truncation_holdup_reason,
           ls.log_backup_time, ls.log_since_last_log_backup_mb, ls.log_since_last_checkpoint_mb, ls.log_recovery_size_mb
    FROM sys.dm_db_log_stats(DB_ID(N'{e}')) ls;
"""


def _q_log_info(db: str) -> str:
    e = _esc(db)
    return f"""
SET NOCOUNT ON;
IF NOT EXISTS (SELECT 1 FROM sys.databases WITH (NOLOCK) WHERE name = N'{e}' AND state = 0) OR HAS_DBACCESS(N'{e}') <> 1
    SELECT N'unavailable' AS status;
ELSE
    SELECT N'ok' AS status, COUNT(*) AS vlf_count,
           SUM(CASE WHEN li.vlf_active = 1 THEN 1 ELSE 0 END) AS active_vlf_count,
           CAST(MIN(li.vlf_size_mb) AS DECIMAL(18,2)) AS min_vlf_mb,
           CAST(MAX(li.vlf_size_mb) AS DECIMAL(18,2)) AS max_vlf_mb,
           SUM(CASE WHEN li.vlf_size_mb < 1 THEN 1 ELSE 0 END) AS vlfs_under_1mb,
           COUNT(DISTINCT li.vlf_create_lsn) AS growth_events_approx
    FROM sys.dm_db_log_info(DB_ID(N'{e}')) li;
"""


def _q_open_tran(db: str, has_input_buffer: bool) -> str:
    e = _esc(db)
    if has_input_buffer:
        batch = "OUTER APPLY sys.dm_exec_input_buffer(st.session_id, NULL) ib"
        batch_col = "LEFT(ib.event_info, 1000) AS last_batch"
    else:
        batch = ("OUTER APPLY (SELECT TOP (1) c.most_recent_sql_handle FROM sys.dm_exec_connections c "
                 "WHERE c.session_id = st.session_id AND c.most_recent_sql_handle IS NOT NULL) c "
                 "OUTER APPLY sys.dm_exec_sql_text(c.most_recent_sql_handle) t")
        batch_col = "LEFT(t.text, 1000) AS last_batch"
    return f"""
SET NOCOUNT ON;
SELECT TOP (10)
       st.session_id, s.login_name, s.host_name, s.program_name, s.status AS session_status,
       s.last_request_start_time, s.last_request_end_time,
       r.command AS request_command, r.status AS request_status, r.wait_type, r.blocking_session_id,
       dt.database_transaction_begin_time,
       DATEDIFF(MINUTE, dt.database_transaction_begin_time, GETDATE()) AS open_minutes,
       dt.database_transaction_state,
       CAST(dt.database_transaction_log_bytes_used / 1048576.0 AS DECIMAL(18,1)) AS log_used_mb,
       CAST(dt.database_transaction_log_bytes_reserved / 1048576.0 AS DECIMAL(18,1)) AS log_reserved_mb,
       dt.database_transaction_log_record_count AS log_record_count,
       st.is_user_transaction,
       {batch_col}
FROM sys.dm_tran_database_transactions dt
JOIN sys.dm_tran_session_transactions st ON st.transaction_id = dt.transaction_id
LEFT JOIN sys.dm_exec_sessions s ON s.session_id = st.session_id
LEFT JOIN sys.dm_exec_requests r ON r.session_id = st.session_id
{batch}
WHERE dt.database_id = DB_ID(N'{e}')
  AND dt.database_transaction_begin_time IS NOT NULL
  AND st.session_id <> @@SPID
ORDER BY dt.database_transaction_begin_time ASC;
"""


def _q_backups_3d(db: str) -> str:
    return f"""
SET NOCOUNT ON;
SELECT TOP (30)
       b.type AS backup_type, b.backup_start_date, b.backup_finish_date,
       DATEDIFF(SECOND, b.backup_start_date, b.backup_finish_date) AS duration_s,
       CAST(b.backup_size / 1048576.0 AS DECIMAL(18,1)) AS backup_size_mb,
       CAST(b.compressed_backup_size / 1048576.0 AS DECIMAL(18,1)) AS compressed_mb,
       b.is_copy_only, b.is_damaged, b.recovery_model, b.first_lsn, b.last_lsn,
       STUFF((SELECT N'; ' + f.physical_device_name FROM msdb.dbo.backupmediafamily f WITH (NOLOCK)
              WHERE f.media_set_id = b.media_set_id ORDER BY f.family_sequence_number
              FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'), 1, 2, N'') AS physical_device_names
FROM msdb.dbo.backupset b WITH (NOLOCK)
WHERE b.database_name = N'{_esc(db)}'
  AND b.backup_finish_date >= DATEADD(DAY, -3, GETDATE())
ORDER BY b.backup_finish_date DESC;
"""


def _q_backups_30d(db: str) -> str:
    return f"""
SET NOCOUNT ON;
SELECT b.type AS backup_type, CAST(b.backup_finish_date AS DATE) AS backup_day, COUNT(*) AS backups,
       CAST(SUM(b.backup_size) / 1048576.0 AS DECIMAL(18,1)) AS total_mb,
       CAST(MAX(b.backup_size) / 1048576.0 AS DECIMAL(18,1)) AS max_size_mb,
       MAX(b.backup_finish_date) AS last_finish,
       SUM(CASE WHEN b.is_copy_only = 1 THEN 1 ELSE 0 END) AS copy_only_count
FROM msdb.dbo.backupset b WITH (NOLOCK)
WHERE b.database_name = N'{_esc(db)}'
  AND b.backup_finish_date >= DATEADD(DAY, -30, GETDATE())
GROUP BY b.type, CAST(b.backup_finish_date AS DATE)
ORDER BY backup_day DESC, b.type;
"""


def _q_volumes(db: str) -> str:
    return f"""
SET NOCOUNT ON;
SELECT mf.file_id, mf.name AS logical_name, mf.physical_name,
       vs.volume_mount_point, vs.logical_volume_name,
       CAST(vs.total_bytes / 1073741824.0 AS DECIMAL(12,1)) AS volume_total_gb,
       CAST(vs.available_bytes / 1073741824.0 AS DECIMAL(12,1)) AS volume_free_gb,
       CAST(100.0 * vs.available_bytes / NULLIF(vs.total_bytes, 0) AS DECIMAL(5,1)) AS volume_free_pct,
       CAST(mf.size AS BIGINT) * 8 / 1024 AS log_size_mb,
       CASE WHEN mf.max_size IN (-1, 268435456) THEN CAST(vs.available_bytes / 1048576 AS BIGINT)
            ELSE CAST((SELECT MIN(v) FROM (VALUES (vs.available_bytes / 1048576),
                                                  ((CAST(mf.max_size AS BIGINT) - mf.size) * 8 / 1024)) x(v)) AS BIGINT)
       END AS log_headroom_mb,
       fs.num_of_writes AS log_writes_since_start,
       CAST(fs.num_of_bytes_written / 1048576.0 AS DECIMAL(18,1)) AS log_mb_written_since_start,
       CASE WHEN fs.num_of_writes > 0 THEN CAST(1.0 * fs.io_stall_write_ms / fs.num_of_writes AS DECIMAL(10,2)) END AS avg_write_latency_ms
FROM sys.master_files mf WITH (NOLOCK)
CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
OUTER APPLY sys.dm_io_virtual_file_stats(mf.database_id, mf.file_id) fs
WHERE mf.database_id = DB_ID(N'{_esc(db)}') AND mf.type = 1;
"""


def _q_ha(db: str) -> str:
    return f"""
SET NOCOUNT ON;
SELECT d.name AS database_name,
       m.mirroring_state_desc, m.mirroring_role_desc, m.mirroring_partner_instance,
       ag.name AS ag_name, ar.replica_server_name, ars.role_desc AS ag_role, ar.availability_mode_desc,
       drs.synchronization_state_desc, drs.synchronization_health_desc, drs.is_suspended, drs.suspend_reason_desc,
       drs.log_send_queue_size AS log_send_queue_kb, drs.redo_queue_size AS redo_queue_kb,
       (SELECT MAX(x.log_send_queue_size) FROM sys.dm_hadr_database_replica_states x
         WHERE x.group_database_id = d.group_database_id AND x.is_local = 0) AS max_remote_send_queue_kb,
       (SELECT COUNT(*) FROM sys.dm_hadr_database_replica_states x
         WHERE x.group_database_id = d.group_database_id AND x.is_local = 0
           AND (x.synchronization_state NOT IN (1, 2) OR x.is_suspended = 1)) AS unhealthy_remote_replicas
FROM sys.databases d WITH (NOLOCK)
LEFT JOIN sys.database_mirroring m WITH (NOLOCK) ON m.database_id = d.database_id AND m.mirroring_guid IS NOT NULL
LEFT JOIN sys.dm_hadr_database_replica_states drs ON drs.group_database_id = d.group_database_id AND drs.is_local = 1
LEFT JOIN sys.dm_hadr_availability_replica_states ars ON ars.replica_id = drs.replica_id
LEFT JOIN sys.availability_replicas ar ON ar.replica_id = drs.replica_id
LEFT JOIN sys.availability_groups ag ON ag.group_id = drs.group_id
WHERE d.name = N'{_esc(db)}';
"""


def _q_requests(db: str) -> str:
    return f"""
SET NOCOUNT ON;
SELECT r.session_id, r.command, r.status, r.percent_complete, r.start_time,
       r.total_elapsed_time / 1000 AS elapsed_s, r.estimated_completion_time / 1000 AS eta_s,
       r.wait_type, r.blocking_session_id, DB_NAME(r.database_id) AS context_db,
       s.login_name, s.host_name, s.program_name, LEFT(t.text, 500) AS statement_text
FROM sys.dm_exec_requests r
LEFT JOIN sys.dm_exec_sessions s ON s.session_id = r.session_id
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE r.session_id <> @@SPID
  AND ( r.command IN (N'BACKUP DATABASE', N'BACKUP LOG', N'RESTORE DATABASE', N'RESTORE LOG')
        OR (r.database_id = DB_ID(N'{_esc(db)}') AND r.command IN (N'DbccFilesCompact', N'DbccSpaceReclaim', N'DB STARTUP', N'ALTER DATABASE')) )
ORDER BY r.start_time;
"""


def _q_errorlog(db: str) -> str:
    # 9002 ocupa duas linhas: a segunda tem o nome da base entre apostrofes.
    return f"""
SET NOCOUNT ON;
DECLARE @from DATETIME = DATEADD(DAY, -7, GETDATE());
EXEC master.dbo.xp_readerrorlog 0, 1, N'''{_esc(db)}''', NULL, @from, NULL, N'desc';
"""


_ERR_PATTERNS = [
    (r"is full due to|cheio devido|lleno debido|\b9002\b", "9002"),
    (r"autogrow of file|auto.?grow", "5145"),
    (r"recovery of database|starting up database", "recovery"),
]


def _errorlog_rows(rows: List[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
    out = []
    for r in rows[:200]:
        text = _clean(r.get("Text") or r.get("text"))[:300]
        kind = next((k for pat, k in _ERR_PATTERNS if re.search(pat, text, re.I)), "")
        out.append({"when": str(r.get("LogDate") or r.get("logdate") or "")[:19], "text": text, "kind": kind})
    return out[:limit]


def _mentions_db(text: str, db: str) -> bool:
    if not text:
        return False
    e = re.escape(db)
    return re.search(rf"\[{e}\]|'{e}'|\"{e}\"|\b{e}\b", text, re.I) is not None


# ---------------------------------------------------------------- endpoint
@router.get("/tlog-diagnosis/{server_id}")
async def tlog_diagnosis(server_id: str, database: str = Query(...),
                         snapshot_pct: Optional[float] = Query(None), snapshot_ts: Optional[str] = Query(None),
                         snapshot_age: Optional[str] = Query(None)) -> Dict[str, Any]:
    if not _DBNAME.match(database or ""):
        raise HTTPException(status_code=400, detail="database invalido")
    # chamada directa (testes) traz os defaults como objectos Query — normalizar
    snapshot_pct = snapshot_pct if isinstance(snapshot_pct, (int, float)) else None
    snapshot_ts = snapshot_ts if isinstance(snapshot_ts, str) else None
    snapshot_age = snapshot_age if isinstance(snapshot_age, str) else None
    notes: List[str] = []
    sid = _sid(server_id)
    out: Dict[str, Any] = {"success": True, "server_id": sid, "database": database, "notes": notes, "sources": []}

    tl_warn = float(_th("tlog_usage", "warning"))
    tl_crit = float(_th("tlog_usage", "critical"))
    lb_warn = float(_th("backup_delay_log", "warning"))
    lb_crit = float(_th("backup_delay_log", "critical"))

    # ---- q0 capacidades ----
    caps_rows = await _try(sid, _Q_CAPS, notes, "capacidades (SERVERPROPERTY)", _TO["fast"])
    caps = caps_rows[0] if caps_rows else {}
    now = _dt(caps.get("server_now")) or datetime.now()
    has_log_stats = int(_n(caps.get("has_log_stats"), 0) or 0) == 1
    has_log_info = int(_n(caps.get("has_log_info"), 0) or 0) == 1
    has_input_buffer = int(_n(caps.get("has_input_buffer"), 0) or 0) == 1
    uptime_h = _n(caps.get("uptime_hours"))
    display_inst = _clean(caps.get("server_name")) or server_id  # @@SERVERNAME (com barra), nao o server_id do pool

    # ---- q1 estado + ficheiros de log ----
    st_rows = await _try(sid, _q_state(database), notes, "estado (sys.databases/master_files)", _TO["fast"])
    st = st_rows[0] if st_rows else {}
    if not st_rows:
        notes.append(f"base '{database}' nao encontrada em sys.databases desta instancia")
    else:
        out["sources"].append("sys.databases")
    db_name = str(st.get("database_name") or database)  # nome canonico (collation CS)
    log_files = [r for r in st_rows if r.get("log_logical_name")]
    recovery = (st.get("recovery_model_desc") or "").upper()
    lrw = (st.get("log_reuse_wait_desc") or "").upper()
    state_desc = (st.get("state_desc") or "").upper()
    has_access = int(_n(st.get("has_db_access"), 1) or 0) == 1
    log_size_mb = sum((_n(r.get("log_size_mb"), 0) or 0) for r in log_files) or None
    data_size_mb = _n(st.get("data_size_mb"))
    first_log = log_files[0] if log_files else {}

    # ---- q2 contadores (fallback SQLPERF) ----
    ctr_rows = await _try(sid, _q_counters(db_name), notes, "contadores Databases", _TO["fast"])
    counters = {str(r.get("counter_name")): _n(r.get("cntr_value")) for r in ctr_rows}
    used_mb = (counters.get("Log File(s) Used Size (KB)") or 0) / 1024 if counters else None
    size_kb = counters.get("Log File(s) Size (KB)") if counters else None
    if size_kb and log_size_mb is None:
        log_size_mb = size_kb / 1024
    used_pct = (100.0 * used_mb / (size_kb / 1024)) if (size_kb and used_mb is not None) else None
    logspace_row = None
    if used_pct is None:
        ls_rows = await _try(sid, _Q_LOGSPACE, notes, "DBCC SQLPERF(LOGSPACE)", _TO["mid"])
        for r in ls_rows:
            if str(r.get("Database Name") or r.get("database_name") or "") == db_name:
                logspace_row = r
                used_pct = _n(r.get("Log Space Used (%)"))
                if log_size_mb is None:
                    log_size_mb = _n(r.get("Log Size (MB)"))
                if used_pct is not None and log_size_mb:
                    used_mb = log_size_mb * used_pct / 100.0
                break
        if ls_rows:
            out["sources"].append("DBCC SQLPERF(LOGSPACE)")
    elif ctr_rows:
        out["sources"].append("dm_os_performance_counters")
    log_growths = counters.get("Log Growths")

    # ---- q3 VLFs / log desde ultimo backup (2016 SP2+) ----
    log_stats: Dict[str, Any] = {}
    vlf_info: Dict[str, Any] = {}
    if has_log_stats:
        r3 = await _try(sid, _q_log_stats(db_name), notes, "dm_db_log_stats", _TO["mid"])
        if r3 and str(r3[0].get("status")) == "ok":
            log_stats = r3[0]
            out["sources"].append("dm_db_log_stats")
        elif r3:
            notes.append(f"dm_db_log_stats: {r3[0].get('note') or r3[0].get('status')}")
        if has_log_info:
            r3b = await _try(sid, _q_log_info(db_name), notes, "dm_db_log_info", _TO["mid"])
            if r3b and str(r3b[0].get("status")) == "ok":
                vlf_info = r3b[0]
    else:
        notes.append(f"VLFs: requer SQL 2016 SP2+ (dm_db_log_stats); em {caps.get('product_version') or 'versao desconhecida'} so' DBCC LOGINFO (db_owner) — correr no SSMS")

    # ---- q4 transacoes abertas ----
    otr = await _try(sid, _q_open_tran(db_name, has_input_buffer), notes, "transacoes abertas (dm_tran_*)", _TO["mid"])
    for r in otr:
        r["last_batch"] = _clean(r.get("last_batch"))
    if otr:
        out["sources"].append("dm_tran_database_transactions")

    # ---- q5 backups (msdb) ----
    bk3 = await _try(sid, _q_backups_3d(db_name), notes, "backups 3d (msdb)", _TO["msdb"])
    bk30 = await _try(sid, _q_backups_30d(db_name), notes, "backups 30d (msdb)", _TO["msdb"])
    if bk3 or bk30:
        out["sources"].append("msdb.dbo.backupset")

    # ---- q6 volumes / q7 HA / q8 requests ----
    vols = await _try(sid, _q_volumes(db_name), notes, "volume do log (dm_os_volume_stats)", _TO["fast"])
    ha_rows = await _try(sid, _q_ha(db_name), notes, "HA (mirroring/AG)", _TO["fast"])
    ha = ha_rows[0] if ha_rows else {}
    reqs_all = await _try(sid, _q_requests(db_name), notes, "backup/restore em curso (dm_exec_requests)", _TO["fast"])
    reqs = [r for r in reqs_all if _mentions_db(str(r.get("statement_text") or ""), db_name)
            or str(r.get("context_db") or "") == db_name and str(r.get("command") or "").startswith(("Dbcc", "DB STARTUP", "ALTER"))]

    # ---- q9 errorlog (ULTIMO, timeout proprio; sem GRANT falha com 229 -> nota) ----
    el_rows = await _try(sid, _q_errorlog(db_name), notes, "errorlog (xp_readerrorlog)", _TO["errorlog"])
    errorlog = _errorlog_rows(el_rows)
    if el_rows:
        out["sources"].append("xp_readerrorlog")

    # ---------------------------------------------------------------- derivadas
    by_type: Dict[str, Dict[str, Any]] = {}
    log_per_day: List[Dict[str, Any]] = []
    daily_mb = None
    days_with_log = 0
    max_log_bkp_mb = None
    cutoff7 = (now - timedelta(days=7)).date()
    for r in bk30:
        t = str(r.get("backup_type") or "").upper()
        agg = by_type.setdefault(t, {"backups": 0, "total_mb": 0.0, "max_mb": 0.0, "last": None})
        agg["backups"] += int(_n(r.get("backups"), 0) or 0)
        agg["total_mb"] += _n(r.get("total_mb"), 0) or 0
        agg["max_mb"] = max(agg["max_mb"], _n(r.get("max_size_mb"), 0) or 0)
        lf = _dt(r.get("last_finish"))
        if lf and (agg["last"] is None or lf > agg["last"]):
            agg["last"] = lf
        if t == "L":
            day = _dt(r.get("backup_day")) or (datetime.strptime(str(r.get("backup_day"))[:10], "%Y-%m-%d") if r.get("backup_day") else None)
            if day and day.date() >= cutoff7:
                log_per_day.append({"backup_day": str(r.get("backup_day"))[:10], "backups": int(_n(r.get("backups"), 0) or 0), "total_mb": _n(r.get("total_mb"), 0) or 0})
    if by_type.get("L"):
        max_log_bkp_mb = by_type["L"]["max_mb"] or None
    if log_per_day:
        days_with_log = len({d["backup_day"] for d in log_per_day})
        daily_mb = sum(d["total_mb"] for d in log_per_day) / 7.0
    daily_mb_io = None
    if vols and uptime_h and uptime_h > 0:
        written = sum((_n(v.get("log_mb_written_since_start"), 0) or 0) for v in vols)
        if written > 0:
            daily_mb_io = written / uptime_h * 24.0

    last_log = _dt(log_stats.get("log_backup_time")) or (by_type.get("L", {}).get("last"))
    last_full = by_type.get("D", {}).get("last")
    hours_since_log = ((now - last_log).total_seconds() / 3600.0) if last_log else None
    log_needs_backup = recovery in ("FULL", "BULK_LOGGED")

    if max_log_bkp_mb:
        alvo_mb = max(max_log_bkp_mb * 2, LOG_MIN_MB)
    else:
        alvo_mb = max((data_size_mb or 0) * 0.10, LOG_MIN_MB)
    alvo_mb = math.ceil(alvo_mb / 512.0) * 512
    potencial_mb = (log_size_mb - alvo_mb) if (log_size_mb and alvo_mb and log_size_mb > alvo_mb * 1.5) else 0

    vol0 = vols[0] if vols else {}
    headroom_mb = _n(vol0.get("log_headroom_mb"))
    vol_free_gb = _n(vol0.get("volume_free_gb"))
    vol_free_pct = _n(vol0.get("volume_free_pct"))
    runway_days = None
    if headroom_mb is not None and daily_mb and daily_mb > 0:
        runway_days = round(headroom_mb / daily_mb, 1)
    # Capacidade EFECTIVA (owner 02/09): margem ja e' MIN(disco livre, max_size - size)
    effective_limit_mb = (log_size_mb + headroom_mb) if (log_size_mb and headroom_mb is not None) else None
    effective_pct = (100.0 * used_mb / effective_limit_mb) if (effective_limit_mb and used_mb is not None) else None

    vlf_total = _n(log_stats.get("total_vlf_count")) or _n(vlf_info.get("vlf_count"))
    vlf_active = _n(log_stats.get("active_vlf_count")) or _n(vlf_info.get("active_vlf_count"))

    oldest = otr[0] if otr else {}
    tran_min = _n(oldest.get("open_minutes"))
    tran_sid = _i(oldest.get("session_id"), "?") if oldest else "?"
    tran_log_mb = sum((_n(r.get("log_reserved_mb"), 0) or 0) for r in otr) if otr else 0
    tran_orphan = bool(oldest) and str(oldest.get("session_status") or "").lower() == "sleeping" and not oldest.get("request_command")

    growth_bad_files = [f for f in log_files if int(_n(f.get("is_percent_growth"), 0) or 0) == 1
                        or (int(_n(f.get("log_growth_disabled"), 0) or 0) == 0 and (_n(f.get("log_growth_value"), 0) or 0) < GROWTH_MIN_MB)]
    growth_disabled = [f for f in log_files if int(_n(f.get("log_growth_disabled"), 0) or 0) == 1]

    ag_name = ha.get("ag_name")
    ag_role = (ha.get("ag_role") or "").upper()
    mstate = (ha.get("mirroring_state_desc") or "").upper()
    send_q_kb = _n(ha.get("max_remote_send_queue_kb")) or _n(ha.get("log_send_queue_kb"))
    unhealthy_replicas = int(_n(ha.get("unhealthy_remote_replicas"), 0) or 0)

    el_9002 = [e for e in errorlog if e.get("kind") == "9002"]
    el_autogrow = [e for e in errorlog if e.get("kind") == "5145"]
    n9002 = len(el_9002)

    # ---------------------------------------------------------------- findings
    problems: List[Dict[str, Any]] = []
    recs: List[Dict[str, Any]] = []
    ts = now.isoformat(timespec="minutes")
    db_q = f"[{db_name.replace(']', ']]')}]"
    log_logical = str(first_log.get("log_logical_name") or "<log_logical_name>")
    log_logical_q = log_logical.replace("'", "''")
    rec_ids_added = set()

    def prob(id_, title, evidence, impact, sev, icon, source="dmv", conf="measured", rec_ids=None, summary=None):
        problems.append({"id": id_, "title": title, "evidence": evidence, "summary": summary or "", "impact": impact, "icon": icon,
                         "severity": sev, "source": source, "confidence": conf, "ts": ts, "recIds": rec_ids or []})

    def rec(id_, title, desc, impact, effort, problem_ids, icon, sql=None):
        if id_ in rec_ids_added:
            for r in recs:
                if r["id"] == id_:
                    r["problemIds"] = sorted(set(r["problemIds"]) | set(problem_ids))
            return
        rec_ids_added.add(id_)
        r = {"id": id_, "title": title, "desc": desc, "impact": impact, "effort": effort, "problemIds": list(problem_ids), "icon": icon}
        if sql:
            r["sqlCheck"] = sql
        recs.append(r)

    pct_txt = f"{_num(used_pct, 1)}% do log usado" if used_pct is not None else "% de log não disponível"
    size_txt = f" ({_gb(used_mb)} / {_gb(log_size_mb)})" if log_size_mb else ""
    h_txt = _num(hours_since_log, 1) if hours_since_log is not None else "?"

    # 1) Cadeia de backup (a causa n.1 de log que nunca trunca em FULL)
    chain_state = None  # never | late | ok | simple | unknown
    if not log_needs_backup and recovery:
        chain_state = "simple"
    elif log_needs_backup:
        if last_log is None:
            if ag_name and not bk30 and not log_stats:
                chain_state = "unknown"
                prob("chain_unknown", "Backup de log não visível nesta réplica AG",
                     f"msdb desta réplica sem backups de {db_name} nos últimos 30 dias e dm_db_log_stats indisponível — o backup de log pode correr noutra réplica (backup preference)",
                     "Sem confirmar a cadeia não se sabe se o log vai truncar", "warning", "fa-question-circle", conf="heuristic", rec_ids=["rec_log_backup"],
                     summary="Backup de log pode correr noutra réplica do AG")
            else:
                chain_state = "never"
                prob("chain_stopped", f"Recovery {recovery} sem nenhum backup de log registado",
                     f"msdb: 0 backups tipo L em 30 dias; {pct_txt}{size_txt}" + (f"; log_reuse_wait = {lrw}" if lrw else ""),
                     "Em FULL o log NUNCA trunca sem backup de log — cresce até encher o disco e parar a aplicação (9002)",
                     "critical", "fa-unlink", source="history", rec_ids=["rec_log_backup"], summary="msdb: 0 backups de log em 30 dias")
        elif hours_since_log is not None and hours_since_log > lb_crit:
            chain_state = "late"
            prob("chain_stopped", f"Backup de log parado há {h_txt} h",
                 f"último backup de log {_fmt_dt_full(last_log)} (limiar crítico {lb_crit:g} h); {pct_txt}{size_txt}",
                 "Enquanto o job não corre o log não trunca: cresce e o RPO afasta-se", "critical", "fa-unlink", source="history", rec_ids=["rec_log_backup"],
                 summary=f"Último backup: {_fmt_dt_full(last_log)}")
        elif hours_since_log is not None and hours_since_log > lb_warn:
            chain_state = "late"
            prob("chain_late", f"Backup de log atrasado ({h_txt} h)",
                 f"último backup de log {_fmt_dt_full(last_log)} (limiar {lb_warn:g} h)", "Ainda não crítico; se o job falhou de vez vira o problema n.1",
                 "warning", "fa-clock", source="history", rec_ids=["rec_log_backup"], summary=f"Último backup: {_fmt_dt_full(last_log)}")
        else:
            chain_state = "ok"
        if last_full is None and not ag_name and bk30 is not None and not by_type.get("D"):
            prob("no_full", f"Recovery {recovery} sem full backup nos últimos 30 dias",
                 "msdb: 0 backups tipo D em 30 dias — sem full não há cadeia e o BACKUP LOG falha",
                 "Sem ponto de partida para restore; log backup não funciona", "critical", "fa-database", source="history", rec_ids=["rec_full"],
                 summary="msdb: 0 full backups em 30 dias")
            rec("rec_full", "Criar full backup (cadeia inexistente)", "Sem FULL o backup de log falha; confirmar política/TSM.",
                "very_high", "low", ["no_full"], "fa-database",
                f"-- comentado; o WatcherDB nao executa:\n-- BACKUP DATABASE {db_q} TO DISK = N'<path>\\{db_name}_full.bak' WITH CHECKSUM, COMPRESSION;\nSELECT TOP 5 type, backup_finish_date, backup_size/1048576 AS mb FROM msdb.dbo.backupset WHERE database_name = N'{_esc(db_name)}' ORDER BY backup_finish_date DESC;")
    if chain_state in ("never", "late", "unknown"):
        rec("rec_log_backup", "Verificar / religar backup de log",
            (f"A cadeia de backup está parada há {h_txt} h." if last_log is not None else "Sem nenhum backup de log registado; sem ele o log nunca trunca em FULL."),
            "very_high", "low", ["chain_stopped", "chain_late", "chain_unknown"], "fa-history",
            f"SELECT TOP 10 type, backup_start_date, backup_finish_date, backup_size/1048576 AS mb, is_copy_only FROM msdb.dbo.backupset WHERE database_name = N'{_esc(db_name)}' ORDER BY backup_finish_date DESC;\nSELECT j.name, j.enabled, h.run_date, h.run_status FROM msdb.dbo.sysjobs j LEFT JOIN msdb.dbo.sysjobhistory h ON h.job_id = j.job_id AND h.step_id = 0 WHERE j.name LIKE N'%log%' ORDER BY h.run_date DESC;\n-- teste manual (comentado; decisao humana):\n-- BACKUP LOG {db_q} TO DISK = N'<path>\\{db_name}_log_manual.trn' WITH CHECKSUM, COMPRESSION;")
        if chain_state == "late":
            rec("rec_log_backup_now", "Executar backup de log (manual, se apropriado)", "Pode permitir o truncamento do log e recuperar espaço.",
                "high", "low", ["chain_stopped", "chain_late"], "fa-upload",
                f"-- comentado; decisao humana (destino e retencao conforme a politica):\n-- BACKUP LOG {db_q} TO DISK = N'<path>\\{db_name}_log_manual.trn' WITH CHECKSUM, COMPRESSION;\nSELECT name, log_reuse_wait_desc FROM sys.databases WHERE name = N'{_esc(db_name)}';")

    # 2) Causa de retencao anormal (log_reuse_wait fora de NOTHING/LOG_BACKUP/CHECKPOINT)
    if lrw and lrw not in _RETAINED_OK:
        text, rec_id = _REASON_TEXT.get(lrw, (f"Retenção {lrw}", "rec_recheck"))
        extra = ""
        if lrw == "ACTIVE_TRANSACTION" and oldest:
            extra = f" · sessão {tran_sid} ({oldest.get('login_name') or '?'} / {oldest.get('program_name') or '?'}) há {_num(tran_min, 0)} min, {_gb(tran_log_mb)} de log reservado" if tran_min is not None else ""
        if lrw in ("DATABASE_MIRRORING", "AVAILABILITY_REPLICA") and send_q_kb is not None:
            extra = f" · fila de envio {_gb(send_q_kb / 1024)}" + (f", {unhealthy_replicas} réplica(s) não saudável(is)" if unhealthy_replicas else "")
        prob("log_not_truncating", f"Log não trunca: {text}",
             f"log_reuse_wait_desc = {lrw}{extra} · {pct_txt}{size_txt}",
             "Backup de log ou shrink NÃO resolvem enquanto a causa persistir — é o relógio a correr", "critical", "fa-fire", rec_ids=[rec_id],
             summary=f"log_reuse_wait_desc = {lrw}")
    elif lrw == "LOG_BACKUP" and chain_state == "ok" and (used_pct or 0) > tl_warn:
        prob("waiting_log_backup", "A aguardar o próximo backup de log",
             f"log_reuse_wait_desc = LOG_BACKUP · último backup de log {_fmt_dt_full(last_log)} · {pct_txt}{size_txt}",
             "Normal em FULL entre backups; se a % não descer após o próximo backup, o log está subdimensionado ou há pico (reindex)", "info", "fa-hourglass-half", rec_ids=["rec_log_backup_freq"],
             summary=f"Último backup: {_fmt_dt_full(last_log)}")
        rec("rec_log_backup_freq", "Encurtar o intervalo do backup de log", "Ou aceitar o tamanho de trabalho e não encolher.",
            "medium", "low", ["waiting_log_backup"], "fa-stopwatch",
            f"SELECT CAST(backup_finish_date AS DATE) dia, COUNT(*) backups, SUM(backup_size)/1048576 AS log_mb FROM msdb.dbo.backupset WHERE database_name = N'{_esc(db_name)}' AND type = 'L' AND backup_finish_date >= DATEADD(DAY,-7,GETDATE()) GROUP BY CAST(backup_finish_date AS DATE) ORDER BY dia DESC;")

    # 2a) Transacao aberta
    if tran_min is not None and tran_min >= TRAN_MIN_WARN:
        sev = "critical" if tran_min >= TRAN_MIN_CRIT else "warning"
        who = f"sessão {tran_sid} · {oldest.get('login_name') or '?'} @ {oldest.get('host_name') or '?'} · {oldest.get('program_name') or '?'}"
        prob("open_tran", f"Transação aberta há {_num(tran_min, 0)} min" + (" (sessão adormecida — provável órfã)" if tran_orphan else ""),
             f"{who} · {_gb(tran_log_mb)} de log reservado por {len(otr)} transação(ões) · último batch: {str(oldest.get('last_batch') or '')[:120]}",
             "Tudo o que está atrás dela no log fica preso — backup de log não liberta", sev, "fa-user-clock", rec_ids=["rec_open_tran"],
             summary=f"Sessão {tran_sid} ({oldest.get('login_name') or '?'}) · {_gb(tran_log_mb)} de log")
    if lrw == "ACTIVE_TRANSACTION" or (tran_min is not None and tran_min >= TRAN_MIN_WARN):
        rec("rec_open_tran", "Investigar a sessão que retém o log",
            f"Sessão {tran_sid} ({oldest.get('login_name') or '?'}) aberta há {_num(tran_min, 0) if tran_min is not None else '?'} min; KILL é decisão humana com o dono da aplicação.",
            "very_high", "low", ["open_tran", "log_not_truncating"], "fa-user-clock",
            f"SELECT st.session_id, s.login_name, s.host_name, s.program_name, s.status, dt.database_transaction_begin_time,\n       DATEDIFF(MINUTE, dt.database_transaction_begin_time, GETDATE()) AS minutos, dt.database_transaction_log_bytes_reserved/1048576 AS log_mb\nFROM sys.dm_tran_database_transactions dt JOIN sys.dm_tran_session_transactions st ON st.transaction_id = dt.transaction_id\nLEFT JOIN sys.dm_exec_sessions s ON s.session_id = st.session_id\nWHERE dt.database_id = DB_ID(N'{_esc(db_name)}') AND dt.database_transaction_begin_time IS NOT NULL ORDER BY dt.database_transaction_begin_time;\n-- DBCC INPUTBUFFER({tran_sid if tran_sid != '?' else '<spid>'});\n-- KILL {tran_sid if tran_sid != '?' else '<spid>'};   -- SO com aval do dono da aplicacao (rollback pode ser longo)")

    # 2b) Replica (AG/mirroring) a reter
    if lrw in ("DATABASE_MIRRORING", "AVAILABILITY_REPLICA") or unhealthy_replicas or mstate in ("SUSPENDED", "DISCONNECTED"):
        rec("rec_replica", "Resolver a réplica (Mirroring/AG)", "O log só trunca quando a réplica confirmar o recebimento; usar o drill de Mirroring/AG.",
            "very_high", "low", ["log_not_truncating", "replica_holding"], "fa-sync-alt",
            f"SELECT DB_NAME(database_id) db, mirroring_state_desc, mirroring_role_desc FROM sys.database_mirroring WHERE database_id = DB_ID(N'{_esc(db_name)}') AND mirroring_guid IS NOT NULL;\nSELECT ar.replica_server_name, drs.synchronization_state_desc, drs.is_suspended, drs.suspend_reason_desc, drs.log_send_queue_size, drs.redo_queue_size\nFROM sys.dm_hadr_database_replica_states drs JOIN sys.availability_replicas ar ON ar.replica_id = drs.replica_id WHERE drs.database_id = DB_ID(N'{_esc(db_name)}');")
        if lrw not in ("DATABASE_MIRRORING", "AVAILABILITY_REPLICA") and (unhealthy_replicas or mstate in ("SUSPENDED", "DISCONNECTED")):
            prob("replica_holding", "Réplica não saudável (vai passar a reter o log)",
                 (f"AG {ag_name}: {unhealthy_replicas} réplica(s) remota(s) não saudável(is), fila {_gb(send_q_kb / 1024) if send_q_kb is not None else 'n/d'}" if ag_name else f"Mirroring {mstate}"),
                 "Quando a fila crescer o log_reuse_wait passa a AVAILABILITY_REPLICA/DATABASE_MIRRORING", "warning", "fa-sync-alt", rec_ids=["rec_replica"],
                 summary=(f"AG {ag_name}: {unhealthy_replicas} réplica(s) não saudável(is)" if ag_name else f"Mirroring {mstate}"))
    if lrw == "REPLICATION":
        rec("rec_replication", "Verificar Log Reader Agent / CDC", "O log só trunca depois de lido pela replicação/CDC; sp_repldone é último recurso do time de replicação.",
            "very_high", "medium", ["log_not_truncating"], "fa-exchange-alt",
            f"SELECT name, is_published, is_subscribed, is_cdc_enabled FROM sys.databases WHERE name = N'{_esc(db_name)}';\nSELECT * FROM sys.dm_cdc_log_scan_sessions;  -- CDC\n-- Log Reader Agent: msdb.dbo.sysjobs (categoria REPL-LogReader) / distribution.dbo.MSlogreader_history\n-- EXEC sp_repldone @xactid = NULL, @xact_seqno = NULL, @numtrans = 0, @time = 0, @reset = 1;  -- ULTIMO RECURSO, comentado")
    if lrw == "ACTIVE_BACKUP_OR_RESTORE":
        rec("rec_wait_backup", "Esperar o backup/restore terminar", "Enquanto corre o log não trunca; se durar horas, ver destino/rede do backup.",
            "medium", "low", ["log_not_truncating", "backup_in_progress"], "fa-hourglass-half",
            "SELECT session_id, command, percent_complete, start_time, estimated_completion_time/60000 AS eta_min FROM sys.dm_exec_requests WHERE command LIKE 'BACKUP%' OR command LIKE 'RESTORE%';")
    if lrw in ("OLDEST_PAGE", "XTP_CHECKPOINT"):
        rec("rec_checkpoint", "Verificar / forçar checkpoint", "Com indirect checkpoint/In-Memory OLTP o log só trunca após o checkpoint (decisão humana).",
            "high", "low", ["log_not_truncating"], "fa-flag-checkered",
            f"SELECT name, target_recovery_time_in_seconds, log_reuse_wait_desc FROM sys.databases WHERE name = N'{_esc(db_name)}';\n-- USE {db_q}; CHECKPOINT;   -- comentado")
    if lrw in ("LOG_SCAN", "OTHER_TRANSIENT") or (lrw and lrw not in _RETAINED_OK and lrw not in _REASON_TEXT):
        rec("rec_recheck", "Reavaliar em alguns minutos", "Motivo transitório/desconhecido; se persistir, ver o errorlog e o estado da base.",
            "low", "low", ["log_not_truncating"], "fa-redo", f"SELECT name, state_desc, log_reuse_wait_desc FROM sys.databases WHERE name = N'{_esc(db_name)}';")

    # 3) Uso do log (registry) — graduado pela capacidade EFECTIVA
    if used_pct is not None and used_pct > tl_warn:
        file_crit = used_pct > tl_crit
        no_room = (headroom_mb is not None and headroom_mb < HEADROOM_MIN_MB) or bool(growth_disabled)
        eff_crit = effective_pct is not None and effective_pct > tl_crit
        if effective_pct is None:
            sev = "critical" if file_crit else "warning"
            eff_txt = "limite efetivo n/d (volume não lido)"
        elif eff_crit or no_room:
            sev = "critical"
            eff_txt = f"limite efetivo a {_num(effective_pct, 0)}% ({_gb(effective_limit_mb)})" + (" · autogrow DESLIGADO" if growth_disabled else (f" · margem {_mb(headroom_mb)}" if no_room else ""))
        else:
            sev = "warning"
            eff_txt = f"limite efetivo a {_num(effective_pct, 0)}% ({_gb(effective_limit_mb)} = ficheiro + {_gb(headroom_mb)} de margem)"
        growth_txt_p = (f"+{_mb(first_log.get('log_growth_value'))}" if first_log and int(_n(first_log.get("is_percent_growth"), 0) or 0) == 0 else (f"+{first_log.get('log_growth_value'):g}%" if first_log else "?"))
        prob("log_usage", f"Log com {_num(used_pct, 1)}% de uso",
             f"{_gb(used_mb)} usados de {_gb(log_size_mb)} · {eff_txt}" + (f" · max_size {_gb(first_log.get('log_max_size_mb'))}" if first_log.get("log_max_size_mb") else " · max_size ilimitado (tecto = disco)"),
             ("Quando chegar a 100% e não puder crescer: 9002, a aplicação para" if sev == "critical"
              else f"A próxima escrita dispara um autogrow ({growth_txt_p}) que bloqueia escritas enquanto zera o ficheiro; o disco ainda aguenta"),
             sev, "fa-database",
             rec_ids=[r for r in (["rec_log_backup"] if chain_state in ("never", "late") else []) + (["rec_open_tran"] if lrw == "ACTIVE_TRANSACTION" else []) + (["rec_disk"] if no_room else []) + (["rec_growth"] if growth_disabled else [])],
             summary=f"{_gb(used_mb)} usados de {_gb(log_size_mb)}" + (f" · {_num(effective_pct, 0)}% do limite efetivo" if effective_pct is not None else ""))

    # 4) Disco / runway
    if headroom_mb is not None and headroom_mb < HEADROOM_MIN_MB:
        sev = "critical" if (used_pct or 0) > tl_warn else "warning"
        prob("drive_low", f"Margem de crescimento do log: {_mb(headroom_mb)}",
             f"volume {vol0.get('volume_mount_point')} com {_num(vol_free_gb, 1)} GB livres ({_num(vol_free_pct, 1)}%)" + (" · limitado por max_size" if first_log.get("log_max_size_mb") else ""),
             "Sem margem o próximo autogrow falha (9002) — mais urgente que tudo o resto", sev, "fa-hdd", rec_ids=["rec_disk"],
             summary=f"{_num(vol_free_gb, 1)} GB livres em {vol0.get('volume_mount_point')}")
    if runway_days is not None and runway_days <= RUNWAY_DAYS_WARN:
        sev = "critical" if runway_days <= RUNWAY_DAYS_CRIT else "warning"
        gap_note = f" (estimativa pode estar subavaliada: {days_with_log} de 7 dias com backup de log)" if days_with_log < 6 else ""
        prob("runway", f"Runway estimado: ~{_num(runway_days, 1)} dias",
             f"margem {_mb(headroom_mb)} / geração {_mb(daily_mb)} por dia (média 7d via msdb){gap_note}" + (f" · IO do ficheiro sugere {_mb(daily_mb_io)}/dia" if daily_mb_io else ""),
             "É a previsão que transforma estado em ação: DRIVE_ENCHE é acionável, '99% usado' sozinho não é", sev, "fa-chart-line", conf="heuristic", rec_ids=["rec_disk"],
             summary=f"Com base na geração atual de ~{_num(daily_mb / 24.0, 0)} MB/h")
    if (headroom_mb is not None and headroom_mb < HEADROOM_MIN_MB) or (runway_days is not None and runway_days <= RUNWAY_DAYS_WARN):
        rec("rec_disk", "Garantir espaço no volume do log", "Libertar/expandir o volume, ou ficheiro de log temporário noutro volume (remover depois).",
            "very_high", "low", ["drive_low", "runway", "log_usage"], "fa-hdd",
            f"SELECT mf.name, vs.volume_mount_point, vs.available_bytes/1073741824.0 AS free_gb, vs.total_bytes/1073741824.0 AS total_gb\nFROM sys.master_files mf CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs WHERE mf.database_id = DB_ID(N'{_esc(db_name)}') AND mf.type = 1;\n-- temporario (comentado): ALTER DATABASE {db_q} ADD LOG FILE (NAME = N'{log_logical_q}_tmp', FILENAME = N'<outro_volume>\\{db_name}_log_tmp.ldf', SIZE = 4096MB, FILEGROWTH = 512MB);")

    # 5) Log muito acima do alvo (so' faz sentido quando nada retem)
    if log_size_mb and alvo_mb and lrw in _RETAINED_OK and potencial_mb > 0:
        ratio = log_size_mb / alvo_mb
        if ratio > TARGET_X_WARN:
            sev = "warning" if ratio > TARGET_X_CRIT else "info"
            prob("log_vs_target", f"Log {ratio:.0f}x maior que o tamanho de trabalho",
                 f"log {_gb(log_size_mb)} vs alvo {_gb(alvo_mb)} (2x o maior backup de log em 30d = {_gb(max_log_bkp_mb or 0)}, piso {LOG_MIN_MB} MB)" + (" · alvo por 10% dos dados (sem log backups em 30d)" if not max_log_bkp_mb else ""),
                 f"Shrink libertaria ~{_gb(potencial_mb)} — só depois de garantir que nada retém", sev, "fa-compress-arrows-alt", conf="heuristic", rec_ids=["rec_shrink"],
                 summary=f"log {_gb(log_size_mb)} vs alvo {_gb(alvo_mb)}")
            rec("rec_shrink", f"Shrink até ao alvo ({_gb(alvo_mb)})", "Só depois de um backup de log e com nada a reter; nunca abaixo do tamanho de trabalho.",
                "medium", "low", ["log_vs_target"], "fa-compress-arrows-alt",
                f"DBCC SQLPERF(LOGSPACE);\n-- comentado; decisao humana, em janela:\n-- BACKUP LOG {db_q} TO DISK = N'<path>\\{db_name}_log.trn' WITH CHECKSUM, COMPRESSION;\n-- USE {db_q}; DBCC SHRINKFILE (N'{log_logical_q}', {int(alvo_mb)});")

    # 6) VLFs / growth / autogrow
    if vlf_total is not None and vlf_total > VLF_WARN:
        prob("vlf_high", f"{_i(vlf_total)} VLFs ({_i(vlf_active or 0)} ativos)",
             "dm_db_log_stats/dm_db_log_info" + (f" · {_i(vlf_info.get('vlfs_under_1mb') or 0)} VLFs < 1 MB (assinatura de autogrow pequeno/percentual)" if vlf_info else ""),
             "VLFs a mais atrasam recovery/restore e backups de log", "warning", "fa-layer-group", rec_ids=["rec_vlf", "rec_growth"],
             summary=f"{_i(vlf_active or 0)} ativos de {_i(vlf_total)}")
        rec("rec_vlf", "Reconstruir o log com poucos VLFs", "Shrink + regrowth em passos de 4–8 GB, em janela, depois de resolver a causa.",
            "medium", "medium", ["vlf_high"], "fa-layer-group",
            f"-- comentado; em janela:\n-- USE {db_q}; DBCC SHRINKFILE (N'{log_logical_q}', 512);\n-- ALTER DATABASE {db_q} MODIFY FILE (NAME = N'{log_logical_q}', SIZE = 4096MB);\n-- ALTER DATABASE {db_q} MODIFY FILE (NAME = N'{log_logical_q}', SIZE = 8192MB);  -- repetir ate ao alvo")
    if growth_disabled:
        prob("growth_disabled", "Autogrow do log DESLIGADO", f"{', '.join(str(f.get('log_logical_name')) for f in growth_disabled)}: growth = 0",
             "Quando encher não cresce: 9002 imediato", "critical" if (used_pct or 0) > tl_warn else "warning", "fa-ban", rec_ids=["rec_growth"],
             summary="growth = 0 no ficheiro de log")
    if growth_bad_files:
        f0 = growth_bad_files[0]
        gtxt = f"{f0.get('log_growth_value'):g}%" if int(_n(f0.get("is_percent_growth"), 0) or 0) == 1 else _mb(f0.get("log_growth_value"))
        prob("growth_bad", f"FILEGROWTH do log = {gtxt}",
             f"{f0.get('log_logical_name')}: crescimento {'percentual' if int(_n(f0.get('is_percent_growth'), 0) or 0) == 1 else 'pequeno'} gera muitos VLFs e autogrows lentos" + (f" · Log Growths desde o arranque: {_i(log_growths)}" if log_growths else ""),
             "Barato de corrigir, evita o próximo incidente", "warning", "fa-expand-arrows-alt", rec_ids=["rec_growth"],
             summary="Crescimento percentual ou pequeno gera VLFs a mais")
    if growth_disabled or growth_bad_files:
        rec("rec_growth", "Corrigir FILEGROWTH do log (512 MB fixos)", "Crescimento fixo em MB (não %), 256–1024 MB conforme a geração.",
            "medium", "low", ["growth_bad", "growth_disabled", "vlf_high"], "fa-expand-arrows-alt",
            f"SELECT name, is_percent_growth, growth, max_size FROM sys.master_files WHERE database_id = DB_ID(N'{_esc(db_name)}') AND type = 1;\n-- ALTER DATABASE {db_q} MODIFY FILE (NAME = N'{log_logical_q}', FILEGROWTH = 512MB);   -- comentado")
    elif log_growths is not None and log_growths >= LOG_GROWTHS_WARN and uptime_h and uptime_h < 24 * 30:
        prob("autogrow_frequent", f"{_i(log_growths)} autogrows do log desde o arranque ({_i(uptime_h)} h)",
             "contador Log Growths (dm_os_performance_counters); histórico com data exige ALTER TRACE (default trace) — não disponível a sql_monitoring",
             "Log subdimensionado para a carga: cada autogrow bloqueia escritas", "info", "fa-expand-arrows-alt", conf="heuristic", rec_ids=["rec_growth"],
             summary="Crescimento contínuo do ficheiro de log")
        rec("rec_growth", "Pré-dimensionar o log ao tamanho de trabalho e FILEGROWTH fixo", "Evita autogrows em produção (cada um zera o ficheiro e bloqueia).",
            "medium", "low", ["autogrow_frequent"], "fa-expand-arrows-alt",
            f"-- ALTER DATABASE {db_q} MODIFY FILE (NAME = N'{log_logical_q}', SIZE = {int(alvo_mb)}MB, FILEGROWTH = 512MB);   -- comentado")
    if len(log_files) > 1:
        prob("multi_log_files", f"{len(log_files)} ficheiros de log",
             "; ".join(f"{f.get('log_logical_name')} ({_mb(f.get('log_size_mb'))})" for f in log_files),
             "SQL Server usa-os sequencialmente (sem stripe): não há ganho, só confusão de shrink", "info", "fa-copy",
             summary="Sem ganho de desempenho; complica o shrink")

    # 7) Em curso / errorlog
    if reqs:
        r0 = reqs[0]
        prob("backup_in_progress", f"{r0.get('command')} em curso ({_num(r0.get('percent_complete'), 0)}%)",
             f"sessão {_i(r0.get('session_id'))} · início {_fmt_dt(r0.get('start_time'))} · {r0.get('program_name') or ''}",
             "Enquanto corre, o log não trunca (ACTIVE_BACKUP_OR_RESTORE)", "info", "fa-tasks", summary=f"Início {_fmt_dt(r0.get('start_time'))}")
    if el_9002:
        prob("errorlog_9002", f"Erro 9002 (log cheio) ocorreu {n9002} vezes nos últimos 7 dias",
             f"última {el_9002[0]['when']}: {el_9002[0]['text'][:140]}", "Já aconteceu: a aplicação já parou por causa deste log", "critical", "fa-file-alt", source="history",
             rec_ids=[i for i in ("rec_log_backup", "rec_open_tran", "rec_disk") if i in rec_ids_added], summary=f"Último: {_fmt_dt_full(el_9002[0]['when'])}")
    if el_autogrow:
        prob("autogrow_slow", f"Autogrow lento registado no errorlog ({len(el_autogrow)}x em 7 dias)", el_autogrow[0]["text"][:160],
             "Autogrows > 10 s bloqueiam escritas (Msg 5145)", "warning", "fa-file-alt", source="history", rec_ids=["rec_growth"] if "rec_growth" in rec_ids_added else [],
             summary=f"Último: {_fmt_dt_full(el_autogrow[0]['when'])}")
    if state_desc and state_desc != "ONLINE":
        prob("db_state", f"Base {state_desc}", "sys.databases.state_desc", "Diagnóstico parcial: DMVs por base indisponíveis", "warning", "fa-power-off", summary=state_desc)
    if not has_access and st_rows:
        notes.append("sem acesso a base (HAS_DBACCESS = 0): dm_db_log_stats/dm_db_log_info indisponiveis (secundaria AG nao legivel ou sem user)")

    # ---------------------------------------------------------------- triagem (heuristica, ordem do pacote 03)
    if chain_state in ("never", "late"):
        triage = ("CADEIA PARADA", "backup de log parado/inexistente — o log nunca trunca em FULL sem ele")
    elif lrw == "ACTIVE_TRANSACTION":
        triage = ("TRANSACAO ABERTA", f"sessão {tran_sid} segura o log há {_num(tran_min, 0)} min" if tran_min is not None else "transação aberta segura o log")
    elif lrw in ("DATABASE_MIRRORING", "AVAILABILITY_REPLICA"):
        triage = ("REPLICA", "fila do mirror/AG segura o log — resolver no drill de mirroring/AG")
    elif lrw == "REPLICATION":
        triage = ("REPLICACAO", "log reader/CDC não consumiu o log")
    elif (headroom_mb is not None and headroom_mb < HEADROOM_MIN_MB) or (runway_days is not None and runway_days <= RUNWAY_DAYS_CRIT):
        triage = ("DISCO", "margem de crescimento a esgotar-se — garantir espaço primeiro")
    elif potencial_mb > 0 and lrw in _RETAINED_OK and (log_size_mb or 0) > alvo_mb * TARGET_X_WARN:
        triage = ("SHRINK", f"nada retém e o log está {(log_size_mb or 0)/alvo_mb:.0f}x acima do alvo ({_gb(alvo_mb)})")
    elif used_pct is not None and used_pct > tl_warn:
        triage = ("CRESCIMENTO", "log cheio mas a truncar normalmente — cadência do backup de log ou tamanho de trabalho")
    else:
        triage = ("SAUDAVEL", "nada retém o log e o uso está abaixo do limiar")

    crit = sum(1 for p in problems if p["severity"] == "critical")
    warn = sum(1 for p in problems if p["severity"] == "warning")
    verdict = "critical" if crit else ("warning" if warn else ("ok" if st_rows else "info"))

    # ---------------------------------------------------------------- tiles (mockup: 5)
    if chain_state == "simple":
        last_log_val, last_log_sub, last_log_sev = "n/a", "recovery SIMPLE", "info"
    elif last_log is None:
        last_log_val, last_log_sub, last_log_sev = ("desconhecido" if chain_state == "unknown" else "NUNCA"), ("noutra réplica?" if chain_state == "unknown" else "sem backup de log registado"), ("warning" if chain_state == "unknown" else "critical")
    else:
        last_log_val = f"{_num(hours_since_log, 1)} h" if hours_since_log < 48 else f"{_num(hours_since_log / 24, 0)} d"
        last_log_sub, last_log_sev = _fmt_dt(last_log), ("critical" if hours_since_log > lb_crit else ("warning" if hours_since_log > lb_warn else "ok"))
    tran_ok = tran_min is None or tran_min < TRAN_MIN_WARN
    summary = [
        {"label": "Log utilizado", "value": (f"{_num(used_pct, 1)}%" if used_pct is not None else "n/d"),
         "sub": (f"{_gb(used_mb)} / {_gb(log_size_mb)}" if log_size_mb else "") + (f" · {_num(effective_pct, 0)}% do limite efetivo ({_gb(effective_limit_mb)})" if effective_pct is not None else ""),
         "icon": "fa-chart-line",
         "severity": ("critical" if ((effective_pct if effective_pct is not None else used_pct) or 0) > tl_crit or bool(growth_disabled)
                      else ("warning" if (used_pct or 0) > tl_warn else "ok"))},
        {"label": "Causa atual (log_reuse_wait)", "value": lrw or "?",
         "sub": _REASON_TEXT.get(lrw, ("", ""))[0] or ("nada retém" if lrw == "NOTHING" else ("aguarda backup de log" if lrw == "LOG_BACKUP" else "")),
         "icon": "fa-database", "severity": "critical" if (lrw and lrw not in _RETAINED_OK) else "ok"},
        {"label": "Último backup de log", "value": last_log_val, "sub": last_log_sub, "icon": "fa-clock", "severity": last_log_sev},
        {"label": "Transação mais antiga", "value": (f"{_num(tran_min, 0)} min" if tran_min is not None else "0 min"),
         "sub": ("sem retenção por transação longa" if tran_ok else f"sessão {tran_sid} · {_gb(tran_log_mb)} de log"),
         "icon": ("fa-check-circle" if tran_ok else "fa-user-clock"),
         "severity": "critical" if (tran_min or 0) >= TRAN_MIN_CRIT else ("warning" if (tran_min or 0) >= TRAN_MIN_WARN else "ok")},
        {"label": "Runway (previsão)", "value": (f"~ {_num(runway_days, 1)} dias" if runway_days is not None else "n/d"),
         "sub": ("até esgotar a capacidade disponível" if runway_days is not None else ("sem geração medida (backups de log 7d)" if headroom_mb is not None else "volume não lido")),
         "icon": "fa-chart-line",
         "severity": "critical" if (runway_days is not None and runway_days <= RUNWAY_DAYS_CRIT) else ("warning" if (runway_days is not None and runway_days <= RUNWAY_DAYS_WARN) else "info")},
    ]

    # ---------------------------------------------------------------- contexto (mockup + extras)
    growth_txt = "n/d"
    if first_log:
        growth_txt = "desligado" if int(_n(first_log.get("log_growth_disabled"), 0) or 0) == 1 else (f"{first_log.get('log_growth_value'):g}%" if int(_n(first_log.get("is_percent_growth"), 0) or 0) == 1 else _mb(first_log.get("log_growth_value")))
    if first_log and int(_n(first_log.get("log_unlimited"), 0) or 0) == 1:
        max_txt = f"ilimitado · {_gb(alvo_mb)} (sugerido)"
    elif first_log:
        max_txt = _gb(first_log.get("log_max_size_mb"))
    else:
        max_txt = "?"
    ok_span = '<span style="color:var(--sev-ok-text);font-weight:600;">{}</span>'
    if ag_name:
        _sync = str(ha.get("synchronization_state_desc") or "?")
        _health = str(ha.get("synchronization_health_desc") or "?")
        ha_html = (ok_span.format(_sync) if _sync == "SYNCHRONIZED" else _sync) + "<br>" + (ok_span.format(_health) if _health == "HEALTHY" else _health)
        ha_txt = f"AG {ag_name} · {ag_role or '?'} · {_sync} / {_health}"
    elif mstate:
        ha_html = None
        ha_txt = f"Mirroring {mstate} ({ha.get('mirroring_role_desc') or '?'})"
    else:
        ha_html = None
        ha_txt = "nenhum"
    side_rows = [
        {"k": "Database", "v": db_name},
        {"k": "Instância", "v": display_inst},
        {"k": "Recovery", "v": recovery or "?"},
        {"k": "Estado", "v": state_desc or "?"},
        {"k": "Tamanho (atual)", "v": (f"{_gb(log_size_mb)} · usado {_gb(used_mb)} ({_num(used_pct, 1)}%)" if used_pct is not None else (_gb(log_size_mb) if log_size_mb else "?"))},
        {"k": "Máx. configurado", "v": max_txt},
        {"k": "Growth", "v": growth_txt},
        {"k": "Volume", "v": (f"{vol0.get('volume_mount_point')} · {_num(vol_free_gb, 1)} GB livres ({_num(vol_free_pct, 1)}%)" if vols else "n/d")},
        {"k": "VLFs", "v": (f"{_i(vlf_total)} ({_i(vlf_active or 0)} ativos)" if vlf_total is not None else "n/d (SQL < 2016 SP2 ou sem acesso)")},
        {"k": "HA / AG", "v": ha_txt, "vHtml": ha_html},
        {"k": "Limite efetivo", "v": (f"{_gb(effective_limit_mb)} (ficheiro + margem) · {_num(effective_pct, 0)}% usado" if effective_pct is not None else "n/d")},
        {"k": "Geração", "v": (f"{_mb(daily_mb)}/dia (média 7d, {days_with_log}/7 dias com backup de log)" if daily_mb else "n/d (sem backups de log em 7d)") + (f" · IO: {_mb(daily_mb_io)}/dia" if daily_mb_io else "")},
        {"k": "Último FULL", "v": _fmt_dt(last_full) if last_full else "nenhum em 30d (msdb local)"},
        {"k": "SQL Server", "v": f"{caps.get('product_version') or '?'} · uptime {_i(uptime_h)} h" if uptime_h is not None else str(caps.get('product_version') or '?')},
        {"k": "Origem", "v": "DMV/msdb/errorlog · " + now.strftime("%d/%m %H:%M")},
    ]
    if snapshot_pct is not None or snapshot_ts:
        diff_txt = ""
        if snapshot_pct is not None and used_pct is not None:
            diff_txt = f" (live {_num(used_pct, 1)}%, {'+' if used_pct - snapshot_pct >= 0 else ''}{_num(used_pct - snapshot_pct, 1)} pp)"
        side_rows.append({"k": "Intelligence", "v": "última coleta " + (f"{_num(snapshot_pct, 1)}%" if snapshot_pct is not None else "?")
                          + (f" às {_fmt_dt(snapshot_ts)}" if snapshot_ts else "") + (f" · log backup: {snapshot_age}" if snapshot_age else "") + diff_txt})

    steps = {
        "CADEIA PARADA": "1) Religar/verificar o job de backup de log (TSM/Agent).\n2) Backup de log manual liberta o log se nada mais retiver.\n3) Garantir espaço no volume enquanto isso.\n4) Só depois: shrink até ao alvo se o log estiver muito acima.",
        "TRANSACAO ABERTA": "1) Identificar a sessão (login/host/programa) e o que faz.\n2) Decidir com o dono da aplicação: esperar, commit pela aplicação, ou KILL (rollback pode ser longo).\n3) Backup de log depois de fechar a transação.\n4) Garantir espaço no volume entretanto.",
        "REPLICA": "1) Abrir o diagnóstico de Mirroring/AG desta base.\n2) Resolver a réplica (RESUME/rebuild pelo runbook).\n3) Garantir espaço no volume do log do principal entretanto.",
        "REPLICACAO": "1) Verificar Log Reader Agent / capture job CDC.\n2) Se parado, arrancar; se destruído, decisão do time de replicação.\n3) Garantir espaço no volume entretanto.",
        "DISCO": "1) Libertar/expandir o volume do log (ou ficheiro temporário noutro volume).\n2) Resolver a causa de retenção/cadência.\n3) Reavaliar runway.",
        "SHRINK": "1) Confirmar que nada retém (log_reuse_wait NOTHING/LOG_BACKUP).\n2) Backup de log.\n3) DBCC SHRINKFILE até ao alvo (repetir 2-3 se o VLF ativo estiver no fim).\n4) Corrigir FILEGROWTH.",
        "CRESCIMENTO": "1) Ver se o log desce após o próximo backup de log.\n2) Se não desce: encurtar cadência ou aceitar tamanho de trabalho.\n3) Corrigir FILEGROWTH se for % ou pequeno.",
        "SAUDAVEL": "Nada a fazer agora. Se o card voltar a alarmar, reabrir este diagnóstico.",
    }
    next_step = {"text": f"TRIAGEM: {triage[0]} ({triage[1]}).\n" + steps.get(triage[0], ""),
                 "sqlCheck": f"SELECT name, recovery_model_desc, log_reuse_wait_desc FROM sys.databases WHERE name = N'{_esc(db_name)}';\nDBCC SQLPERF(LOGSPACE);"}

    # ---------------------------------------------------------------- banner "DIAGNOSTICO PRINCIPAL" + "desde" (mockup owner 02/09)
    if n9002:
        risk_text = f"Já ocorreram {n9002} eventos de Erro 9002 nos últimos 7 dias."
        risk_cta = {"label": "Ver eventos", "section": "errorlog"}
    elif runway_days is not None and runway_days <= RUNWAY_DAYS_WARN:
        risk_text = f"Ao ritmo atual o disco do log esgota em ~{_num(runway_days, 1)} dias."
        risk_cta = {"label": "Ver evidência", "section": "technical"}
    elif headroom_mb is not None:
        risk_text = f"Margem de crescimento {_gb(headroom_mb)}; sem Erro 9002 no errorlog (7 dias)."
        risk_cta = {"label": "Ver histórico de backups", "section": "backups"}
    else:
        risk_text = "Sem Erro 9002 no errorlog (7 dias)."
        risk_cta = None
    since_ts = None
    tkey = triage[0]
    used_chip = f"log a {_num(used_pct, 1)}%" if used_pct is not None else "uso n/d"
    if tkey == "CADEIA PARADA":
        headline = "CADEIA DE BACKUP DE LOG INTERROMPIDA"
        chain = [recovery or "?", ("Sem backup de log" if last_log is None else "Backup de log atrasado"), lrw or "LOG_BACKUP",
                 "Log não trunca", "Crescimento contínuo", "Risco de erro 9002 / indisponibilidade"]
        note = "Um backup de log pode permitir o truncamento se LOG_BACKUP continuar a ser o único fator de retenção."
        since_ts = last_log  # desde o último backup de log (o modelo usa este instante)
    elif tkey == "TRANSACAO ABERTA":
        headline = "TRANSAÇÃO ABERTA RETÉM O LOG"
        chain = [f"sessão {tran_sid} ({oldest.get('login_name') or '?'})", (f"aberta há {_num(tran_min, 0)} min" if tran_min is not None else "aberta"),
                 "ACTIVE_TRANSACTION", "Log não trunca", "Backup de log não liberta", used_chip]
        note = "Tudo o que está atrás da transação no log fica preso; fechar (ou matar, decisão humana) a sessão é a única saída."
        since_ts = _dt(oldest.get("database_transaction_begin_time"))
    elif tkey == "REPLICA":
        headline = "RÉPLICA RETÉM O LOG DO PRINCIPAL"
        chain = [(f"AG {ag_name} · {ag_role or '?'}" if ag_name else f"Mirroring {mstate or '?'}"), f"fila {_gb((send_q_kb or 0) / 1024)}", lrw,
                 "Log não trunca", used_chip, "Risco de erro 9002 no principal"]
        note = "O log só trunca quando a réplica confirmar o recebimento; resolver no drill de Mirroring/AG."
    elif tkey == "REPLICACAO":
        headline = "REPLICAÇÃO/CDC NÃO CONSUMIU O LOG"
        chain = ["Publicação/CDC ativo", "Log reader / capture parado?", "REPLICATION", "Log não trunca", used_chip]
        note = "O log só trunca depois de lido pelo log reader (replicação) ou pelo capture job (CDC)."
    elif tkey == "DISCO":
        headline = "DISCO DO LOG A ESGOTAR-SE"
        chain = [used_chip, (f"margem {_mb(headroom_mb)}" if headroom_mb is not None else "margem n/d"),
                 (f"runway ~{_num(runway_days, 1)} dias" if runway_days is not None else "runway n/d"), "9002 ao encher"]
        note = "Garantir espaço primeiro; a causa de retenção/cadência resolve-se a seguir."
    elif tkey == "SHRINK":
        headline = "LOG MUITO ACIMA DO TAMANHO DE TRABALHO"
        chain = [f"log {_gb(log_size_mb)}", f"alvo {_gb(alvo_mb)}", lrw or "NOTHING", "nada retém", f"shrink potencial {_gb(potencial_mb)}"]
        note = "Shrink só depois de um backup de log e nunca abaixo do tamanho de trabalho."
    elif tkey == "CRESCIMENTO":
        headline = "LOG CHEIO MAS A TRUNCAR NORMALMENTE"
        chain = [used_chip, lrw or "LOG_BACKUP", "aguarda próximo backup de log", "cadência ou tamanho de trabalho"]
        note = "Se a % não descer após o próximo backup de log, o log está subdimensionado ou a cadência é longa para a geração."
    else:
        headline = "TRANSACTION LOG SAUDÁVEL"
        chain = [lrw or "NOTHING", used_chip, "sem retenção"]
        note = "Nada retém o log e o uso está abaixo do limiar."
    principal = {"label": "Diagnóstico principal", "headline": headline, "chain": [{"label": c} for c in chain], "note": note,
                 "severity": verdict, "icon": ("fa-check" if verdict == "ok" else "fa-exclamation"),
                 "risk": {"level": verdict, "text": risk_text, "cta": risk_cta}}

    out["diagnosis"] = {"header": {"title": f"Transaction log — {db_name}", "subtitle": f"{display_inst} · Recovery: {recovery or '?'} · {lrw or '?'}", "verdict": verdict},
                        "since": ({"ts": since_ts.isoformat()} if since_ts else None),
                        "principal": principal,
                        "summary": summary, "problems": problems, "recommendations": recs,
                        "side": {"title": "Contexto do log", "rows": side_rows}, "nextStep": next_step}
    out["raw"] = {"capabilities": caps, "state": st, "log_files": log_files, "counters": counters, "logspace_row": logspace_row,
                  "log_stats": log_stats, "vlf_info": vlf_info, "open_transactions": otr, "backups_3d": bk3, "backups_30d_by_day": bk30,
                  "by_type": {k: {**v, "last": (v["last"].isoformat() if v["last"] else None)} for k, v in by_type.items()},
                  "log_per_day": log_per_day, "volumes": vols, "ha": ha, "requests": reqs, "errorlog": errorlog,
                  "derived": {"used_pct": used_pct, "used_mb": used_mb, "log_size_mb": log_size_mb, "alvo_mb": alvo_mb, "potencial_mb": potencial_mb,
                              "effective_limit_mb": effective_limit_mb, "effective_pct": effective_pct,
                              "daily_mb": daily_mb, "daily_mb_io": daily_mb_io, "runway_days": runway_days, "headroom_mb": headroom_mb,
                              "hours_since_log_backup": hours_since_log, "chain_state": chain_state, "triage": triage[0],
                              "thresholds": {"tlog_usage": [tl_warn, tl_crit], "backup_delay_log_h": [lb_warn, lb_crit]}}}
    return out
