# -*- coding: utf-8 -*-
"""
GET /api/queries/mirroring-diagnosis/{server_id}?database=...&partner=...   (2026-08-17)

Drill-down de diagnostico de Database Mirroring (layout "Diagnostico": O que se
passa / Porque / O que fazer / Evidencia tecnica / Dados brutos), a partir do
card do KPI "Mirroring nao saudavel". Ordem de leitura do DBA (owner):
  1) INCENDIO REAL primeiro: enquanto SUSPENDED o log do PRINCIPAL nao trunca
     (log_reuse_wait_desc = DATABASE_MIRRORING) -> risco de encher o disco de log
     e derrubar a aplicacao. Medir % de log usado (DBCC SQLPERF(LOGSPACE)) e
     send/redo queue.
  2) CAUSA no MIRROR: errorlog (1453, 823/824 corrupcao no redo, 9002 log cheio,
     'suspend'), espaco em disco dos volumes da DB no mirror, auto page repair.
  3) ACCAO: ALTER DATABASE ... SET PARTNER RESUME (comentado) -> Synchronizing
     enquanto drena a send queue -> Synchronized. Se voltar a SUSPENDED sozinho:
     redo a bater em erro -> CHECKDB + rebuild do mirror (comentado, por passos).
  4) Estrategico: mirroring e' deprecated desde SQL 2012 -> radar de migracao p/ AG.

Identidade: pool (conta do servico), SELECT/DBCC informativo; xp_readerrorlog
exige securityadmin — se falhar, degrada com instrucao para correr no SSMS.
Nada e' executado/alterado. DDL/ALTER so' comentado. Nunca 500 por um bloco:
cada fonte falha isoladamente e o texto diz o que faltou.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from api.async_db import async_execute_on_server

logger = logging.getLogger(__name__)
router = APIRouter()

_DBNAME = re.compile(r"^[^\[\]'\";]{1,128}$")


def _sid(instance: str) -> str:
    """'HOST\\I01' -> 'HOST_I01' (formato server_id do pool)."""
    return (instance or "").strip().replace("\\", "_")


def _esc(v: str) -> str:
    return (v or "").replace("'", "''")


def _n(v, d=None):
    try:
        return float(v) if v is not None else d
    except (TypeError, ValueError):
        return d


# 2026-09-02 (mockup owner): formato pt (virgula decimal, ponto de milhares), GB com 1 decimal
def _num(v, nd: int = 1, d: str = "n/d") -> str:
    if v is None:
        return d
    try:
        s = f"{float(v):,.{nd}f}"
    except (TypeError, ValueError):
        return d
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _gb(mb, nd: int = 1) -> str:
    return "n/d" if mb is None else f"{_num(float(mb) / 1024.0, nd)} GB"


def _i(v, d: str = "?") -> str:
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return d


def _fmt_dt_full(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M:%S")
    try:
        return datetime.fromisoformat(str(v)[:19]).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return str(v)[:19] if v else "n/d"


def _q_backups(db: str) -> str:
    # ultimo FULL / LOG (msdb local ao principal); filtro por backup_finish_date (indice backupsetDate)
    return f"""
SELECT b.type AS backup_type, MAX(b.backup_finish_date) AS last_finish
FROM msdb.dbo.backupset b WITH (NOLOCK)
WHERE b.database_name = N'{_esc(db)}' AND b.backup_finish_date >= DATEADD(DAY, -60, GETDATE())
GROUP BY b.type;
"""


async def _try(server_id: str, query: str, notes: List[str], label: str, database: str = "master") -> List[Dict[str, Any]]:
    try:
        return await async_execute_on_server(server_id, query, database) or []
    except Exception as e:  # graceful degradation por bloco
        msg = str(e)[:180]
        logger.info(f"mirroring-diagnosis {server_id} {label}: {msg}")
        notes.append(f"{label}: {msg}")
        return []


def _q_state(db: str) -> str:
    return f"""
SELECT CAST(@@SERVERNAME AS NVARCHAR(128)) AS server_name,
       d.name AS database_name, d.state_desc AS database_state, d.log_reuse_wait_desc, d.recovery_model_desc,
       m.mirroring_state_desc, m.mirroring_role_desc, m.mirroring_safety_level_desc, m.mirroring_witness_state_desc,
       m.mirroring_partner_name, m.mirroring_partner_instance, m.mirroring_witness_name,
       m.mirroring_connection_timeout, m.mirroring_failover_lsn, m.mirroring_end_of_log_lsn, m.mirroring_redo_queue_type, m.mirroring_redo_queue,
       (SELECT SUM(CAST(mf.size AS BIGINT)) * 8 / 1024 FROM sys.master_files mf WITH (NOLOCK) WHERE mf.database_id = d.database_id AND mf.type_desc = 'LOG') AS log_size_mb,
       (SELECT SUM(CAST(mf.size AS BIGINT)) * 8 / 1024 FROM sys.master_files mf WITH (NOLOCK) WHERE mf.database_id = d.database_id AND mf.type_desc = 'ROWS') AS data_size_mb,
       (SELECT MAX(CASE WHEN mf.max_size IN (-1, 268435456) THEN 1 ELSE 0 END) FROM sys.master_files mf WITH (NOLOCK) WHERE mf.database_id = d.database_id AND mf.type_desc = 'LOG') AS log_unlimited,
       (SELECT COUNT(*) FROM sys.master_files mf WITH (NOLOCK) WHERE mf.database_id = d.database_id AND mf.type_desc = 'LOG') AS log_file_count
FROM sys.databases d WITH (NOLOCK)
JOIN sys.database_mirroring m WITH (NOLOCK) ON m.database_id = d.database_id
WHERE d.name = N'{_esc(db)}';
"""


_Q_LOGSPACE = "DBCC SQLPERF(LOGSPACE) WITH NO_INFOMSGS;"


def _q_counters(db: str) -> str:
    return f"""
SELECT RTRIM(counter_name) AS counter_name, cntr_value
FROM sys.dm_os_performance_counters WITH (NOLOCK)
WHERE object_name LIKE '%Database Mirroring%'
  AND RTRIM(instance_name) = N'{_esc(db)}'
  AND RTRIM(counter_name) IN ('Log Send Queue KB','Redo Queue KB','Log Bytes Sent/sec','Log Bytes Received/sec','Redo Bytes/sec',
                              'Send/Receive Ack Time','Log Harden Time','Mirrored Write Transactions/sec','Transaction Delay','Log Remaining for Undo KB');
"""


def _q_errorlog(term: str) -> str:
    return f"EXEC master.dbo.xp_readerrorlog 0, 1, N'{_esc(term)}';"


def _q_page_repair(db: str) -> str:
    return f"""
SELECT TOP 10 database_id, file_id, page_id, error_type, page_status, modification_time
FROM sys.dm_db_mirroring_auto_page_repair WITH (NOLOCK)
WHERE database_id = DB_ID(N'{_esc(db)}')
ORDER BY modification_time DESC;
"""


def _q_volumes(db: str) -> str:
    return f"""
SELECT DISTINCT vs.volume_mount_point, vs.logical_volume_name,
       CAST(vs.total_bytes / 1073741824.0 AS DECIMAL(12,1)) AS total_gb,
       CAST(vs.available_bytes / 1073741824.0 AS DECIMAL(12,1)) AS free_gb,
       CAST(100.0 * vs.available_bytes / NULLIF(vs.total_bytes, 0) AS DECIMAL(5,1)) AS free_pct,
       mf.type_desc AS file_type
FROM sys.master_files mf WITH (NOLOCK)
CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs
WHERE mf.database_id = DB_ID(N'{_esc(db)}');
"""


def _parse_errorlog_dt(row: Dict[str, Any]) -> Optional[datetime]:
    v = row.get("LogDate") or row.get("logdate")
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v)[:19])
    except Exception:
        return None


def _errorlog_recent(rows: List[Dict[str, Any]], days: int = 7, limit: int = 15) -> List[Dict[str, Any]]:
    cutoff = datetime.now() - timedelta(days=days)
    out = []
    for r in rows:
        dt = _parse_errorlog_dt(r)
        if dt is None or dt >= cutoff:
            out.append({"when": str(r.get("LogDate") or r.get("logdate") or "")[:19], "text": str(r.get("Text") or r.get("text") or "")[:300]})
    out.sort(key=lambda x: x["when"], reverse=True)
    return out[:limit]


_ERR_PATTERNS = [
    (r"\b1453\b", "1453 (mirroring suspenso: parceiro nao alcancavel / erro de rede)"),
    (r"\b823\b|\b824\b", "823/824 (I/O / pagina corrompida — redo pode falhar no mirror)"),
    (r"\b9002\b", "9002 (log cheio)"),
    (r"\b1418\b", "1418 (endpoint do parceiro nao alcancavel)"),
    (r"suspend", "'suspend' (evento de suspensao registado)"),
    (r"insufficient|no space|disk full|espa", "espaco em disco"),
]


def _classify_errorlog(lines: List[Dict[str, Any]]) -> List[str]:
    found = []
    for pat, label in _ERR_PATTERNS:
        if any(re.search(pat, (l.get("text") or ""), re.I) for l in lines):
            found.append(label)
    return found


@router.get("/mirroring-diagnosis/{server_id}")
async def mirroring_diagnosis(server_id: str, database: str = Query(...), partner: Optional[str] = Query(None)) -> Dict[str, Any]:
    if not _DBNAME.match(database or ""):
        raise HTTPException(status_code=400, detail="database invalido")
    notes: List[str] = []
    principal_sid = _sid(server_id)
    out: Dict[str, Any] = {"success": True, "server_id": principal_sid, "database": database, "notes": notes, "sources": []}

    # ---- PRINCIPAL ----
    st_rows = await _try(principal_sid, _q_state(database), notes, "estado (sys.database_mirroring)")
    st = st_rows[0] if st_rows else {}
    if st_rows:
        out["sources"].append("sys.database_mirroring")
    partner_inst = (st.get("mirroring_partner_instance") or partner or "").strip()
    partner_sid = _sid(partner_inst) if partner_inst else None

    logspace_rows = await _try(principal_sid, _Q_LOGSPACE, notes, "DBCC SQLPERF(LOGSPACE)")
    log_used_pct = None
    log_size_mb = _n(st.get("log_size_mb"))
    for r in logspace_rows:
        name = r.get("Database Name") or r.get("database_name") or r.get("DatabaseName")
        if str(name) == database:
            log_used_pct = _n(r.get("Log Space Used (%)") or r.get("log_space_used_pct"))
            if log_size_mb is None:
                log_size_mb = _n(r.get("Log Size (MB)"))
            break
    if logspace_rows:
        out["sources"].append("DBCC SQLPERF(LOGSPACE)")

    ctr_rows = await _try(principal_sid, _q_counters(database), notes, "contadores Database Mirroring")
    counters = {r.get("counter_name"): _n(r.get("cntr_value")) for r in ctr_rows}
    if ctr_rows:
        out["sources"].append("dm_os_performance_counters")

    el_p = _errorlog_recent(await _try(principal_sid, _q_errorlog("mirror"), notes, "errorlog principal (xp_readerrorlog)"))
    el_p += _errorlog_recent(await _try(principal_sid, _q_errorlog("suspend"), notes, "errorlog principal 'suspend'"))
    el_p = sorted({(x["when"], x["text"]): x for x in el_p}.values(), key=lambda x: x["when"], reverse=True)[:15]

    apr = await _try(principal_sid, _q_page_repair(database), notes, "auto page repair (principal)")

    # 2026-09-01 (Fase A2): volumes tambem no PRINCIPAL — o incendio real e' o
    # disco do t-log DESTE lado; ate hoje so se olhava o disco do mirror.
    vol_p = await _try(principal_sid, _q_volumes(database), notes, "volumes no principal")
    # 2026-09-02 (mockup): ultimo backup FULL/LOG para o "Contexto rapido"
    bk_rows = await _try(principal_sid, _q_backups(database), notes, "backups (msdb)")
    last_full = next((r.get("last_finish") for r in bk_rows if str(r.get("backup_type") or "").upper() == "D"), None)
    last_log_bkp = next((r.get("last_finish") for r in bk_rows if str(r.get("backup_type") or "").upper() == "L"), None)

    # ---- MIRROR ----
    mirror: Dict[str, Any] = {"instance": partner_inst, "reachable": False}
    el_m: List[Dict[str, Any]] = []
    vol_m: List[Dict[str, Any]] = []
    st_m: Dict[str, Any] = {}
    if partner_sid:
        st_m_rows = await _try(partner_sid, _q_state(database), notes, f"estado no mirror {partner_inst}")
        st_m = st_m_rows[0] if st_m_rows else {}
        mirror["reachable"] = bool(st_m_rows)
        vol_m = await _try(partner_sid, _q_volumes(database), notes, f"volumes no mirror {partner_inst}")
        el_m = _errorlog_recent(await _try(partner_sid, _q_errorlog("mirror"), notes, f"errorlog mirror {partner_inst}"))
        el_m += _errorlog_recent(await _try(partner_sid, _q_errorlog("suspend"), notes, f"errorlog mirror 'suspend'"))
        el_m = sorted({(x["when"], x["text"]): x for x in el_m}.values(), key=lambda x: x["when"], reverse=True)[:15]
        apr_m = await _try(partner_sid, _q_page_repair(database), notes, "auto page repair (mirror)")
        if apr_m:
            apr = apr + apr_m
        if st_m_rows or vol_m or el_m:
            out["sources"].append(f"mirror:{partner_inst}")
    else:
        notes.append("parceiro (mirror) desconhecido — nao foi possivel consultar o lado do mirror")

    # ---- Findings ----
    problems: List[Dict[str, Any]] = []
    recs: List[Dict[str, Any]] = []
    mstate = (st.get("mirroring_state_desc") or "").upper()
    role = (st.get("mirroring_role_desc") or "").upper()
    lrw = (st.get("log_reuse_wait_desc") or "").upper()
    send_q = counters.get("Log Send Queue KB")
    redo_q = counters.get("Redo Queue KB")
    ts = datetime.now().isoformat(timespec="minutes")
    db_q = f"[{database}]"

    # 2026-09-01 (Fase A, heuristica do runbook MirrorRebuild do owner, validada
    # ao vivo 31/08: fila 101 GB vs dados 6,8 GB): com o mirroring parado,
    # fila > dados => re-seed (rebuild) e' mais rapido que drenar; fila < dados
    # => RESUME tende a bastar. Triagem, nao ordem — a execucao e' do runbook.
    data_size_mb = _n(st.get("data_size_mb"))
    triage = None  # None = sem veredito (saudavel, ou sem dados para calcular)
    if mstate in ("SUSPENDED", "DISCONNECTED") and role == "PRINCIPAL" \
            and send_q is not None and data_size_mb:
        if send_q > data_size_mb * 1024:
            triage = {"verdict": "REBUILD", "why": f"fila {send_q/1048576:.1f} GB > dados {data_size_mb/1024:.1f} GB — re-seed e' mais rapido que drenar"}
        else:
            triage = {"verdict": "RESUME", "why": f"fila {send_q/1024:.0f} MB < dados {data_size_mb/1024:.1f} GB — drenagem tende a ser viavel"}

    def prob(id_, title, evidence, impact, sev, icon, source="dmv", conf="measured", rec_ids=None):
        problems.append({"id": id_, "title": title, "evidence": evidence, "impact": impact, "icon": icon, "severity": sev,
                         "source": source, "confidence": conf, "ts": ts, "recIds": rec_ids or []})

    # 1) Incendio real: log do principal nao trunca
    if lrw == "DATABASE_MIRRORING" or (mstate in ("SUSPENDED", "DISCONNECTED") and role == "PRINCIPAL"):
        pct_txt = f"{log_used_pct:.0f}% do log usado" if log_used_pct is not None else "% de log nao disponivel"
        size_txt = f", log de {log_size_mb:,.0f} MB" if log_size_mb else ""
        sq_txt = f", send queue {send_q:,.0f} KB" if send_q is not None else ""
        sev = "critical" if (log_used_pct or 0) >= 70 else ("warning" if (log_used_pct or 0) >= 40 else "warning")
        prob("log_not_truncating", "Log do PRINCIPAL nao trunca enquanto o mirroring esta suspenso",
             f"log_reuse_wait_desc = {lrw or '?'} · {pct_txt}{size_txt}{sq_txt}",
             "Risco de encher o disco de log do principal e parar a aplicacao — e' o relogio a correr", sev, "fa-fire",
             rec_ids=["rec_check_log"])
        recs.append({"id": "rec_check_log", "title": "Proteger o Principal", "desc": "Confirmar espaço disponível e capacidade de crescimento do transaction log; não encolher/quebrar o mirroring sem decisão.",
                     "impact": "very_high", "effort": "low", "problemIds": ["log_not_truncating"], "icon": "fa-fire-extinguisher",
                     "sqlCheck": f"SELECT name, log_reuse_wait_desc FROM sys.databases WHERE name = N'{_esc(database)}';\nDBCC SQLPERF(LOGSPACE);  -- % de uso do log\nSELECT RTRIM(counter_name) counter_name, cntr_value FROM sys.dm_os_performance_counters WHERE object_name LIKE '%Database Mirroring%' AND RTRIM(instance_name) = N'{_esc(database)}';"})

    # 2) Estado
    if mstate and mstate not in ("SYNCHRONIZED",):
        prob("mstate", f"Mirroring {mstate}", f"role {role or '?'} · safety {st.get('mirroring_safety_level_desc') or '?'} · witness {st.get('mirroring_witness_state_desc') or 'n/a'} · parceiro {partner_inst or '?'}",
             "Sem redundancia enquanto nao voltar a SYNCHRONIZED", "critical" if mstate in ("SUSPENDED", "DISCONNECTED") else "warning", "fa-sync-alt", rec_ids=["rec_resume"])

    # 2b) Triagem RESUME vs REBUILD (2026-09-01, Fase A)
    if triage:
        _is_rb = triage["verdict"] == "REBUILD"
        prob("triage", f"Triagem: {'REBUILD do mirror' if _is_rb else 'RESUME'} recomendado",
             triage["why"],
             "Re-seed (full+logs no mirror) evita drenar a fila inteira e liberta o t-log do principal" if _is_rb
             else "Corrigida a causa, o RESUME drena a fila em tempo aceitavel",
             "warning", "fa-balance-scale", conf="heuristic",
             rec_ids=(["rec_rebuild", "rec_check_log"] if _is_rb else ["rec_resume"]))

    # 2c) Disco do t-log no PRINCIPAL (2026-09-01, Fase A2) — o relogio real.
    low_p = [v for v in vol_p if v.get("file_type") == "LOG"
             and _n(v.get("free_pct"), 100) is not None and _n(v.get("free_pct"), 100) < 15]
    if low_p:
        v0 = low_p[0]
        prob("principal_log_disk", "Disco do t-log do PRINCIPAL a esgotar",
             f"{v0.get('volume_mount_point')} {v0.get('free_gb')} GB livres ({v0.get('free_pct')}%) — volume do LOG",
             "Se encher, a aplicacao PARA (9002) — mais urgente que o proprio mirroring",
             "critical", "fa-hdd", rec_ids=["rec_check_log"])
    if mstate == "SYNCHRONIZING":
        prob("sync", "A ressincronizar (a drenar send queue)", f"send queue {send_q if send_q is not None else '?'} KB · redo queue {redo_q if redo_q is not None else '?'} KB", "Normal apos RESUME; vigiar ate SYNCHRONIZED", "info", "fa-hourglass-half")

    # 3) Causa no mirror
    el_hits = _classify_errorlog(el_m) if el_m else []
    if el_hits:
        prob("mirror_errorlog", "Errorlog do MIRROR com sinais de causa", " · ".join(el_hits) + f" — {len(el_m)} linha(s) recentes", "Explica a suspensao (rede/corrupcao/log cheio)", "critical" if any("823" in h or "9002" in h for h in el_hits) else "warning", "fa-file-alt", source="history", rec_ids=["rec_errorlog"])
    low_vols = [v for v in vol_m if _n(v.get("free_pct"), 100) is not None and _n(v.get("free_pct"), 100) < 10]
    if low_vols:
        v0 = low_vols[0]
        prob("mirror_disk", "Espaco em disco baixo no MIRROR", f"{v0.get('volume_mount_point')} {v0.get('free_gb')} GB livres ({v0.get('free_pct')}%) — {v0.get('file_type')}" + (f" (+{len(low_vols)-1})" if len(low_vols) > 1 else ""),
             "Causa mais comum quando so' alguns bancos suspendem", "critical", "fa-hdd", rec_ids=["rec_disk"])
        recs.append({"id": "rec_disk", "title": "Libertar/expandir disco no mirror", "desc": "Sem espaço no mirror o redo volta a falhar e o mirroring re-suspende; fazer antes do RESUME.", "impact": "very_high", "effort": "low", "problemIds": ["mirror_disk"], "icon": "fa-hdd"})
    if apr:
        prob("page_repair", "Auto page repair registado", f"{len(apr)} tentativa(s) de reparacao automatica de pagina (sys.dm_db_mirroring_auto_page_repair)", "Sinal de corrupcao — se o RESUME recusar, e' isto", "warning", "fa-band-aid", rec_ids=["rec_rebuild"])
    if partner_sid and not mirror["reachable"]:
        prob("mirror_unreachable", "Mirror nao alcancavel a partir do WatcherDB", f"{partner_inst}: sem resposta as consultas (rede/servico/permissao)", "Nao foi possivel confirmar a causa no lado do mirror", "warning", "fa-plug", conf="heuristic", rec_ids=["rec_errorlog"])
    if el_p and _classify_errorlog(el_p):
        prob("principal_errorlog", "Errorlog do PRINCIPAL com eventos de mirroring", " · ".join(_classify_errorlog(el_p)), "Confirma a janela do incidente", "info", "fa-file-alt", source="history")

    # 4) Accoes
    recs.append({"id": "rec_errorlog", "title": "Identificar a causa da suspensão", "desc": "Analisar Errorlog do Principal e do Mirror antes de executar RESUME (1453, 823/824, 9002, falta de espaço).",
                 "impact": "high", "effort": "low", "problemIds": ["mstate", "mirror_errorlog", "mirror_unreachable"], "icon": "fa-search",
                 "sqlCheck": f"-- ligado ao MIRROR ({partner_inst or '<mirror>'}):\nEXEC xp_readerrorlog 0, 1, N'mirror';\nEXEC xp_readerrorlog 0, 1, N'suspend';\nSELECT DB_NAME(database_id) AS banco, mirroring_state_desc, mirroring_role_desc, mirroring_safety_level_desc FROM sys.database_mirroring WHERE mirroring_guid IS NOT NULL;\n-- espaco nos volumes da DB:\nSELECT DISTINCT vs.volume_mount_point, vs.available_bytes/1073741824.0 AS free_gb FROM sys.master_files mf CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs WHERE mf.database_id = DB_ID(N'{_esc(database)}');"})
    recs.append({"id": "rec_resume", "title": "Recuperar o Mirroring", "desc": "Se causa resolvida, avaliar RESUME (no Principal). Se não for viável, considerar rebuild/re-seed.",
                 "impact": "very_high", "effort": "low", "problemIds": ["mstate", "log_not_truncating"], "icon": "fa-play",
                 "sqlCheck": f"-- NO PRINCIPAL, so' depois de resolvida a causa (comentado; o WatcherDB nao executa):\n-- ALTER DATABASE {db_q} SET PARTNER RESUME;\n-- acompanhar:\nSELECT DB_NAME(database_id) banco, mirroring_state_desc FROM sys.database_mirroring WHERE database_id = DB_ID(N'{_esc(database)}');\nSELECT RTRIM(counter_name) c, cntr_value FROM sys.dm_os_performance_counters WHERE object_name LIKE '%Database Mirroring%' AND RTRIM(instance_name) = N'{_esc(database)}' AND RTRIM(counter_name) IN ('Log Send Queue KB','Redo Queue KB');"})
    recs.append({"id": "rec_rebuild", "title": "Rebuild do mirror (re-seed)", "desc": "Se o RESUME voltar a SUSPENDED: CHECKDB, SET PARTNER OFF, restore FULL + logs WITH NORECOVERY no mirror, SET PARTNER de novo.",
                 "impact": "high", "effort": "medium", "problemIds": ["page_repair", "mirror_errorlog"], "icon": "fa-tools",
                 "sqlCheck": f"-- TODOS comentados — plano de rebuild, executar passo a passo com janela:\n-- DBCC CHECKDB ({db_q}) WITH NO_INFOMSGS;            -- no lado que der\n-- ALTER DATABASE {db_q} SET PARTNER OFF;                 -- no principal\n-- RESTORE DATABASE {db_q} FROM DISK = '<full.bak>' WITH NORECOVERY;   -- no mirror\n-- RESTORE LOG {db_q} FROM DISK = '<log.trn>' WITH NORECOVERY;         -- no mirror, todos os logs\n-- ALTER DATABASE {db_q} SET PARTNER = 'TCP://<principal-fqdn>:5022';   -- no mirror\n-- ALTER DATABASE {db_q} SET PARTNER = 'TCP://<mirror-fqdn>:5022';      -- no principal"})
    recs.append({"id": "rec_legacy", "title": "Planear migração para Always On AG", "desc": "Database Mirroring é deprecated (SQL 2012+); cada incidente custa troubleshooting em tecnologia que não evolui.",
                 "impact": "medium", "effort": "high", "problemIds": [], "icon": "fa-road"})

    # ---- Resumo / veredicto ----
    crit = sum(1 for p in problems if p["severity"] == "critical")
    warn = sum(1 for p in problems if p["severity"] == "warning")
    verdict = "critical" if crit else ("warning" if warn else ("ok" if mstate == "SYNCHRONIZED" else "info"))
    # ---------------------------------------------------------------- tiles (mockup owner 02/09: 4, icone a esquerda)
    db_state = (st.get("database_state") or "").upper()
    used_mb = (log_size_mb * log_used_pct / 100.0) if (log_size_mb and log_used_pct is not None) else None
    ha_degraded = bool(mstate) and mstate not in ("SYNCHRONIZED", "SYNCHRONIZING")
    ha_txt = "DEGRADADA" if ha_degraded else ("A SINCRONIZAR" if mstate == "SYNCHRONIZING" else ("ATIVA" if mstate == "SYNCHRONIZED" else "DESCONHECIDA"))
    send_gb = (send_q / 1048576.0) if send_q is not None else None
    fila_txt = f"{_num(send_gb, 1)} GB" if send_gb is not None else "n/d"
    summary = [
        {"label": "Mirroring", "value": mstate or "?", "sub": ("Mirror não está a receber log" if ha_degraded else ("A drenar a fila para o mirror" if mstate == "SYNCHRONIZING" else "Mirror a receber log")),
         "icon": "fa-database", "severity": "ok" if mstate == "SYNCHRONIZED" else ("critical" if ha_degraded else "warning")},
        {"label": "Log principal", "value": (f"{_num(log_used_pct, 0)}%" if log_used_pct is not None else "n/d"), "sub": (f"{_gb(used_mb)} / {_gb(log_size_mb)}" if log_size_mb else ""),
         "icon": "fa-file-alt", "severity": "critical" if (log_used_pct or 0) >= 70 else ("warning" if (log_used_pct or 0) >= 40 else "ok")},
        {"label": "Fila para o mirror", "value": fila_txt, "sub": "Log Send Queue", "icon": "fa-share-square", "severity": "critical" if (send_gb or 0) >= 10 else ("warning" if (send_q or 0) > 0 else "info")},
        {"label": "Proteção HA", "value": ha_txt, "sub": ("Sem proteção efetiva do mirror" if ha_degraded else ("Redundância ativa" if mstate == "SYNCHRONIZED" else "Redundância a repor")),
         "icon": "fa-shield-alt", "severity": "critical" if ha_degraded else ("ok" if mstate == "SYNCHRONIZED" else "warning")},
    ]
    # ---------------------------------------------------------------- contexto rapido (mockup) + extras atras de "Ver detalhes completos"
    safety = (st.get("mirroring_safety_level_desc") or "?").upper()
    witness_on = bool(st.get("mirroring_witness_name")) and (st.get("mirroring_witness_state_desc") or "").upper() == "CONNECTED"
    side_rows = [
        {"k": "Recovery Model", "v": st.get("recovery_model_desc") or "?"},
        {"k": "Estado da base (Principal)", "v": db_state or "?"},
        {"k": "Mirroring Role (Principal)", "v": role or "?"},
        {"k": "Mirroring Role (Mirror)", "v": (st_m.get("mirroring_role_desc") or ("MIRROR" if partner_inst else "?"))},
        {"k": "Data Safety", "v": safety},
        {"k": "Automatic Failover", "v": "ON" if (witness_on and safety == "FULL") else "OFF"},
        {"k": "Sincronização", "v": "SÍNCRONA" if safety == "FULL" else ("ASSÍNCRONA" if safety == "OFF" else "?")},
        {"k": "Último backup FULL", "v": _fmt_dt_full(last_full) if last_full else "nenhum em 60d"},
        {"k": "Último backup LOG", "v": _fmt_dt_full(last_log_bkp) if last_log_bkp else "nenhum em 60d"},
        {"k": "Tamanho da base", "v": _gb(data_size_mb) if data_size_mb else "?"},
        {"k": "Arquivos do log", "v": _i(st.get("log_file_count"), "?")},
        {"k": "Database", "v": database},
        {"k": "Principal", "v": server_id},
        {"k": "Mirror", "v": partner_inst or "?"},
        {"k": "Estado no mirror", "v": (st_m.get("mirroring_state_desc") or ("não alcançável" if partner_sid else "n/a"))},
        {"k": "Witness", "v": f"{st.get('mirroring_witness_name') or 'nenhum'} ({st.get('mirroring_witness_state_desc') or '-'})"},
        {"k": "Timeout parceiro", "v": f"{_i(st.get('mirroring_connection_timeout'), '?')} s"},
        {"k": "Log ilimitado?", "v": "sim" if int(_n(st.get("log_unlimited"), 0) or 0) == 1 else "não (max_size definido)"},
        {"k": "Origem", "v": "DMV/DBCC/errorlog · " + datetime.now().strftime("%d/%m %H:%M")},
    ]
    if vol_p:
        side_rows.append({"k": "Disco no principal", "v": "; ".join(f"{v.get('volume_mount_point')} {_num(v.get('free_gb'), 1)} GB ({_num(v.get('free_pct'), 1)}%) {v.get('file_type')}" for v in vol_p[:3])})
    if vol_m:
        side_rows.append({"k": "Disco no mirror", "v": "; ".join(f"{v.get('volume_mount_point')} {_num(v.get('free_gb'), 1)} GB ({_num(v.get('free_pct'), 1)}%)" for v in vol_m[:3])})
    _fila_gb = (send_q or 0) / 1048576
    _base_gb = (data_size_mb / 1024) if data_size_mb else 0
    _ratio = (_fila_gb / _base_gb) if _base_gb else 0
    if data_size_mb:
        side_rows.append({"k": "Base da triagem", "v": f"copiar a base (re-seed) = {_num(_base_gb, 1)} GB · drenar a fila (RESUME) = {_num(_fila_gb, 1)} GB" + (f" — fila é {_ratio:.0f}x a base" if _ratio >= 2 else "")})
    # ---------------------------------------------------------------- estrategia sugerida (heuristica) — coluna do meio
    strategy = None
    if triage:
        _is_rb = triage["verdict"] == "REBUILD"
        strategy = {"label": "Estratégia sugerida (por regra)", "icon": "fa-balance-scale",
                    "help": "Regra fixa e explicável, sem IA: compara a fila de log pendente (o que o mirror ainda não recebeu) com o tamanho da base. Se a fila for maior que a base, copiar a base de novo (re-seed) é mais rápido do que drenar a fila; se for menor, o RESUME tende a bastar.",
                    "title": ("Rebuild pode ser mais eficiente" if _is_rb else "RESUME tende a bastar"),
                    "text": (f"Fila pendente ({_num(_fila_gb, 1)} GB) é ~{_ratio:.0f}x maior que o tamanho da base ({_num(_base_gb, 1)} GB). Re-seed tende a ser mais rápido que drenar toda a fila com o mirror suspenso."
                             if _is_rb else f"Fila pendente ({_num(_fila_gb, 1)} GB) é menor que o tamanho da base ({_num(_base_gb, 1)} GB): drenar a fila após RESUME tende a ser viável."),
                    "rows": [{"k": "Send Queue", "v": f"{_num(_fila_gb, 1)} GB"}, {"k": "Tamanho da base", "v": f"{_num(_base_gb, 1)} GB"}, {"k": "Relação", "v": f"{_num(_ratio, 1)}x"}],
                    "details": ([
                        {"t": "Como se decide", "d": f"Fila de log por enviar ({_num(_fila_gb, 1)} GB) contra o tamanho da base ({_num(_base_gb, 1)} GB). Fila maior que a base → re-seed; menor → RESUME."},
                        {"t": "Porquê rebuild", "d": f"Com RESUME o mirror teria de receber e aplicar {_num(_fila_gb, 1)} GB de log; com re-seed copia-se a base ({_num(_base_gb, 1)} GB) via backup FULL + logs e o mirroring recomeça limpo."},
                        {"t": "O que validar antes", "d": "Causa da suspensão resolvida (errorlog do mirror), espaço no mirror, backup FULL + logs disponíveis e janela; o log do principal só trunca depois de SET PARTNER OFF ou de voltar a SYNCHRONIZED."},
                    ] if _is_rb else [
                        {"t": "Como se decide", "d": f"Fila de log por enviar ({_num(_fila_gb, 1)} GB) contra o tamanho da base ({_num(_base_gb, 1)} GB). Fila menor que a base → RESUME; maior → re-seed."},
                        {"t": "Porquê resume", "d": "A fila é pequena face à base: depois de corrigida a causa, o mirror drena o atraso em tempo aceitável e volta a SYNCHRONIZED sem copiar a base."},
                        {"t": "O que validar antes", "d": "Causa da suspensão resolvida (errorlog do mirror) e espaço no mirror; vigiar send/redo queue a descer após o RESUME."},
                    ]),
                    "note": "Validar throughput, backups disponíveis e causa da suspensão antes de executar o rebuild." if _is_rb else "Confirmar a causa da suspensão no errorlog do mirror antes do RESUME.",
                    "link": {"label": "Ver runbook de rebuild", "section": "runbook"}}
    # 2026-09-01: proximo passo abre com a triagem quando ela existe. \n entre
    # itens: o .diag-next tem white-space pre-line (pedido owner 01/09 — itens
    # numerados em linhas proprias, nao paragrafo corrido).
    _lead = (f"TRIAGEM: {triage['verdict']} ({triage['why']}).\n" if triage else "")
    next_step = {"text": _lead
                 + "1) Log do principal (o incendio real).\n"
                 + "2) Errorlog do mirror na janela.\n"
                 + "3) Causa corrigida -> RESUME e vigiar send/redo queue.\n"
                 + "4) Se re-suspender (ou triagem REBUILD) -> rebuild pelo runbook.",
                 "sqlCheck": f"SELECT name, log_reuse_wait_desc FROM sys.databases WHERE name = N'{_esc(database)}';\nDBCC SQLPERF(LOGSPACE);"}

    # 2026-09-02 (mockup owner): banner "DIAGNOSTICO PRINCIPAL" + "desde" (evento
    # 'suspend' mais antigo na janela do errorlog; sem evento = sem "desde").
    _pct_txt = f"{_num(log_used_pct, 0)}%" if log_used_pct is not None else "n/d"
    if mstate in ("SUSPENDED", "DISCONNECTED"):
        _headline = ("MIRRORING INTERROMPIDO ESTÁ IMPEDINDO A REUTILIZAÇÃO DO TRANSACTION LOG" if lrw == "DATABASE_MIRRORING"
                     else f"MIRRORING {mstate} — SEM REDUNDÂNCIA")
        _desc = (f"O mirror está {'suspenso' if mstate == 'SUSPENDED' else 'desligado'}. A fila de envio de log cresceu e o SQL Server não consegue reutilizar o transaction log (log_reuse_wait_desc = {lrw or '?'})."
                 if lrw == "DATABASE_MIRRORING" else f"O mirror está {'suspenso' if mstate == 'SUSPENDED' else 'desligado'}; o principal continua a escrever sem redundância (log_reuse_wait_desc = {lrw or '?'}).")
        _chain = [{"icon": "fa-times-circle", "title": f"Mirroring {mstate}", "sub": "Mirror não recebe novos logs", "sev": "critical"},
                  {"icon": "fa-share-square", "title": "Fila de envio cresce", "sub": f"{fila_txt} pendentes para o mirror", "sev": "warning"},
                  {"icon": "fa-database", "title": f"{lrw or '?'} impede reutilização do log", "sub": "", "sev": "critical"},
                  {"icon": "fa-database", "title": f"Log do Principal {_pct_txt} utilizado", "sub": "Risco de erro 9002 / indisponibilidade", "sev": "critical"}]
        _note = ("O Principal permanece ONLINE e a base continua disponível para leitura/escrita." if db_state == "ONLINE"
                 else f"Base do principal em estado {db_state or '?'} — ver dados brutos.")
    elif mstate == "SYNCHRONIZING":
        _headline = "A RESSINCRONIZAR (A DRENAR A SEND QUEUE)"
        _desc = "O RESUME foi executado; o mirror está a receber e aplicar o log em atraso."
        _chain = [{"icon": "fa-play", "title": "RESUME", "sub": "no Principal", "sev": "info"}, {"icon": "fa-sync-alt", "title": "SYNCHRONIZING", "sub": f"{fila_txt} por enviar", "sev": "warning"},
                  {"icon": "fa-check-circle", "title": "SYNCHRONIZED", "sub": "quando a fila chegar a zero", "sev": "ok"}]
        _note = "Normal após RESUME; vigiar send/redo queue a descer."
    elif mstate == "SYNCHRONIZED":
        _headline = "MIRRORING SINCRONIZADO"
        _desc = "O mirror recebe e aplica o log; redundância ativa."
        _chain = [{"icon": "fa-check-circle", "title": "SYNCHRONIZED", "sub": "", "sev": "ok"}, {"icon": "fa-database", "title": f"log_reuse_wait {lrw or '?'}", "sub": "", "sev": ("ok" if lrw in ("NOTHING", "LOG_BACKUP") else "warning")},
                  {"icon": "fa-share-square", "title": f"fila {fila_txt}", "sub": "", "sev": "info"}]
        _note = "Redundância ativa."
    else:
        _headline = f"MIRRORING {mstate or 'DESCONHECIDO'}"
        _desc = "Estado não reconhecido — ver dados brutos."
        _chain = [{"icon": "fa-question-circle", "title": mstate or "?", "sub": "", "sev": "info"}, {"icon": "fa-database", "title": lrw or "?", "sub": "", "sev": "info"}]
        _note = ""
    _el_all = el_m + el_p
    _susp = sorted([x["when"] for x in _el_all if re.search(r"suspend", x.get("text") or "", re.I) and x.get("when")])
    _vol_log = next((v for v in vol_p if v.get("file_type") == "LOG"), (vol_p[0] if vol_p else None))
    _facts = [
        {"icon": "fa-server", "label": "Principal", "value": db_state or "?", "sev": ("ok" if db_state == "ONLINE" else "warning")},
        {"icon": "fa-clone", "label": "Mirror", "value": (st_m.get("mirroring_state_desc") or mstate or "?"), "sev": ("ok" if mstate == "SYNCHRONIZED" else ("critical" if ha_degraded else "warning"))},
        {"icon": "fa-file-alt", "label": "Log principal", "value": f"{_pct_txt} utilizado", "sev": ("critical" if (log_used_pct or 0) >= 70 else ("warning" if (log_used_pct or 0) >= 40 else "ok"))},
        {"icon": "fa-share-square", "label": "Fila pendente", "value": fila_txt, "sev": ("critical" if (send_gb or 0) >= 10 else ("warning" if (send_q or 0) > 0 else "info"))},
        {"icon": "fa-balance-scale", "label": "log_reuse_wait_desc", "value": lrw or "?", "sev": ("critical" if lrw == "DATABASE_MIRRORING" else "ok")},
        {"icon": "fa-shield-alt", "label": "Proteção HA", "value": ha_txt, "sev": ("critical" if ha_degraded else ("ok" if mstate == "SYNCHRONIZED" else "warning"))},
    ]
    _box = None
    if _vol_log:
        _fp = _n(_vol_log.get("free_pct"))
        _box = {"icon": "fa-hdd", "title": f"Volume do log: {_num(_vol_log.get('free_gb'), 1)} GB livres ({_num(_fp, 0)}%)",
                "sub": ("Existe margem física para atuação." if (_fp or 0) >= 15 else "Margem física escassa — prioridade máxima.")}
    principal = {"label": "Diagnóstico principal", "headline": _headline, "description": _desc, "chain": _chain, "note": _note,
                 "severity": verdict, "icon": ("fa-check" if verdict == "ok" else "fa-exclamation"),
                 "risk": {"label": "Risco atual", "level": verdict, "facts": _facts, "box": _box,
                          "cta": ({"label": "Ver eventos", "section": "errorlog"} if _el_all else None)}}

    _disp = (str(st.get("server_name") or "").strip() or server_id)  # @@SERVERNAME (com barra), nao o server_id do pool
    out["diagnosis"] = {"header": {"title": f"{_disp} (Principal) → {partner_inst or '?'} (Mirror)", "subtitle": f"Recuperação: {st.get('recovery_model_desc') or '?'} • Database: {database}", "verdict": verdict},
                        "since": ({"ts": _susp[0]} if (_susp and mstate in ("SUSPENDED", "DISCONNECTED")) else None),
                        "principal": principal, "strategy": strategy,
                        "summary": summary, "problems": problems, "recommendations": recs,
                        "side": {"title": "Contexto rápido", "rows": side_rows}, "nextStep": next_step}
    out["raw"] = {"principal_state": st, "mirror_state": st_m, "logspace_row": next((r for r in logspace_rows if str(r.get('Database Name') or r.get('database_name')) == database), None),
                  "counters": counters, "errorlog_principal": el_p, "errorlog_mirror": el_m,
                  "principal_volumes": vol_p, "mirror_volumes": vol_m, "auto_page_repair": apr, "triage": triage,
                  "backups": {"last_full": (str(last_full) if last_full else None), "last_log": (str(last_log_bkp) if last_log_bkp else None)}}
    return out
