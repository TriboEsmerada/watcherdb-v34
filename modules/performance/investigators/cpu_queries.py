"""CPUQueriesInvestigator — queries dominantes de CPU + deteccao de parameter sniffing."""

import logging
import time
from typing import Any, Dict, List

from modules.performance.base import (
    InvestigationResult, InvestigationStep, PerformanceInvestigator,
    Recommendation, EstimatedImpact,
    SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO, SEVERITY_OK,
)

logger = logging.getLogger(__name__)


class CPUQueriesInvestigator(PerformanceInvestigator):
    investigator_id = "cpu_queries"
    display_name_pt = "CPU Queries"
    category = "CPU_QUERIES"
    icon = "fa-microchip"
    help_text_pt = (
        "O QUE E: queries que dominam o consumo de CPU no plan cache. Inclui "
        "deteccao de parameter sniffing — condicao em que um plano compilado "
        "para um valor de parametro se torna ineficiente quando reutilizado "
        "com valores diferentes (variacao significativa de logical_reads entre "
        "execucoes do mesmo plano).\n\n"
        "PROBLEMA CAUSADO: CPU elevado reduz capacidade global de processamento "
        "do servidor. Parameter sniffing provoca latencia imprevisivel — a "
        "mesma query executa em 50ms ou em 50s dependendo do valor de "
        "parametro usado na primeira compilacao.\n\n"
        "COMO MEDIMOS: agregado de sys.dm_exec_query_stats. CRITICAL quando "
        "top 5 somam > 100.000.000 ms CPU acumulado; WARNING > 10.000.000 ms. "
        "Parameter sniffing sinalizado quando max_logical_reads / min_logical_reads "
        "para a mesma query excede factor 10."
    )

    THRESHOLD_TOTAL_CPU_MS_CRITICAL = 100_000_000
    THRESHOLD_TOTAL_CPU_MS_WARNING = 10_000_000
    PARAMETER_SNIFFING_RATIO = 10

    def get_steps_schema(self) -> List[Dict[str, str]]:
        return [
            {"id": "step_1_top_total", "label": "Top 20 por CPU acumulado",
             "description_pt": (
                 "total_worker_time desde o ultimo restart ou eviction do plano. "
                 "Reflecte impacto agregado — avaliar em conjunto com "
                 "execution_count para distinguir query pontualmente pesada de "
                 "query frequente."
             )},
            {"id": "step_2_top_avg", "label": "Top 20 por CPU medio por execucao",
             "description_pt": (
                 "avg_worker_time individual. Identifica queries pontualmente "
                 "pesadas em CPU, independentemente da frequencia."
             )},
            {"id": "step_3_recompiles", "label": "Queries com uso repetido do mesmo plano adhoc",
             "description_pt": (
                 "Planos adhoc com usecounts > 20. Sugerem falta de parametrizacao "
                 "na aplicacao (queries concatenam valores em vez de usar "
                 "parametros). Causa pressao no plan cache e recompilacoes."
             )},
            {"id": "step_4_param_sniffing", "label": "Deteccao de parameter sniffing",
             "description_pt": (
                 "Queries cujo mesmo plano executa com variancia significativa "
                 "de logical_reads entre execucoes. Sinal de que o plano "
                 "compilado para um valor se comporta mal para outros valores. "
                 "Mitigacoes: OPTION (RECOMPILE), OPTIMIZE FOR UNKNOWN, plan guide."
             )},
            {"id": "step_5_active_sessions", "label": "Sessoes activas com CPU elevado (tempo real)",
             "description_pt": (
                 "Requests em execucao neste instante com CPU > 5s acumulado. "
                 "Inclui session_id para identificacao e accao imediata (KILL, "
                 "sp_who2, DBCC INPUTBUFFER). Complementa os steps 1-4 que "
                 "mostram historico agregado do plan cache."
             )},
        ]

    async def collect(self, instance: str) -> Dict[str, Any]:
        from api.async_db import async_execute_on_server
        data = {"instance": instance, "steps": {}, "_errors": []}

        # Step 1: top total — com session_id via LEFT JOIN dm_exec_requests
        # (mostra session_id quando a query esta activa AGORA; NULL se nao esta)
        t0 = time.time()
        q1 = """
        SELECT TOP 20
            qs.query_hash, qs.plan_handle, qs.execution_count,
            qs.total_worker_time / 1000 AS total_cpu_ms,
            qs.total_worker_time / NULLIF(qs.execution_count, 0) / 1000 AS avg_cpu_ms,
            qs.total_logical_reads / NULLIF(qs.execution_count, 0) AS avg_logical_reads,
            qs.min_logical_reads, qs.max_logical_reads,
            qs.last_execution_time,
            r.session_id AS active_session_id,
            r.status AS session_status,
            r.cpu_time / 1000 AS session_cpu_seconds,
            s.login_name,
            s.host_name,
            s.program_name,
            SUBSTRING(qt.text, (qs.statement_start_offset/2)+1,
                ((CASE qs.statement_end_offset
                    WHEN -1 THEN DATALENGTH(qt.text)
                    ELSE qs.statement_end_offset END - qs.statement_start_offset)/2)+1
            ) AS sql_text,
            DB_NAME(qt.dbid) AS database_name
        FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
        LEFT JOIN sys.dm_exec_requests r WITH (NOLOCK)
            ON r.plan_handle = qs.plan_handle AND r.session_id > 50
        LEFT JOIN sys.dm_exec_sessions s WITH (NOLOCK)
            ON s.session_id = r.session_id
        ORDER BY qs.total_worker_time DESC
        """
        try:
            rows = await async_execute_on_server(instance, q1) or []
            data["steps"]["step_1_top_total"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q1}
        except Exception as e:
            data["_errors"].append(("step_1_top_total", str(e)))
            data["steps"]["step_1_top_total"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # Step 2: top avg CPU — com session_id via LEFT JOIN
        t0 = time.time()
        q2 = """
        SELECT TOP 20
            qs.query_hash, qs.execution_count,
            qs.total_worker_time / NULLIF(qs.execution_count, 0) / 1000 AS avg_cpu_ms,
            qs.max_worker_time / 1000 AS max_cpu_ms,
            qs.total_logical_reads / NULLIF(qs.execution_count, 0) AS avg_logical_reads,
            qs.last_execution_time,
            r.session_id AS active_session_id,
            r.status AS session_status,
            s.login_name,
            s.program_name,
            SUBSTRING(qt.text, (qs.statement_start_offset/2)+1,
                ((CASE qs.statement_end_offset
                    WHEN -1 THEN DATALENGTH(qt.text)
                    ELSE qs.statement_end_offset END - qs.statement_start_offset)/2)+1
            ) AS sql_text,
            DB_NAME(qt.dbid) AS database_name
        FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
        LEFT JOIN sys.dm_exec_requests r WITH (NOLOCK)
            ON r.plan_handle = qs.plan_handle AND r.session_id > 50
        LEFT JOIN sys.dm_exec_sessions s WITH (NOLOCK)
            ON s.session_id = r.session_id
        WHERE qs.execution_count > 0
        ORDER BY (qs.total_worker_time / NULLIF(qs.execution_count, 0)) DESC
        """
        try:
            rows = await async_execute_on_server(instance, q2) or []
            data["steps"]["step_2_top_avg"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q2}
        except Exception as e:
            data["_errors"].append(("step_2_top_avg", str(e)))
            data["steps"]["step_2_top_avg"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # Step 3: recompiles (via dm_exec_cached_plans + dm_exec_plan_attributes)
        t0 = time.time()
        q3 = """
        SELECT TOP 20
            cp.plan_handle, cp.usecounts, cp.objtype,
            qs.query_hash, qs.execution_count,
            SUBSTRING(qt.text, (qs.statement_start_offset/2)+1,
                ((CASE qs.statement_end_offset
                    WHEN -1 THEN DATALENGTH(qt.text)
                    ELSE qs.statement_end_offset END - qs.statement_start_offset)/2)+1
            ) AS sql_text,
            DB_NAME(qt.dbid) AS database_name
        FROM sys.dm_exec_cached_plans cp WITH (NOLOCK)
        JOIN sys.dm_exec_query_stats qs WITH (NOLOCK) ON cp.plan_handle = qs.plan_handle
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
        WHERE cp.usecounts > 20 AND cp.objtype = 'Adhoc'
        ORDER BY cp.usecounts DESC
        """
        try:
            rows = await async_execute_on_server(instance, q3) or []
            data["steps"]["step_3_recompiles"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q3}
        except Exception as e:
            data["_errors"].append(("step_3_recompiles", str(e)))
            data["steps"]["step_3_recompiles"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # Step 4: parameter sniffing — variancia de reads
        t0 = time.time()
        q4 = """
        SELECT TOP 20
            qs.query_hash, qs.plan_handle, qs.execution_count,
            qs.min_logical_reads, qs.max_logical_reads,
            CAST(qs.max_logical_reads AS FLOAT) / NULLIF(qs.min_logical_reads, 0) AS read_variance_ratio,
            qs.total_worker_time / NULLIF(qs.execution_count, 0) / 1000 AS avg_cpu_ms,
            SUBSTRING(qt.text, (qs.statement_start_offset/2)+1,
                ((CASE qs.statement_end_offset
                    WHEN -1 THEN DATALENGTH(qt.text)
                    ELSE qs.statement_end_offset END - qs.statement_start_offset)/2)+1
            ) AS sql_text,
            DB_NAME(qt.dbid) AS database_name
        FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
        WHERE qs.execution_count > 5
          AND qs.min_logical_reads > 0
          AND (CAST(qs.max_logical_reads AS FLOAT) / NULLIF(qs.min_logical_reads, 0)) > 10
        ORDER BY read_variance_ratio DESC
        """
        try:
            rows = await async_execute_on_server(instance, q4) or []
            data["steps"]["step_4_param_sniffing"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q4}
        except Exception as e:
            data["_errors"].append(("step_4_param_sniffing", str(e)))
            data["steps"]["step_4_param_sniffing"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # Step 5: sessoes activas com CPU elevado AGORA (dm_exec_requests + sessions)
        t0 = time.time()
        q5 = """
        SELECT TOP 20
            r.session_id,
            s.login_name,
            s.host_name,
            s.program_name,
            DB_NAME(r.database_id) AS database_name,
            r.status AS request_status,
            r.command,
            r.cpu_time / 1000 AS cpu_seconds,
            r.total_elapsed_time / 1000 AS elapsed_seconds,
            r.logical_reads,
            r.writes,
            r.wait_type,
            r.wait_time / 1000 AS wait_seconds,
            r.blocking_session_id,
            r.open_transaction_count,
            SUBSTRING(qt.text, (r.statement_start_offset/2)+1,
                ((CASE r.statement_end_offset
                    WHEN -1 THEN DATALENGTH(qt.text)
                    ELSE r.statement_end_offset END - r.statement_start_offset)/2)+1
            ) AS sql_text,
            r.start_time
        FROM sys.dm_exec_requests r WITH (NOLOCK)
        JOIN sys.dm_exec_sessions s WITH (NOLOCK) ON s.session_id = r.session_id
        OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) qt
        WHERE r.session_id > 50
          AND s.is_user_process = 1
          AND (r.cpu_time > 1000 OR r.total_elapsed_time > 10000)
        ORDER BY r.cpu_time DESC
        """
        try:
            rows = await async_execute_on_server(instance, q5) or []
            data["steps"]["step_5_active_sessions"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q5}
        except Exception as e:
            data["_errors"].append(("step_5_active_sessions", str(e)))
            data["steps"]["step_5_active_sessions"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        return data

    async def analyze(self, raw: Dict[str, Any], instance: str) -> InvestigationResult:
        top_total = raw["steps"].get("step_1_top_total", {}).get("data", [])
        top_avg = raw["steps"].get("step_2_top_avg", {}).get("data", [])
        param_sniffing = raw["steps"].get("step_4_param_sniffing", {}).get("data", [])

        top_total_ms = sum((q.get("total_cpu_ms") or 0) for q in top_total[:5])

        if top_total_ms >= self.THRESHOLD_TOTAL_CPU_MS_CRITICAL:
            severity = SEVERITY_CRITICAL
        elif top_total_ms >= self.THRESHOLD_TOTAL_CPU_MS_WARNING:
            severity = SEVERITY_WARNING
        elif top_total_ms > 0:
            severity = SEVERITY_INFO
        else:
            severity = SEVERITY_OK

        count = len(top_total)
        parameter_sniffing_detected = len(param_sniffing) > 0

        root_cause_parts = []
        if top_total:
            w = top_total[0]
            execs = int(w.get("execution_count") or 0)
            db = w.get("database_name")
            db_label = f"em {db}" if db else "em base nao identificada (ad-hoc/sp_executesql)"
            root_cause_parts.append(
                f"Top offender: query {db_label} com "
                f"{(w.get('total_cpu_ms') or 0):,.0f}ms CPU acumulado ({execs} execucoes)."
            )
        if parameter_sniffing_detected:
            root_cause_parts.append(
                f"Parameter sniffing detectado em {len(param_sniffing)} queries — "
                f"variancia de reads superior a 10x."
            )

        root_cause = " ".join(root_cause_parts) or "Sem queries de CPU significativas."

        recs = []
        if severity != SEVERITY_OK and top_total:
            recs.append(Recommendation(
                action="Investigar query plan da top offender",
                effort='low',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt="Abrir plano em SSMS — procurar Table Scans, Hash operators, Sort operators.",
                estimated_impact_pct=70.0, requires_approval=False,
            ))
        if parameter_sniffing_detected:
            recs.append(Recommendation(
                action="Mitigar parameter sniffing",
                effort='medium',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt="OPTION (RECOMPILE), OPTIMIZE FOR UNKNOWN, ou plan guide. Testar em TST.",
                estimated_impact_pct=60.0, requires_approval=True,
            ))

        steps = []
        for schema in self.get_steps_schema():
            sid = schema["id"]
            sdata = raw["steps"].get(sid, {})
            steps.append(InvestigationStep(
                id=sid, label=schema["label"], description_pt=schema["description_pt"],
                data=sdata.get("data", []), query_sql=sdata.get("query", ""),
                duration_ms=sdata.get("duration_ms", 0),
                data_available=not sdata.get("error"), error_pt=sdata.get("error"),
            ))

        return InvestigationResult(
            investigator_id=self.investigator_id, instance=instance, severity=severity,
            count=count,
            subtitle_pt=(
                f"Top {count} / PS: {len(param_sniffing)}" if count else "Sem queries de CPU"
            ),
            executive_summary_pt=(
                f"Top 5 queries em {instance} consomem {top_total_ms:,.0f}ms de CPU acumulado."
                + (f" {len(param_sniffing)} queries com parameter sniffing." if parameter_sniffing_detected else "")
            ),
            business_impact_pt=(
                "CPU dominado por poucas queries — utilizadores outros podem experienciar lentidao."
                if severity in (SEVERITY_CRITICAL, SEVERITY_WARNING) else "Sem impacto significativo."
            ),
            estimated_impact=EstimatedImpact(
                sla_risk="HIGH" if severity == SEVERITY_CRITICAL else ("MEDIUM" if severity == SEVERITY_WARNING else "LOW"),
            ),
            root_cause_pt=root_cause,
            confidence_score=80.0 if count else 90.0,
            recommendations=recs, steps=steps,
            raw_dmv_data={
                "top_total_cpu_ms": top_total_ms,
                "parameter_sniffing_count": len(param_sniffing),
                "parameter_sniffing_detected": parameter_sniffing_detected,
            },
        )
