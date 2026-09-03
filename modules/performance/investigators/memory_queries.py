"""MemoryQueriesInvestigator — queries com grants de memoria elevados e waits.

Detecta:
- Sessoes activas com memoria concedida (granted) > 100MB
- RESOURCE_SEMAPHORE waits (espera por memoria)
- Optimizer a sobrestimar (granted >> used)
- Queries no plan cache com maior used_grant_kb total
"""

import logging
import time
from typing import Any, Dict, List

from modules.performance.base import (
    InvestigationResult, InvestigationStep, PerformanceInvestigator,
    Recommendation, EstimatedImpact,
    SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO, SEVERITY_OK,
)

logger = logging.getLogger(__name__)


class MemoryQueriesInvestigator(PerformanceInvestigator):
    investigator_id = "memory_queries"
    display_name_pt = "Memory Queries"
    category = "CPU_QUERIES"
    icon = "fa-memory"
    help_text_pt = (
        "O QUE E: queries cujo perfil revela pressao de memoria — grants "
        "elevados concedidos pelo optimizer, espera em RESOURCE_SEMAPHORE, ou "
        "desalinhamento significativo entre memoria concedida e memoria "
        "efectivamente usada (overestimation).\n\n"
        "PROBLEMA CAUSADO: grants excessivos reduzem memoria disponivel para "
        "outras queries, que acabam em fila (RESOURCE_SEMAPHORE). Timeouts no "
        "cliente, latencia elevada. Overestimation sistematica indica "
        "statistics desactualizadas ou cardinality estimator a divergir da "
        "realidade.\n\n"
        "COMO MEDIMOS: combina dm_exec_query_memory_grants (grants activos), "
        "dm_exec_requests (waits RESOURCE_SEMAPHORE*) e agregado do plan cache "
        "(granted/used ratio > 5 em queries historicas). CRITICAL se houver "
        "waits em RESOURCE_SEMAPHORE ou grants >= 1 GB; WARNING se grants "
        ">= 100 MB; INFO apenas com overestimation."
    )

    THRESHOLD_GRANTED_KB_CRITICAL = 1024 * 1024  # 1 GB
    THRESHOLD_GRANTED_KB_WARNING = 100 * 1024    # 100 MB

    def get_steps_schema(self) -> List[Dict[str, str]]:
        return [
            {"id": "step_1_active_grants", "label": "Memory grants activos",
             "description_pt": (
                 "Sessoes com memoria efectivamente concedida neste instante. "
                 "Nota: fotografia pontual — queries rapidas podem nao aparecer "
                 "mesmo sendo regulares. Cruzar com step 3 para visao historica."
             )},
            {"id": "step_2_semaphore_waits", "label": "Sessoes em RESOURCE_SEMAPHORE",
             "description_pt": (
                 "Sessoes em espera por atribuicao de grant. Indica que a "
                 "memoria query workspace do SQL Server ja nao comporta "
                 "concessao imediata — sinal de pressao real."
             )},
            {"id": "step_3_overestimation", "label": "Queries com granted muito superior a used",
             "description_pt": (
                 "Historico do plan cache onde granted_kb / used_kb > 5. "
                 "Indica que o optimizer esta a reservar mais memoria do que a "
                 "query efectivamente consome — desperdica capacidade que "
                 "podia servir outras sessoes. Causa comum: statistics "
                 "desactualizadas."
             )},
        ]

    async def collect(self, instance: str) -> Dict[str, Any]:
        from api.async_db import async_execute_on_server
        data = {"instance": instance, "steps": {}, "_errors": []}

        # Step 1: active grants
        t0 = time.time()
        q1 = """
        SELECT
            mg.session_id, mg.request_id,
            mg.requested_memory_kb, mg.granted_memory_kb,
            mg.required_memory_kb, mg.used_memory_kb,
            mg.max_used_memory_kb, mg.grant_time, mg.wait_time_ms,
            mg.dop, mg.wait_order, mg.is_small,
            s.login_name, s.host_name, s.program_name,
            DB_NAME(r.database_id) AS database_name,
            SUBSTRING(t.text, (r.statement_start_offset/2)+1,
                ((CASE r.statement_end_offset
                    WHEN -1 THEN DATALENGTH(t.text)
                    ELSE r.statement_end_offset END - r.statement_start_offset)/2)+1
            ) AS sql_text
        FROM sys.dm_exec_query_memory_grants mg WITH (NOLOCK)
        LEFT JOIN sys.dm_exec_sessions s WITH (NOLOCK) ON s.session_id = mg.session_id
        LEFT JOIN sys.dm_exec_requests r WITH (NOLOCK) ON r.session_id = mg.session_id
        OUTER APPLY sys.dm_exec_sql_text(COALESCE(r.sql_handle, mg.sql_handle)) t
        ORDER BY mg.granted_memory_kb DESC
        """
        try:
            rows = await async_execute_on_server(instance, q1) or []
            data["steps"]["step_1_active_grants"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q1}
        except Exception as e:
            data["_errors"].append(("step_1_active_grants", str(e)))
            data["steps"]["step_1_active_grants"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # Step 2: RESOURCE_SEMAPHORE waits
        t0 = time.time()
        q2 = """
        SELECT TOP 20
            r.session_id, r.wait_type, r.wait_time / 1000 AS wait_sec,
            r.cpu_time, r.total_elapsed_time / 1000 AS elapsed_sec,
            s.login_name, s.program_name, s.host_name,
            DB_NAME(r.database_id) AS database_name,
            SUBSTRING(t.text, (r.statement_start_offset/2)+1,
                ((CASE r.statement_end_offset
                    WHEN -1 THEN DATALENGTH(t.text)
                    ELSE r.statement_end_offset END - r.statement_start_offset)/2)+1
            ) AS sql_text
        FROM sys.dm_exec_requests r WITH (NOLOCK)
        JOIN sys.dm_exec_sessions s WITH (NOLOCK) ON s.session_id = r.session_id
        OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
        WHERE r.wait_type LIKE 'RESOURCE_SEMAPHORE%'
        ORDER BY r.wait_time DESC
        """
        try:
            rows = await async_execute_on_server(instance, q2) or []
            data["steps"]["step_2_semaphore_waits"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q2}
        except Exception as e:
            data["_errors"].append(("step_2_semaphore_waits", str(e)))
            data["steps"]["step_2_semaphore_waits"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # Step 3: queries no plan cache com maior granted vs used
        # SQL Server 2016+ tem these columns em dm_exec_query_stats
        t0 = time.time()
        q3 = """
        SELECT TOP 20
            qs.query_hash,
            qs.execution_count,
            qs.total_grant_kb / NULLIF(qs.execution_count, 0) AS avg_granted_kb,
            qs.total_used_grant_kb / NULLIF(qs.execution_count, 0) AS avg_used_kb,
            qs.total_ideal_grant_kb / NULLIF(qs.execution_count, 0) AS avg_ideal_kb,
            CAST(qs.total_grant_kb AS FLOAT) / NULLIF(qs.total_used_grant_kb, 0) AS overestimation_ratio,
            qs.total_worker_time / NULLIF(qs.execution_count, 0) / 1000 AS avg_cpu_ms,
            SUBSTRING(qt.text, (qs.statement_start_offset/2)+1,
                ((CASE qs.statement_end_offset
                    WHEN -1 THEN DATALENGTH(qt.text)
                    ELSE qs.statement_end_offset END - qs.statement_start_offset)/2)+1
            ) AS sql_text,
            DB_NAME(qt.dbid) AS database_name
        FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
        WHERE qs.total_grant_kb > 0
          AND qs.total_used_grant_kb > 0
          AND (CAST(qs.total_grant_kb AS FLOAT) / NULLIF(qs.total_used_grant_kb, 0)) > 5
        ORDER BY qs.total_grant_kb DESC
        """
        try:
            rows = await async_execute_on_server(instance, q3) or []
            data["steps"]["step_3_overestimation"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q3}
        except Exception as e:
            data["_errors"].append(("step_3_overestimation", str(e)))
            data["steps"]["step_3_overestimation"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        return data

    async def analyze(self, raw: Dict[str, Any], instance: str) -> InvestigationResult:
        grants = raw["steps"].get("step_1_active_grants", {}).get("data", [])
        sem_waits = raw["steps"].get("step_2_semaphore_waits", {}).get("data", [])
        overest = raw["steps"].get("step_3_overestimation", {}).get("data", [])

        big_grants = [g for g in grants if (g.get("granted_memory_kb") or 0) >= self.THRESHOLD_GRANTED_KB_WARNING]
        huge_grants = [g for g in grants if (g.get("granted_memory_kb") or 0) >= self.THRESHOLD_GRANTED_KB_CRITICAL]

        if sem_waits or huge_grants:
            severity = SEVERITY_CRITICAL
        elif big_grants:
            severity = SEVERITY_WARNING
        elif overest:
            severity = SEVERITY_INFO
        else:
            severity = SEVERITY_OK

        count = len(big_grants) + len(sem_waits)

        root_cause = "Sem pressao de memoria em queries."
        confidence = 85.0
        if sem_waits:
            root_cause = f"{len(sem_waits)} sessoes em RESOURCE_SEMAPHORE — pressao de memoria real. Queries estao a esperar grant."
            confidence = 90.0
        elif huge_grants:
            top = huge_grants[0]
            db = top.get("database_name")
            db_label = f"em {db}" if db else "em base nao identificada (ad-hoc/sp_executesql)"
            root_cause = (
                f"Top grant: {(top.get('granted_memory_kb') or 0)/1024:.0f} MB concedido "
                f"(used: {(top.get('used_memory_kb') or 0)/1024:.0f} MB) {db_label}."
            )
            confidence = 75.0
        elif overest:
            top = overest[0]
            root_cause = (
                f"Optimizer a sobrestimar em {len(overest)} queries (top: {(top.get('overestimation_ratio') or 0):.1f}x). "
                f"Verificar UPDATE STATISTICS."
            )
            confidence = 70.0

        recs: List[Recommendation] = []
        if sem_waits:
            recs.append(Recommendation(
                action="Aumentar memoria OU reduzir MAXDOP",
                effort='low',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt="Sessoes em espera por grant — OS memory pode estar esgotada. Considerar aumentar max_server_memory ou reduzir paralelismo.",
                estimated_impact_pct=60.0, requires_approval=True,
                risk_if_ignored_pt="Queries continuarao a esperar — timeouts no cliente.",
            ))
        if overest:
            recs.append(Recommendation(
                action="UPDATE STATISTICS nas tabelas afectadas",
                effort='low',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt="Optimizer sobrestima quando stats sao antigas. Correr UPDATE STATISTICS com FULLSCAN em off-hours.",
                estimated_impact_pct=50.0, requires_approval=False,
                risk_if_ignored_pt="Queries continuam a alocar grants excessivos, bloqueando outras sessoes.",
            ))
        if huge_grants:
            recs.append(Recommendation(
                action="Investigar top query com grant > 1GB",
                effort='low',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt="Abrir plan em SSMS — procurar Hash Match/Sort operators com memoria excessiva. Considerar hint MIN_GRANT_PERCENT.",
                estimated_impact_pct=70.0, requires_approval=True,
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
                f"{len(huge_grants)} huge / {len(big_grants)} big / {len(sem_waits)} waiting"
                if count else "Sem pressao de memoria"
            ),
            executive_summary_pt=(
                f"{count} queries com consumo elevado de memoria em {instance}."
                + (f" {len(sem_waits)} em RESOURCE_SEMAPHORE." if sem_waits else "")
            ) if count else f"{instance} — memoria sob controlo.",
            business_impact_pt=(
                "Pressao de memoria provoca queries lentas e timeouts intermitentes."
                if severity in (SEVERITY_CRITICAL, SEVERITY_WARNING) else "Sem impacto."
            ),
            estimated_impact=EstimatedImpact(
                users_affected=len(sem_waits),
                sla_risk="HIGH" if severity == SEVERITY_CRITICAL else ("MEDIUM" if severity == SEVERITY_WARNING else "LOW"),
            ),
            root_cause_pt=root_cause, confidence_score=confidence,
            recommendations=recs, steps=steps,
            raw_dmv_data={
                "huge_grants_count": len(huge_grants),
                "big_grants_count": len(big_grants),
                "semaphore_waits": len(sem_waits),
                "overestimation_count": len(overest),
            },
        )
