"""BlockingChainsInvestigator — cadeias de bloqueio activas na instancia."""

import logging
import time
from typing import Any, Dict, List

from modules.performance.base import (
    InvestigationResult, InvestigationStep, PerformanceInvestigator,
    Recommendation, EstimatedImpact,
    SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO, SEVERITY_OK,
)

logger = logging.getLogger(__name__)


class BlockingChainsInvestigator(PerformanceInvestigator):
    investigator_id = "blocking_chains"
    display_name_pt = "Blocking Chains"
    category = "LOCKS"
    icon = "fa-link"
    help_text_pt = (
        "O QUE E: estrutura em cadeia onde uma sessao (lead blocker) detem um "
        "lock nao compativel com o que outras sessoes (vitimas) pretendem "
        "adquirir. As vitimas podem, por sua vez, bloquear terceiros, formando "
        "uma cadeia com potencial crescimento exponencial.\n\n"
        "PROBLEMA CAUSADO: as vitimas ficam suspensas ate o lead blocker libertar "
        "o lock. Transacoes aplicacionais acumulam latencia e podem atingir "
        "timeouts configurados no cliente. Diferente de deadlock (SQL Server "
        "nao termina a transacao automaticamente): a cadeia persiste ate "
        "intervencao manual ou commit/rollback voluntario.\n\n"
        "COMO MEDIMOS: leitura em tempo real de sys.dm_exec_requests cruzada com "
        "sys.dm_os_waiting_tasks. Severity: CRITICAL quando uma cadeia tem mais "
        "de 5 vitimas; WARNING com 2-5; INFO com 1."
    )

    def get_steps_schema(self) -> List[Dict[str, str]]:
        return [
            {"id": "step_1_chains", "label": "Cadeias de bloqueio activas",
             "description_pt": (
                 "Sessoes bloqueadas com o respectivo blocker, tipo de wait e "
                 "recurso. Identifica onde esta o choque de locks."
             )},
            {"id": "step_2_lead_blockers", "label": "Lead blockers",
             "description_pt": (
                 "Sessoes no topo da cadeia — estao a bloquear mas nao sao "
                 "bloqueadas por ninguem. Sao o ponto de intervencao prioritario."
             )},
            {"id": "step_3_long_tran", "label": "Transacoes abertas ha mais de 5 minutos",
             "description_pt": (
                 "Sessoes com transacao aberta mas sem request activo. Suspeitas "
                 "de transacao esquecida pela aplicacao (begin tran sem commit/rollback) "
                 "— causa frequente de lead blockers persistentes."
             )},
        ]

    async def collect(self, instance: str) -> Dict[str, Any]:
        from api.async_db import async_execute_on_server
        data = {"instance": instance, "steps": {}, "_errors": []}

        # Step 1: chains
        t0 = time.time()
        q1 = """
        SELECT
            r.session_id AS blocked_spid,
            r.blocking_session_id AS blocker_spid,
            DB_NAME(r.database_id) AS database_name,
            r.wait_type, r.wait_time / 1000 AS wait_sec,
            r.cpu_time, r.total_elapsed_time / 1000 AS elapsed_sec,
            s.login_name, s.host_name, s.program_name,
            SUBSTRING(t.text, (r.statement_start_offset/2)+1,
                ((CASE r.statement_end_offset
                    WHEN -1 THEN DATALENGTH(t.text)
                    ELSE r.statement_end_offset END - r.statement_start_offset)/2)+1
            ) AS sql_text
        FROM sys.dm_exec_requests r WITH (NOLOCK)
        JOIN sys.dm_exec_sessions s WITH (NOLOCK) ON s.session_id = r.session_id
        OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
        WHERE r.blocking_session_id > 0
        ORDER BY r.wait_time DESC
        """
        try:
            rows = await async_execute_on_server(instance, q1) or []
            data["steps"]["step_1_chains"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q1}
        except Exception as e:
            data["_errors"].append(("step_1_chains", str(e)))
            data["steps"]["step_1_chains"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # Step 2: lead blockers (blocker_spid present in chains but not being blocked themselves)
        t0 = time.time()
        q2 = """
        SELECT DISTINCT s.session_id, s.login_name, s.host_name, s.program_name,
               s.status, s.cpu_time, s.memory_usage * 8 AS memory_kb,
               DATEDIFF(SECOND, s.last_request_start_time, GETDATE()) AS idle_since_sec
        FROM sys.dm_exec_sessions s WITH (NOLOCK)
        WHERE s.session_id IN (
            SELECT DISTINCT blocking_session_id
            FROM sys.dm_exec_requests WITH (NOLOCK)
            WHERE blocking_session_id > 0
        )
        AND s.session_id NOT IN (
            SELECT session_id FROM sys.dm_exec_requests WITH (NOLOCK)
            WHERE blocking_session_id > 0
        )
        """
        try:
            rows = await async_execute_on_server(instance, q2) or []
            data["steps"]["step_2_lead_blockers"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q2}
        except Exception as e:
            data["_errors"].append(("step_2_lead_blockers", str(e)))
            data["steps"]["step_2_lead_blockers"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # Step 3: long transactions
        t0 = time.time()
        q3 = """
        SELECT
            s.session_id, s.login_name, s.host_name, s.program_name,
            DB_NAME(tran.database_id) AS database_name,
            DATEDIFF(SECOND, tran.database_transaction_begin_time, GETDATE()) / 60 AS tran_minutes,
            tran.database_transaction_log_bytes_used / 1024.0 / 1024.0 AS log_used_mb
        FROM sys.dm_tran_database_transactions tran WITH (NOLOCK)
        JOIN sys.dm_tran_session_transactions sesstran WITH (NOLOCK)
            ON tran.transaction_id = sesstran.transaction_id
        JOIN sys.dm_exec_sessions s WITH (NOLOCK)
            ON sesstran.session_id = s.session_id
        WHERE DATEDIFF(SECOND, tran.database_transaction_begin_time, GETDATE()) > 300
        ORDER BY tran.database_transaction_begin_time
        """
        try:
            rows = await async_execute_on_server(instance, q3) or []
            data["steps"]["step_3_long_tran"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q3}
        except Exception as e:
            data["_errors"].append(("step_3_long_tran", str(e)))
            data["steps"]["step_3_long_tran"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        return data

    async def analyze(self, raw: Dict[str, Any], instance: str) -> InvestigationResult:
        chains = raw["steps"].get("step_1_chains", {}).get("data", [])
        leads = raw["steps"].get("step_2_lead_blockers", {}).get("data", [])
        long_tran = raw["steps"].get("step_3_long_tran", {}).get("data", [])

        count = len(chains)
        if count >= 5:
            severity = SEVERITY_CRITICAL
        elif count >= 2:
            severity = SEVERITY_WARNING
        elif count > 0:
            severity = SEVERITY_INFO
        else:
            severity = SEVERITY_OK

        databases = set(c.get("database_name") for c in chains if c.get("database_name"))

        root_cause = "Sem blocking activo." if severity == SEVERITY_OK else (
            f"{count} sessoes bloqueadas por {len(leads)} lead blockers. "
            f"Databases afectadas: {', '.join(list(databases)[:3]) or '?'}."
        )

        recs = []
        if count > 0 and leads:
            top = leads[0]
            recs.append(Recommendation(
                action=f"Investigar SPID {top.get('session_id')} (lead blocker)",
                effort='low',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt=f"Login {top.get('login_name')} / {top.get('program_name')} — rever SQL activo e considerar KILL se for zombie.",
                estimated_impact_pct=80.0, requires_approval=False,
                risk_if_ignored_pt="Chains continuam a crescer — SLA em risco.",
            ))
        if long_tran:
            recs.append(Recommendation(
                action="Avaliar long transactions",
                effort='medium',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt=f"{len(long_tran)} transacoes abertas ha mais de 5min — confirmar com os owners.",
                estimated_impact_pct=40.0, requires_approval=False,
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
            subtitle_pt=f"{count} bloqueadas / {len(leads)} lead blockers" if count else "Sem blocking",
            executive_summary_pt=(
                f"{count} sessoes bloqueadas em {instance}. {len(leads)} lead blockers identificados."
            ) if count else f"{instance} sem blocking activo.",
            business_impact_pt=(
                "Utilizadores com queries em espera — risco de timeout no cliente."
                if severity in (SEVERITY_CRITICAL, SEVERITY_WARNING) else "Sem impacto."
            ),
            estimated_impact=EstimatedImpact(
                users_affected=count, databases_affected=len(databases),
                sla_risk="HIGH" if severity == SEVERITY_CRITICAL else ("MEDIUM" if severity == SEVERITY_WARNING else "LOW"),
            ),
            root_cause_pt=root_cause, confidence_score=80.0 if count else 95.0,
            recommendations=recs, steps=steps,
            raw_dmv_data={"chain_count": count, "lead_count": len(leads), "long_tran_count": len(long_tran)},
        )
