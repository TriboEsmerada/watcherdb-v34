# -*- coding: utf-8 -*-
"""
POST /api/queries/plan-analysis/{server_id}  — 2026-08-17 (layout Diagnostico)

Responde, de forma HONESTA e deterministica, a "o plano executado e' o melhor?":
  A) comparacao com os OUTROS planos observados para o mesmo query_hash no plan
     cache (sys.dm_exec_query_stats por query_plan_hash): "ha' um plano X vezes
     mais barato observado entre ... e ..." / "e' o mais barato entre N" / "sem
     base de comparacao (1 plano)". Sinal de sniffing = spread min/max no mesmo
     plano.  SQL 2014+.
  B) Query Store (2016+, so' se ligado na DB e com acesso): regressao vs melhor
     plano de 30 dias, planos forcados, force failures; waits por plano (2017+).
  C) analise do XML do plano (statement-level via dm_exec_text_query_plan, cap
     5 MB, <=2 planos por pedido) com modules/performance/plan_analyzer.py; ou de
     um XML colado pelo utilizador (plan_xml) — sem tocar no servidor.
  D) cruzamento dos missing indexes do plano com sys.dm_db_missing_index_*.

Identidade: a do pool (conta do servico), SELECT-only + VIEW SERVER STATE. Nada
e' executado/alterado. DDL so' comentado. Nunca CROSS APPLY dm_exec_query_plan
sobre a DMV inteira. Parse XML fora do event loop (anyio.to_thread).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import anyio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.async_db import async_execute_on_server
from modules.performance.plan_analyzer import analyze_plan_xml, PlanParseError, MAX_XML_BYTES

logger = logging.getLogger(__name__)

router = APIRouter()

_HEX16 = re.compile(r"^(0x)?[0-9a-fA-F]{16}$")
_HEX_PH = re.compile(r"^(0x)?[0-9a-fA-F]{2,128}$")
_IDENT = re.compile(r"^[A-Za-z0-9_\-\.\[\] $#@]{1,256}$")

MIN_EXECS_COMPARABLE = 3
REGRESSION_RATIO = 3.0
QS_WINDOW_DAYS = 30


class PlanAnalysisRequest(BaseModel):
    query_hash: Optional[str] = Field(None, description="hex de 16 (com ou sem 0x), vindo das Heavy/Slow Queries")
    plan_handle: Optional[str] = Field(None, description="hex, opcional (plano actual conhecido)")
    statement_start_offset: Optional[int] = None
    statement_end_offset: Optional[int] = None
    database_name: Optional[str] = None
    plan_xml: Optional[str] = Field(None, description="XML de plano colado pelo utilizador (analise offline)")
    include_xml: bool = True
    include_qs: bool = True


def _hex(v: Optional[str], rx: re.Pattern) -> Optional[str]:
    if not v:
        return None
    v = v.strip()
    if not rx.match(v):
        raise HTTPException(status_code=400, detail="identificador hex invalido")
    return v if v.lower().startswith("0x") else "0x" + v


def _num(v, default=None):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


async def _major_version(server_id: str) -> int:
    try:
        rows = await async_execute_on_server(server_id, "SELECT CAST(PARSENAME(CAST(SERVERPROPERTY('ProductVersion') AS VARCHAR(50)), 4) AS INT) AS major") or []
        return int((rows[0] or {}).get("major") or 0) if rows else 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# A) planos por query_hash no cache
# ---------------------------------------------------------------------------
def _q_plans_by_hash(qh: str) -> str:
    return f"""
DECLARE @qh BINARY(8) = {qh};
DECLARE @min_execs INT = {MIN_EXECS_COMPARABLE};
;WITH p AS (
    SELECT qs.query_plan_hash, qs.plan_handle, qs.sql_handle,
           qs.statement_start_offset, qs.statement_end_offset,
           qs.creation_time, qs.last_execution_time, qs.execution_count,
           qs.total_worker_time, qs.total_elapsed_time, qs.total_logical_reads, qs.total_rows,
           qs.min_worker_time, qs.max_worker_time, qs.min_elapsed_time, qs.max_elapsed_time,
           qs.min_logical_reads, qs.max_logical_reads, qs.min_rows, qs.max_rows,
           ROW_NUMBER() OVER (PARTITION BY qs.query_plan_hash ORDER BY qs.last_execution_time DESC) AS rn
    FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
    WHERE qs.query_hash = @qh
),
agg AS (
    SELECT query_plan_hash,
           COUNT(*) AS cached_entries,
           SUM(execution_count) AS execs,
           SUM(total_worker_time)   * 1.0 / NULLIF(SUM(execution_count),0) / 1000.0 AS avg_cpu_ms,
           SUM(total_elapsed_time)  * 1.0 / NULLIF(SUM(execution_count),0) / 1000.0 AS avg_elapsed_ms,
           SUM(total_logical_reads) * 1.0 / NULLIF(SUM(execution_count),0)          AS avg_reads,
           SUM(total_rows)          * 1.0 / NULLIF(SUM(execution_count),0)          AS avg_rows,
           MIN(min_elapsed_time)/1000.0 AS min_elapsed_ms, MAX(max_elapsed_time)/1000.0 AS max_elapsed_ms,
           MIN(min_logical_reads) AS min_reads, MAX(max_logical_reads) AS max_reads,
           MIN(min_rows) AS min_rows, MAX(max_rows) AS max_rows,
           MIN(creation_time) AS first_seen, MAX(last_execution_time) AS last_seen
    FROM p GROUP BY query_plan_hash
),
best AS (
    SELECT MIN(CASE WHEN execs >= @min_execs THEN avg_cpu_ms END)     AS best_cpu_ms,
           MIN(CASE WHEN execs >= @min_execs THEN avg_reads END)      AS best_reads,
           MIN(CASE WHEN execs >= @min_execs THEN avg_elapsed_ms END) AS best_elapsed_ms,
           COUNT(*) AS plans_total,
           SUM(CASE WHEN execs >= @min_execs THEN 1 ELSE 0 END) AS plans_comparable
    FROM agg
)
SELECT a.query_plan_hash, a.cached_entries, a.execs,
       a.avg_cpu_ms, a.avg_elapsed_ms, a.avg_reads, a.avg_rows,
       a.min_elapsed_ms, a.max_elapsed_ms, a.min_reads, a.max_reads, a.min_rows, a.max_rows,
       a.first_seen, a.last_seen, b.plans_total, b.plans_comparable,
       a.avg_cpu_ms     / NULLIF(b.best_cpu_ms,0)     AS cpu_ratio_vs_best,
       a.avg_reads      / NULLIF(b.best_reads,0)      AS reads_ratio_vs_best,
       a.avg_elapsed_ms / NULLIF(b.best_elapsed_ms,0) AS elapsed_ratio_vs_best,
       CASE WHEN a.execs >= @min_execs AND a.avg_cpu_ms = b.best_cpu_ms THEN 1 ELSE 0 END AS is_best_cpu,
       a.max_elapsed_ms / NULLIF(a.min_elapsed_ms,0) AS elapsed_spread,
       a.max_rows * 1.0 / NULLIF(a.min_rows,0)       AS rows_spread,
       r.plan_handle AS rep_plan_handle, r.statement_start_offset, r.statement_end_offset, r.last_execution_time AS rep_last_exec
FROM agg a CROSS JOIN best b
JOIN p r ON r.query_plan_hash = a.query_plan_hash AND r.rn = 1
ORDER BY a.last_seen DESC;
"""


def _q_plan_xml(ph: str, so: int, eo: int) -> str:
    return f"""
DECLARE @ph VARBINARY(64) = {ph};
DECLARE @so INT = {int(so)}, @eo INT = {int(eo)};
DECLARE @cap INT = {MAX_XML_BYTES};
SELECT DATALENGTH(tqp.query_plan) AS plan_bytes, tqp.dbid, tqp.objectid,
       CASE WHEN DATALENGTH(tqp.query_plan) <= @cap THEN tqp.query_plan END AS query_plan
FROM sys.dm_exec_text_query_plan(@ph, @so, @eo) tqp;
"""


_Q_QS_DBS = """
SELECT d.name, d.is_query_store_on
FROM sys.databases d WITH (NOLOCK)
WHERE d.state = 0 AND d.database_id > 4 AND d.is_query_store_on = 1 AND HAS_DBACCESS(d.name) = 1;
"""

_Q_QS_OPTIONS = """
SELECT actual_state_desc, desired_state_desc, readonly_reason, current_storage_size_mb, max_storage_size_mb,
       stale_query_threshold_days, interval_length_minutes
FROM sys.database_query_store_options;
"""


def _q_qs_plans(qh: str) -> str:
    return f"""
DECLARE @qh BINARY(8) = {qh};
DECLARE @since DATETIMEOFFSET = DATEADD(DAY, -{QS_WINDOW_DAYS}, SYSDATETIMEOFFSET());
;WITH q AS (SELECT query_id FROM sys.query_store_query WITH (NOLOCK) WHERE query_hash = @qh),
ps AS (
    SELECT p.plan_id, p.query_id, p.query_plan_hash, p.is_forced_plan, p.force_failure_count,
           p.last_force_failure_reason_desc, p.is_parallel_plan, p.count_compiles, p.last_execution_time,
           SUM(rs.count_executions) AS execs,
           SUM(rs.avg_cpu_time         * rs.count_executions) / NULLIF(SUM(rs.count_executions),0) / 1000.0 AS avg_cpu_ms,
           SUM(rs.avg_duration         * rs.count_executions) / NULLIF(SUM(rs.count_executions),0) / 1000.0 AS avg_duration_ms,
           SUM(rs.avg_logical_io_reads * rs.count_executions) / NULLIF(SUM(rs.count_executions),0)          AS avg_reads,
           MIN(rsi.start_time) AS first_seen, MAX(rsi.end_time) AS last_seen
    FROM sys.query_store_plan p WITH (NOLOCK)
    JOIN q ON q.query_id = p.query_id
    JOIN sys.query_store_runtime_stats rs WITH (NOLOCK) ON rs.plan_id = p.plan_id
    JOIN sys.query_store_runtime_stats_interval rsi WITH (NOLOCK) ON rsi.runtime_stats_interval_id = rs.runtime_stats_interval_id
    WHERE rsi.start_time >= @since
    GROUP BY p.plan_id, p.query_id, p.query_plan_hash, p.is_forced_plan, p.force_failure_count,
             p.last_force_failure_reason_desc, p.is_parallel_plan, p.count_compiles, p.last_execution_time
)
SELECT TOP 20 ps.*, COUNT(*) OVER () AS plans_in_window,
       ps.avg_cpu_ms      / NULLIF(MIN(CASE WHEN execs >= {MIN_EXECS_COMPARABLE} THEN avg_cpu_ms END)      OVER (),0) AS cpu_ratio_vs_best,
       ps.avg_duration_ms / NULLIF(MIN(CASE WHEN execs >= {MIN_EXECS_COMPARABLE} THEN avg_duration_ms END) OVER (),0) AS duration_ratio_vs_best,
       ps.avg_reads       / NULLIF(MIN(CASE WHEN execs >= {MIN_EXECS_COMPARABLE} THEN avg_reads END)       OVER (),0) AS reads_ratio_vs_best
FROM ps ORDER BY ps.last_seen DESC;
"""


def _q_missing_dmv(db: str, obj: str) -> str:
    db_e = db.replace("'", "''")
    obj_e = obj.replace("'", "''")
    return f"""
DECLARE @db SYSNAME = N'{db_e}', @obj NVARCHAR(400) = N'{obj_e}';
SELECT TOP 20 mid.statement AS object_full, mid.equality_columns, mid.inequality_columns, mid.included_columns,
       migs.user_seeks, migs.user_scans, migs.avg_user_impact, migs.avg_total_user_cost, migs.last_user_seek,
       migs.avg_total_user_cost * (migs.avg_user_impact/100.0) * (migs.user_seeks + migs.user_scans) AS improvement_measure
FROM sys.dm_db_missing_index_details mid WITH (NOLOCK)
JOIN sys.dm_db_missing_index_groups mig WITH (NOLOCK) ON mig.index_handle = mid.index_handle
JOIN sys.dm_db_missing_index_group_stats migs WITH (NOLOCK) ON migs.group_handle = mig.index_group_handle
WHERE mid.database_id = DB_ID(@db) AND mid.object_id = OBJECT_ID(@obj)
ORDER BY improvement_measure DESC;
"""


def _fmt_dt(v) -> str:
    if not v:
        return "?"
    s = str(v)
    return s[:16].replace("T", " ")


def _verdict_from_cache(plans: List[Dict[str, Any]], current_ph: Optional[str]) -> Dict[str, Any]:
    """Texto + severidade do veredicto A) a partir das linhas por query_plan_hash."""
    if not plans:
        return {"text": "Plano ja' nao esta em cache (evicted/flush) — sem base de comparacao no plan cache.", "severity": "info", "kind": "no_cache"}
    plans_total = int(_num(plans[0].get("plans_total"), 0) or 0)
    plans_comp = int(_num(plans[0].get("plans_comparable"), 0) or 0)
    # plano actual = plan_handle dado, senao o mais recente (ordenado por last_seen desc)
    cur = None
    if current_ph:
        for p in plans:
            rp = p.get("rep_plan_handle")
            if rp and str(rp).lower().replace("0x", "") == current_ph.lower().replace("0x", ""):
                cur = p
                break
    cur = cur or plans[0]
    first_seen = _fmt_dt(min((p.get("first_seen") for p in plans if p.get("first_seen")), default=None))
    if plans_total <= 1:
        return {"text": f"Sem base de comparacao no plan cache: 1 plano observado (desde {first_seen}).", "severity": "info", "kind": "single", "current": cur}
    ratio_cpu = _num(cur.get("cpu_ratio_vs_best"))
    ratio_reads = _num(cur.get("reads_ratio_vs_best"))
    ratio_el = _num(cur.get("elapsed_ratio_vs_best"))
    execs = int(_num(cur.get("execs"), 0) or 0)
    if plans_comp == 0 or execs < MIN_EXECS_COMPARABLE:
        return {"text": f"{plans_total} planos em cache, mas sem execucoes suficientes (>= {MIN_EXECS_COMPARABLE}) para comparar com confianca.", "severity": "info", "kind": "insufficient", "current": cur}
    worst_ratio = max(r for r in (ratio_cpu or 1, ratio_reads or 1, ratio_el or 1))
    if worst_ratio >= REGRESSION_RATIO:
        best = min((p for p in plans if int(_num(p.get("execs"), 0) or 0) >= MIN_EXECS_COMPARABLE), key=lambda p: _num(p.get("avg_cpu_ms"), 1e18) or 1e18)
        # robustez: min do actual > max do melhor?
        robust = (_num(cur.get("min_reads"), 0) or 0) > (_num(best.get("max_reads"), 0) or 0)
        metric = "CPU" if (ratio_cpu or 0) >= worst_ratio else ("leituras" if (ratio_reads or 0) >= worst_ratio else "duracao")
        txt = (f"Ha' um plano ~{worst_ratio:.0f}x mais barato em {metric} observado entre {_fmt_dt(best.get('first_seen'))} e {_fmt_dt(best.get('last_seen'))} "
               f"({int(_num(best.get('execs'),0) or 0)} exec.). ")
        txt += "Diferenca robusta (min do actual > max do melhor)." if robust else "Pode reflectir parametros diferentes (intervalos sobrepoem-se) — confirmar antes de agir."
        return {"text": txt, "severity": "critical" if robust else "warning", "kind": "regression", "ratio": worst_ratio, "robust": robust, "current": cur, "best": best}
    if int(_num(cur.get("is_best_cpu"), 0) or 0) == 1 or worst_ratio <= 1.05:
        return {"text": f"Plano actual e' o mais barato entre {plans_total} planos observados no cache (desde {first_seen}); nao garante que seja optimo.", "severity": "ok", "kind": "best", "current": cur}
    return {"text": f"Plano actual e' ~{worst_ratio:.1f}x mais caro que o melhor de {plans_total} planos observados — dentro da margem, sem regressao clara.", "severity": "info", "kind": "close", "current": cur}


@router.post("/plan-analysis/{server_id}")
async def plan_analysis(server_id: str, req: PlanAnalysisRequest) -> Dict[str, Any]:
    out: Dict[str, Any] = {"success": True, "server_id": server_id, "sources": [], "notes": []}
    problems: List[Dict[str, Any]] = []
    recs: List[Dict[str, Any]] = []
    side_rows: List[Dict[str, Any]] = []
    summary: List[Dict[str, Any]] = []
    verdict_text = ""
    verdict_sev = "info"

    qh = _hex(req.query_hash, _HEX16)
    ph = _hex(req.plan_handle, _HEX_PH)
    if req.database_name and not _IDENT.match(req.database_name):
        raise HTTPException(status_code=400, detail="database_name invalido")

    # ---------- C0) XML colado (offline) ----------
    xml_findings = None
    if req.plan_xml:
        try:
            xml_findings = await anyio.to_thread.run_sync(lambda: analyze_plan_xml(req.plan_xml))
            out["sources"].append("plan_xml_pasted")
        except PlanParseError as e:
            raise HTTPException(status_code=400, detail=f"plano XML: {e}")

    plans: List[Dict[str, Any]] = []
    cur_row: Optional[Dict[str, Any]] = None
    if qh:
        # ---------- A) plan cache por query_hash ----------
        try:
            plans = await async_execute_on_server(server_id, _q_plans_by_hash(qh)) or []
            out["sources"].append("dm_exec_query_stats")
        except Exception as e:
            logger.warning(f"plan-analysis {server_id}: cache query failed: {e}")
            out["notes"].append("plan cache indisponivel: " + str(e)[:160])
        v = _verdict_from_cache(plans, ph)
        verdict_text, verdict_sev = v["text"], v["severity"]
        cur_row = v.get("current")
        out["cache_verdict"] = {k: val for k, val in v.items() if k not in ("current", "best")}
        out["plans"] = plans[:20]
        if v.get("kind") == "regression":
            best = v.get("best") or {}
            problems.append({"id": "plan_regression", "title": "Plano actual pior que plano ja' observado", "evidence": v["text"], "impact": "Regressao de plano / parameter sniffing",
                             "icon": "fa-history", "severity": verdict_sev, "source": "history", "confidence": "measured" if v.get("robust") else "heuristic", "recIds": ["plan_rec_regression"],
                             "object_name": str(best.get("query_plan_hash", ""))})
            recs.append({"id": "plan_rec_regression", "title": "Recuperar o plano mais barato", "desc": "Forcar plano (Query Store 2016+) ou recompilar; validar com parametros representativos.",
                         "impact": "very_high", "effort": "low", "problemIds": ["plan_regression"], "icon": "fa-undo",
                         "sqlCheck": ("-- Opcoes (comentadas; escolher UMA apos validar):\n"
                                      "-- EXEC sp_query_store_force_plan @query_id = <id>, @plan_id = <plan_id>;  -- 2016+\n"
                                      f"-- DBCC FREEPROCCACHE ({cur_row.get('rep_plan_handle') if cur_row and cur_row.get('rep_plan_handle') else '<plan_handle>'});  -- expulsa so' este plano\n"
                                      "-- OPTION (RECOMPILE) / OPTIMIZE FOR (...) na query")})
        # sniffing (spread)
        if cur_row:
            sp = _num(cur_row.get("elapsed_spread"), 0) or 0
            rsp = _num(cur_row.get("rows_spread"), 0) or 0
            if sp >= 100 or rsp >= 100:
                problems.append({"id": "plan_spread", "title": "Grande variacao no mesmo plano (sinal de sniffing)", "evidence": f"duracao min..max x{sp:,.0f}; linhas min..max x{rsp:,.0f} ({int(_num(cur_row.get('execs'),0) or 0)} exec.)",
                                 "impact": "Um plano serve bem uns parametros e mal outros", "icon": "fa-wave-square", "severity": "warning", "source": "dmv", "confidence": "measured", "recIds": ["plan_rec_spread"]})
                recs.append({"id": "plan_rec_spread", "title": "Mitigar parameter sniffing", "desc": "RECOMPILE / OPTIMIZE FOR / reescrita por ramos; confirmar com Actual Plan de ambos os casos.", "impact": "high", "effort": "medium", "problemIds": ["plan_spread"], "icon": "fa-code-branch"})
        if cur_row:
            side_rows.append({"k": "Planos em cache (mesmo hash)", "v": f"{int(_num(cur_row.get('plans_total'),0) or 0)} ({int(_num(cur_row.get('plans_comparable'),0) or 0)} comparaveis)"})
            side_rows.append({"k": "Exec. do plano actual", "v": f"{int(_num(cur_row.get('execs'),0) or 0)} · CPU {(_num(cur_row.get('avg_cpu_ms'),0) or 0):,.1f} ms · {(_num(cur_row.get('avg_reads'),0) or 0):,.0f} reads"})

        # ---------- B) Query Store ----------
        if req.include_qs:
            major = await _major_version(server_id)
            out["sql_major"] = major
            if major and major < 13:
                out["notes"].append("Query Store indisponivel (SQL < 2016)")
                side_rows.append({"k": "Query Store", "v": "indisponivel nesta versao"})
            else:
                try:
                    qs_dbs = await async_execute_on_server(server_id, _Q_QS_DBS) or []
                    qs_names = [r.get("name") for r in qs_dbs if r.get("name")]
                    target_db = req.database_name if (req.database_name and req.database_name in qs_names) else None
                    if not target_db:
                        side_rows.append({"k": "Query Store", "v": ("desligado em " + req.database_name) if req.database_name else ("ligado em " + str(len(qs_names)) + " DB(s); indicar database para comparar")})
                    else:
                        opts = await async_execute_on_server(server_id, _Q_QS_OPTIONS, database=target_db) or []
                        st = (opts[0] or {}) if opts else {}
                        qs_rows = await async_execute_on_server(server_id, _q_qs_plans(qh), database=target_db) or []
                        out["sources"].append("query_store")
                        out["query_store"] = {"database": target_db, "state": st.get("actual_state_desc"), "readonly_reason": st.get("readonly_reason"), "plans": qs_rows}
                        side_rows.append({"k": "Query Store", "v": f"{target_db}: {st.get('actual_state_desc') or '?'} · {len(qs_rows)} plano(s)/{QS_WINDOW_DAYS}d"})
                        if str(st.get("actual_state_desc") or "").upper() == "READ_ONLY":
                            problems.append({"id": "qs_ro", "title": "Query Store em READ_ONLY", "evidence": f"reason={st.get('readonly_reason')} · {st.get('current_storage_size_mb')}/{st.get('max_storage_size_mb')} MB", "impact": "Historico deixou de ser gravado", "icon": "fa-database", "severity": "warning", "source": "dmv", "confidence": "measured", "recIds": []})
                        for r in qs_rows:
                            if int(_num(r.get("is_forced_plan"), 0) or 0) == 1 and int(_num(r.get("force_failure_count"), 0) or 0) > 0:
                                problems.append({"id": f"qs_force_{r.get('plan_id')}", "title": "Plano forcado com falhas de forcamento", "evidence": f"plan_id {r.get('plan_id')}: {r.get('force_failure_count')} falhas ({r.get('last_force_failure_reason_desc')})", "impact": "Forcamento nao esta a ser respeitado", "icon": "fa-thumbtack", "severity": "warning", "source": "history", "confidence": "measured", "recIds": []})
                        # regressao QS: plano mais recente vs melhor
                        if qs_rows:
                            latest = qs_rows[0]
                            ratio = max((_num(latest.get("cpu_ratio_vs_best"), 1) or 1), (_num(latest.get("duration_ratio_vs_best"), 1) or 1), (_num(latest.get("reads_ratio_vs_best"), 1) or 1))
                            if ratio >= REGRESSION_RATIO and int(_num(latest.get("plans_in_window"), 0) or 0) > 1:
                                problems.append({"id": "qs_regression", "title": f"Query Store: plano recente ~{ratio:.0f}x mais caro que o melhor de {QS_WINDOW_DAYS}d", "evidence": f"plan_id {latest.get('plan_id')} ({int(_num(latest.get('execs'),0) or 0)} exec.) vs melhor plano da janela", "impact": "Regressao persistente registada", "icon": "fa-history", "severity": "critical", "source": "history", "confidence": "measured", "recIds": ["plan_rec_regression"]})
                                if not any(x["id"] == "plan_rec_regression" for x in recs):
                                    recs.append({"id": "plan_rec_regression", "title": "Recuperar o plano mais barato (Query Store)", "desc": "sp_query_store_force_plan apos validar; monitorizar force failures.", "impact": "very_high", "effort": "low", "problemIds": ["qs_regression"], "icon": "fa-undo", "sqlCheck": "-- EXEC sp_query_store_force_plan @query_id = <query_id>, @plan_id = <plan_id>;  -- validar antes"})
                                if verdict_sev not in ("critical",):
                                    verdict_text = (verdict_text + " " if verdict_text else "") + f"Query Store confirma plano ~{ratio:.0f}x mais caro na janela de {QS_WINDOW_DAYS} dias."
                                    verdict_sev = "critical"
                except Exception as e:
                    logger.warning(f"plan-analysis {server_id}: QS failed: {e}")
                    out["notes"].append("Query Store: " + str(e)[:160])

        # ---------- C) XML do plano actual (statement-level) ----------
        if req.include_xml and not xml_findings:
            rp = ph or (cur_row.get("rep_plan_handle") if cur_row else None)
            so = req.statement_start_offset if req.statement_start_offset is not None else (cur_row.get("statement_start_offset") if cur_row else 0)
            eo = req.statement_end_offset if req.statement_end_offset is not None else (cur_row.get("statement_end_offset") if cur_row else -1)
            if rp:
                try:
                    rp_hex = rp if str(rp).lower().startswith("0x") else "0x" + str(rp)
                    xrows = await async_execute_on_server(server_id, _q_plan_xml(rp_hex, int(so or 0), int(eo if eo is not None else -1))) or []
                    if xrows and xrows[0].get("query_plan"):
                        xml_text = xrows[0]["query_plan"]
                        xml_findings = await anyio.to_thread.run_sync(lambda: analyze_plan_xml(xml_text))
                        out["sources"].append("dm_exec_text_query_plan")
                    elif xrows and (xrows[0].get("plan_bytes") or 0) > MAX_XML_BYTES:
                        out["notes"].append(f"plano demasiado grande ({xrows[0].get('plan_bytes')} bytes) — nao analisado")
                        side_rows.append({"k": "XML do plano", "v": "demasiado grande para analisar"})
                    else:
                        out["notes"].append("plano ja' nao esta em cache — sem XML para analisar")
                except PlanParseError as e:
                    out["notes"].append(f"XML do plano invalido: {e}")
                except Exception as e:
                    logger.warning(f"plan-analysis {server_id}: xml failed: {e}")
                    out["notes"].append("XML do plano: " + str(e)[:160])

    # ---------- D) cruzar missing indexes do plano com DMV ----------
    if xml_findings:
        parsed = xml_findings.get("parsed") or {}
        confirm: Dict[str, Any] = {}
        for mi in (parsed.get("missing_indexes") or [])[:3]:
            db = (mi.get("database") or "").strip("[]")
            tbl = ".".join(p for p in (mi.get("database"), mi.get("schema"), mi.get("table")) if p)
            obj = ".".join(p for p in (mi.get("database"), mi.get("schema"), mi.get("table")) if p)
            if not db or not qh:
                continue
            try:
                drows = await async_execute_on_server(server_id, _q_missing_dmv(db, obj)) or []
                if drows:
                    confirm[tbl] = drows[0]
            except Exception as e:
                out["notes"].append("DMV missing index: " + str(e)[:120])
        if confirm:
            # re-gerar findings com confirmacao
            from modules.performance.plan_analyzer import parse_plan_xml, build_findings  # local import (evitar ciclo)
            try:
                if req.plan_xml:
                    plan_obj = await anyio.to_thread.run_sync(lambda: parse_plan_xml(req.plan_xml))
                    xml_findings = build_findings(plan_obj, {"dmv_missing_index_confirm": confirm})
                    xml_findings["parsed"] = plan_obj.to_dict()
                else:
                    # ja' temos parsed; reconstruir a partir do XML seria outro round-trip — anotar confirmacao nos problemas
                    for p in xml_findings.get("problems", []):
                        c = confirm.get(p.get("object_name"))
                        if c and p.get("icon") == "fa-key":
                            p["evidence"] += f" · DMV: {c.get('user_seeks', 0)} seeks, {c.get('avg_user_impact', 0)}% impacto"
                            p["confidence"] = "measured"
            except Exception:
                pass
            out["sources"].append("dm_db_missing_index_details")
        problems.extend(xml_findings.get("problems", []))
        recs.extend(xml_findings.get("recommendations", []))
        summary.extend(xml_findings.get("summary", []))
        side_rows.extend(xml_findings.get("side_rows", []))
        out["plan_parsed"] = {k: v for k, v in (xml_findings.get("parsed") or {}).items() if k != "operators"}
        out["plan_parsed"]["top_operators"] = (xml_findings.get("parsed") or {}).get("operators", [])[:10]
        if not qh:
            verdict_text = "Analise do XML colado: sem comparacao com outros planos (sem query_hash)." + (" Plano ESTIMADO — sem actual rows/spills." if xml_findings.get("plan_type") == "estimated" else "")
            verdict_sev = "critical" if any(p["severity"] == "critical" for p in problems) else ("warning" if any(p["severity"] == "warning" for p in problems) else "info")

    if not qh and not req.plan_xml:
        raise HTTPException(status_code=400, detail="indicar query_hash (das Heavy/Slow Queries) ou colar plan_xml")

    if not verdict_text:
        verdict_text = "Sem base de comparacao."
    out["plan_analysis"] = {"summary": summary, "problems": problems, "recommendations": recs, "side_rows": side_rows,
                            "verdict_text": verdict_text, "verdict_severity": verdict_sev}
    return out
