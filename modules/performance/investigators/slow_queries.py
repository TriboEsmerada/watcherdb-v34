"""SlowQueriesInvestigator — queries com elapsed_time elevado.

Le sys.dm_exec_query_stats + sys.dm_exec_sql_text directamente na instancia
via async_execute_on_server.
"""

import logging
import time
from typing import Any, Dict, List

from modules.performance.base import (
    InvestigationResult,
    InvestigationStep,
    PerformanceInvestigator,
    Recommendation,
    EstimatedImpact,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    SEVERITY_OK,
)

logger = logging.getLogger(__name__)


class SlowQueriesInvestigator(PerformanceInvestigator):
    investigator_id = "slow_queries"
    display_name_pt = "Queries Lentas"
    category = "CPU_QUERIES"
    icon = "fa-hourglass-half"
    help_text_pt = (
        "O QUE E: queries do plan cache com tempo de execucao elevado. Incluem "
        "tambem regressoes silenciosas — queries cujo tempo actual excede "
        "significativamente a media historica mas ainda nao violam o threshold "
        "absoluto de alerta.\n\n"
        "PROBLEMA CAUSADO: latencia percebida pelo utilizador aumenta, risco de "
        "violacao de SLA, consumo de recursos do servidor desproporcional ao "
        "resultado entregue.\n\n"
        "COMO MEDIMOS: agregado do plan cache (sys.dm_exec_query_stats). Inclui "
        "queries com avg_elapsed_time >= 5s OU max_elapsed_time >= 30s. "
        "Comparacao com baseline 7d/30d para deteccao de regressao silenciosa."
    )

    THRESHOLD_AVG_MS = 5_000
    THRESHOLD_MAX_MS = 30_000

    def get_steps_schema(self) -> List[Dict[str, str]]:
        return [
            {"id": "step_1_top_total_cpu", "label": "Top 20 por CPU total",
             "description_pt": (
                 "Agregado desde o ultimo restart ou eviction do plano. Uma query "
                 "executada 1000 vezes com 10ms cada pode dominar este ranking "
                 "pelo impacto agregado — avaliar sempre execution_count em "
                 "conjunto com avg_elapsed_time."
             )},
            {"id": "step_2_top_avg_elapsed", "label": "Top 20 por duracao media",
             "description_pt": (
                 "Queries mais lentas por execucao individual. Relevante para "
                 "identificar queries pontualmente pesadas, independentemente da "
                 "frequencia de execucao."
             )},
            {"id": "step_3_active_now", "label": "Execucoes activas no momento",
             "description_pt": (
                 "Requests em execucao neste instante com tempo decorrido. "
                 "Fotografia pontual — queries rapidas podem nao aparecer aqui "
                 "mesmo sendo frequentes."
             )},
        ]

    async def collect(self, instance: str) -> Dict[str, Any]:
        from api.async_db import async_execute_on_server

        data = {"instance": instance, "steps": {}, "_errors": []}

        # Step 1: top total_worker_time
        t0 = time.time()
        q1 = """
        SELECT TOP 20
            qs.sql_handle, qs.query_hash, qs.query_plan_hash, qs.plan_handle,
            qs.statement_start_offset, qs.statement_end_offset,
            qs.execution_count,
            qs.total_worker_time / 1000 AS total_cpu_ms,
            qs.total_worker_time / qs.execution_count / 1000 AS avg_cpu_ms,
            qs.total_elapsed_time / qs.execution_count / 1000 AS avg_elapsed_ms,
            qs.total_logical_reads / qs.execution_count AS avg_logical_reads,
            qs.last_execution_time,
            SUBSTRING(qt.text,
                (qs.statement_start_offset/2)+1,
                ((CASE qs.statement_end_offset
                    WHEN -1 THEN DATALENGTH(qt.text)
                    ELSE qs.statement_end_offset END - qs.statement_start_offset)/2)+1
            ) AS sql_text,
            DB_NAME(qt.dbid) AS database_name
        FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
        ORDER BY qs.total_worker_time DESC
        """
        try:
            rows = await async_execute_on_server(instance, q1) or []
            data["steps"]["step_1_top_total_cpu"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q1}
        except Exception as e:
            data["_errors"].append(("step_1_top_total_cpu", str(e)))
            data["steps"]["step_1_top_total_cpu"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # Step 2: top avg_elapsed_time
        t0 = time.time()
        q2 = """
        SELECT TOP 20
            qs.query_hash,
            qs.execution_count,
            qs.total_elapsed_time / qs.execution_count / 1000 AS avg_elapsed_ms,
            qs.max_elapsed_time / 1000 AS max_elapsed_ms,
            qs.total_worker_time / qs.execution_count / 1000 AS avg_cpu_ms,
            qs.last_execution_time,
            SUBSTRING(qt.text,
                (qs.statement_start_offset/2)+1,
                ((CASE qs.statement_end_offset
                    WHEN -1 THEN DATALENGTH(qt.text)
                    ELSE qs.statement_end_offset END - qs.statement_start_offset)/2)+1
            ) AS sql_text,
            DB_NAME(qt.dbid) AS database_name
        FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
        WHERE (qs.total_elapsed_time / qs.execution_count / 1000) >= 1000
        ORDER BY avg_elapsed_ms DESC
        """
        try:
            rows = await async_execute_on_server(instance, q2) or []
            data["steps"]["step_2_top_avg_elapsed"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q2}
        except Exception as e:
            data["_errors"].append(("step_2_top_avg_elapsed", str(e)))
            data["steps"]["step_2_top_avg_elapsed"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # Step 3: active now
        t0 = time.time()
        q3 = """
        SELECT TOP 20
            r.session_id, r.status, r.command, r.wait_type, r.blocking_session_id,
            r.cpu_time, r.total_elapsed_time / 1000 AS elapsed_sec,
            r.logical_reads, DB_NAME(r.database_id) AS database_name,
            SUBSTRING(t.text, (r.statement_start_offset/2)+1,
                ((CASE r.statement_end_offset
                    WHEN -1 THEN DATALENGTH(t.text)
                    ELSE r.statement_end_offset END - r.statement_start_offset)/2)+1
            ) AS sql_text
        FROM sys.dm_exec_requests r WITH (NOLOCK)
        CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
        WHERE r.session_id > 50 AND r.session_id <> @@SPID
        ORDER BY r.total_elapsed_time DESC
        """
        try:
            rows = await async_execute_on_server(instance, q3) or []
            data["steps"]["step_3_active_now"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q3}
        except Exception as e:
            data["_errors"].append(("step_3_active_now", str(e)))
            data["steps"]["step_3_active_now"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        return data

    async def analyze(self, raw: Dict[str, Any], instance: str) -> InvestigationResult:
        total_cpu = raw["steps"].get("step_1_top_total_cpu", {}).get("data", [])
        avg_elapsed = raw["steps"].get("step_2_top_avg_elapsed", {}).get("data", [])
        active = raw["steps"].get("step_3_active_now", {}).get("data", [])

        # Contar queries lentas (avg >= 5s OR max >= 30s)
        slow = [q for q in avg_elapsed
                if (q.get("avg_elapsed_ms", 0) >= self.THRESHOLD_AVG_MS
                    or q.get("max_elapsed_ms", 0) >= self.THRESHOLD_MAX_MS)]

        databases = set()
        for q in slow:
            db = q.get("database_name")
            if db:
                databases.add(db)

        count = len(slow)
        # Severity
        if count >= 10:
            severity = SEVERITY_CRITICAL
        elif count >= 3:
            severity = SEVERITY_WARNING
        elif count > 0:
            severity = SEVERITY_INFO
        else:
            severity = SEVERITY_OK

        # Worst offender
        worst = slow[0] if slow else None
        root_cause = "Sem queries lentas detectadas."
        confidence = 90.0
        if worst:
            worst_ms = worst.get("avg_elapsed_ms", 0)
            execs = int(worst.get("execution_count") or 0)
            db = worst.get("database_name")
            db_label = f"na base {db}" if db else "em base nao identificada (query ad-hoc ou sp_executesql)"
            root_cause = (
                f"Query dominante: avg {worst_ms:.0f}ms, "
                f"executada {execs}x {db_label}. "
                f"Representa impacto principal."
            )
            confidence = 70.0 if count >= 3 else 55.0

        recs: List[Recommendation] = []
        if count > 0:
            recs.append(Recommendation(
                action="Investigar query plan das top 3 queries",
                effort='low',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt="Abrir SSMS e examinar o plano de execucao. Procurar Table Scans e missing index hints.",
                estimated_impact_pct=60.0,
                requires_approval=False,
            ))
            recs.append(Recommendation(
                action="Cruzar com Missing Indexes",
                effort='low',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt="Abrir o card Missing Indexes — frequentemente a causa raiz de queries lentas.",
                estimated_impact_pct=70.0,
                requires_approval=True,
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
            subtitle_pt=f"{count} queries >{self.THRESHOLD_AVG_MS//1000}s em {len(databases)} DBs" if count else "Sem queries lentas",
            executive_summary_pt=(
                f"{count} queries lentas detectadas em {instance}, afectando {len(databases)} databases. "
                f"Severity: {severity}."
            ) if count else f"{instance} — sem queries lentas detectadas.",
            business_impact_pt=(
                f"Latencia >5s percebida pelos utilizadores em {len(databases)} DBs."
                if count >= 3 else "Impacto pontual, utilizadores podem notar lentidao em operacoes especificas."
            ) if count else "Sem impacto.",
            estimated_impact=EstimatedImpact(
                databases_affected=len(databases),
                sla_risk="HIGH" if severity == SEVERITY_CRITICAL else ("MEDIUM" if severity == SEVERITY_WARNING else "LOW"),
            ),
            root_cause_pt=root_cause, confidence_score=confidence,
            recommendations=recs, steps=steps,
            raw_dmv_data={"slow_count": count, "databases": list(databases)},
        )
