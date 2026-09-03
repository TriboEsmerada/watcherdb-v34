"""ProblematicSessionsInvestigator — sessoes com CPU/memoria/duracao altos."""

import logging
import time
from typing import Any, Dict, List

from modules.performance.base import (
    InvestigationResult, InvestigationStep, PerformanceInvestigator,
    Recommendation, EstimatedImpact,
    SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO, SEVERITY_OK,
)

logger = logging.getLogger(__name__)

THRESHOLD_CPU_MS = 60_000
THRESHOLD_MEM_KB = 100 * 1024  # 100 MB
THRESHOLD_DURATION_SEC = 600   # 10 min


class ProblematicSessionsInvestigator(PerformanceInvestigator):
    investigator_id = "problematic_sessions"
    display_name_pt = "Sessoes Problematicas"
    category = "CPU_QUERIES"
    icon = "fa-user-clock"
    help_text_pt = (
        "O QUE E: vista agregada das sessoes activas cujo perfil de consumo "
        "indica anomalia — CPU elevado, memoria concedida elevada, longa duracao "
        "ou espera em wait types criticos. Complementa os investigators "
        "especificos (CPU/Memory/Blocking) oferecendo visao transversal.\n\n"
        "PROBLEMA CAUSADO: sessoes nestas condicoes consomem recursos "
        "desproporcionais ao trabalho util produzido, degradando capacidade do "
        "servidor para sessoes saudaveis. Podem tambem corresponder a sessoes "
        "abandonadas pela aplicacao (sleep com open_transaction_count > 0).\n\n"
        "COMO MEDIMOS: leitura em tempo real de sys.dm_exec_sessions + "
        "sys.dm_exec_requests. Criterios de inclusao: CPU > 60s, memoria > 100 MB, "
        "duracao > 10 min, ou wait_type em lista critica."
    )

    def get_steps_schema(self) -> List[Dict[str, str]]:
        return [
            {"id": "step_1_by_cpu", "label": "Top sessoes por CPU",
             "description_pt": (
                 "Sessoes ordenadas por CPU acumulado desde o login. Valores "
                 "altos em sessoes persistentes podem indicar application pool "
                 "a manter ligacao e executar batch intensivo."
             )},
            {"id": "step_2_by_memory", "label": "Top sessoes por memoria concedida",
             "description_pt": (
                 "Sessoes com maior memoria concedida pelo optimizer. Grants "
                 "elevados reduzem memoria disponivel para outras queries "
                 "(RESOURCE_SEMAPHORE)."
             )},
            {"id": "step_3_problematic_waits", "label": "Sessoes em waits criticos",
             "description_pt": (
                 "Filtra sessoes com wait_type em RESOURCE_SEMAPHORE, "
                 "PAGEIOLATCH_*, WRITELOG, CXPACKET e similares — indicadores "
                 "de contencao de memoria, I/O, log ou paralelismo."
             )},
        ]

    async def collect(self, instance: str) -> Dict[str, Any]:
        from api.async_db import async_execute_on_server
        data = {"instance": instance, "steps": {}, "_errors": []}

        t0 = time.time()
        q_base = """
        SELECT TOP 20 s.session_id, s.login_name, s.host_name, s.program_name,
               s.status, s.cpu_time, s.memory_usage * 8 AS memory_kb,
               s.total_elapsed_time / 1000 AS elapsed_sec,
               r.wait_type, r.blocking_session_id, r.command,
               SUBSTRING(t.text, (r.statement_start_offset/2)+1,
                   ((CASE r.statement_end_offset
                       WHEN -1 THEN DATALENGTH(t.text)
                       ELSE r.statement_end_offset END - r.statement_start_offset)/2)+1
               ) AS sql_text
        FROM sys.dm_exec_sessions s WITH (NOLOCK)
        LEFT JOIN sys.dm_exec_requests r WITH (NOLOCK) ON s.session_id = r.session_id
        OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
        WHERE s.is_user_process = 1
          AND s.session_id <> @@SPID
        """
        q1 = q_base + " ORDER BY s.cpu_time DESC"
        try:
            rows = await async_execute_on_server(instance, q1) or []
            data["steps"]["step_1_by_cpu"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q1}
        except Exception as e:
            data["_errors"].append(("step_1_by_cpu", str(e)))
            data["steps"]["step_1_by_cpu"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        t0 = time.time()
        q2 = q_base + " ORDER BY s.memory_usage DESC"
        try:
            rows = await async_execute_on_server(instance, q2) or []
            data["steps"]["step_2_by_memory"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q2}
        except Exception as e:
            data["_errors"].append(("step_2_by_memory", str(e)))
            data["steps"]["step_2_by_memory"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        t0 = time.time()
        q3 = """
        SELECT TOP 20 s.session_id, s.login_name, s.program_name, r.wait_type,
               r.wait_time / 1000 AS wait_sec, r.command, r.cpu_time,
               DB_NAME(r.database_id) AS database_name,
               SUBSTRING(t.text, (r.statement_start_offset/2)+1,
                   ((CASE r.statement_end_offset
                       WHEN -1 THEN DATALENGTH(t.text)
                       ELSE r.statement_end_offset END - r.statement_start_offset)/2)+1
               ) AS sql_text
        FROM sys.dm_exec_sessions s WITH (NOLOCK)
        JOIN sys.dm_exec_requests r WITH (NOLOCK) ON s.session_id = r.session_id
        OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
        WHERE r.wait_type IN ('RESOURCE_SEMAPHORE', 'PAGEIOLATCH_SH', 'PAGEIOLATCH_EX',
                              'LCK_M_X', 'LCK_M_U', 'CXPACKET', 'ASYNC_NETWORK_IO')
          AND r.wait_time > 5000
        ORDER BY r.wait_time DESC
        """
        try:
            rows = await async_execute_on_server(instance, q3) or []
            data["steps"]["step_3_problematic_waits"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q3}
        except Exception as e:
            data["_errors"].append(("step_3_problematic_waits", str(e)))
            data["steps"]["step_3_problematic_waits"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        return data

    async def analyze(self, raw: Dict[str, Any], instance: str) -> InvestigationResult:
        by_cpu = raw["steps"].get("step_1_by_cpu", {}).get("data", [])
        by_mem = raw["steps"].get("step_2_by_memory", {}).get("data", [])
        bad_waits = raw["steps"].get("step_3_problematic_waits", {}).get("data", [])

        high_cpu = [s for s in by_cpu if (s.get("cpu_time") or 0) > THRESHOLD_CPU_MS]
        high_mem = [s for s in by_mem if (s.get("memory_kb") or 0) > THRESHOLD_MEM_KB]
        long_running = [s for s in by_cpu if (s.get("elapsed_sec") or 0) > THRESHOLD_DURATION_SEC]

        total = len(set([s.get("session_id") for s in high_cpu + high_mem + long_running + bad_waits
                          if s.get("session_id")]))

        if total >= 10 or len(bad_waits) >= 5:
            severity = SEVERITY_CRITICAL
        elif total >= 3:
            severity = SEVERITY_WARNING
        elif total > 0:
            severity = SEVERITY_INFO
        else:
            severity = SEVERITY_OK

        root_cause = "Sem sessoes problematicas." if severity == SEVERITY_OK else (
            f"{len(high_cpu)} sessoes com CPU>60s, {len(high_mem)} com memoria>100MB, "
            f"{len(long_running)} com duracao>10min, {len(bad_waits)} em waits problematicos."
        )

        recs = []
        if bad_waits:
            top = bad_waits[0]
            recs.append(Recommendation(
                action=f"Investigar SPID {top.get('session_id')} em wait {top.get('wait_type')}",
                effort='low',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt=f"Sessao em wait ha {top.get('wait_sec')}s — verificar causa root (ver runbook).",
                estimated_impact_pct=60.0, requires_approval=False,
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
            count=total,
            subtitle_pt=(
                f"{len(high_cpu)} CPU / {len(high_mem)} MEM / {len(long_running)} long" if total else "Sem sessoes problematicas"
            ),
            executive_summary_pt=(
                f"{total} sessoes problematicas em {instance}."
            ) if total else f"{instance} — carga normal.",
            business_impact_pt=(
                "Recursos consumidos por sessoes individuais podem afectar outros utilizadores."
                if severity in (SEVERITY_CRITICAL, SEVERITY_WARNING) else "Sem impacto."
            ),
            estimated_impact=EstimatedImpact(
                users_affected=total,
                sla_risk="HIGH" if severity == SEVERITY_CRITICAL else ("MEDIUM" if severity == SEVERITY_WARNING else "LOW"),
            ),
            root_cause_pt=root_cause,
            confidence_score=75.0 if total else 90.0,
            recommendations=recs, steps=steps,
            raw_dmv_data={"high_cpu": len(high_cpu), "high_mem": len(high_mem),
                          "long_running": len(long_running), "bad_waits": len(bad_waits)},
        )
