"""HeavyQueriesInvestigator — queries que consomem muito de tudo.

Score combinado: CPU + reads + duration + memoria + frequencia.
Identifica queries que sao "multi-offender" — o mau tipo da sala.

Formula de heavy_score (0-100):
    0.30 * normalized(total_cpu_ms)
  + 0.25 * normalized(total_logical_reads)
  + 0.20 * normalized(total_elapsed_ms)
  + 0.15 * normalized(total_granted_kb)
  + 0.10 * normalized(execution_count)
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


class HeavyQueriesInvestigator(PerformanceInvestigator):
    investigator_id = "heavy_queries"
    display_name_pt = "Heavy Queries"
    category = "CPU_QUERIES"
    icon = "fa-dumbbell"
    help_text_pt = (
        "O QUE E: queries que consomem simultaneamente recursos elevados em "
        "multiplas dimensoes — CPU, I/O, duracao, memoria e frequencia. A sua "
        "priorizacao para tuning tem retorno superior, dado que uma unica "
        "accao correctiva (indice, reescrita, plan guide) impacta varias "
        "metricas em simultaneo.\n\n"
        "PROBLEMA CAUSADO: estas queries tipicamente dominam o consumo global "
        "do servidor. Atacar queries isoladas de CPU ou I/O sem identificar "
        "os multi-offenders resulta em optimizacao dispersa e ROI baixo.\n\n"
        "COMO MEDIMOS: heavy_score (0-100) calculado com pesos: 30% CPU + "
        "25% logical_reads + 20% elapsed_time + 15% memory_grant + 10% "
        "execution_count, normalizados via MAX() OVER () em T-SQL. "
        "CRITICAL se pelo menos 1 query com score >= 70 ou 5+ multi-offenders. "
        "WARNING se score 40-69 ou 2+ multi-offenders."
    )

    def get_steps_schema(self) -> List[Dict[str, str]]:
        return [
            {"id": "step_1_top_combined", "label": "Top 20 por heavy_score combinado",
             "description_pt": (
                 "Queries ordenadas pelo score ponderado das 5 dimensoes. "
                 "Scores >= 70 correspondem a queries que dominam o consumo "
                 "global do servidor — primeira prioridade de tuning."
             )},
            {"id": "step_2_high_cpu_high_io", "label": "Queries no top 20 de CPU e de I/O simultaneamente",
             "description_pt": (
                 "Interseccao dos rankings de CPU e I/O. Estas queries "
                 "desperdicam duas dimensoes de recurso por execucao — uma "
                 "accao correctiva (tipicamente um indice) melhora ambas."
             )},
            {"id": "step_3_frequent_and_slow", "label": "Queries frequentes e com latencia elevada",
             "description_pt": (
                 "execution_count > 100 e avg_elapsed_ms > 1000. O impacto "
                 "agregado (frequencia x latencia) sobrepoe-se a queries "
                 "pontualmente pesadas mas raras. Atacar aqui tem efeito "
                 "multiplicador."
             )},
        ]

    async def collect(self, instance: str) -> Dict[str, Any]:
        from api.async_db import async_execute_on_server
        data = {"instance": instance, "steps": {}, "_errors": []}

        # Step 1: top combined — calcular normalizacao em T-SQL (ranks)
        t0 = time.time()
        # 2026-08-17: total_grant_kb so' existe em SQL 2016+ (13.x). Em 2014 a query
        # inteira falhava ("Invalid column name") e o investigator ficava vazio em
        # silencio (achado sql-deep-reviewer). Gate por versao: em <13 usa 0 e a
        # componente memoria do score fica a 0 (documentado no help).
        # Tambem passa a projectar query_plan_hash + offsets (base da comparacao
        # de planos do layout Diagnostico: "ha plano mais barato para este hash?").
        _major = 0
        try:
            _vrows = await async_execute_on_server(instance, "SELECT CAST(PARSENAME(CAST(SERVERPROPERTY('ProductVersion') AS VARCHAR(50)), 4) AS INT) AS major") or []
            _major = int((_vrows[0] or {}).get("major") or 0) if _vrows else 0
        except Exception:
            _major = 0
        _grant_col = "qs.total_grant_kb" if (_major == 0 or _major >= 13) else "CAST(0 AS BIGINT) AS total_grant_kb"
        q1 = f"""
        WITH stats AS (
            SELECT
                qs.query_hash, qs.query_plan_hash, qs.plan_handle,
                qs.execution_count,
                qs.total_worker_time AS total_cpu,
                qs.total_elapsed_time AS total_elapsed,
                qs.total_logical_reads AS total_reads,
                {_grant_col},
                qs.last_execution_time,
                qs.sql_handle, qs.statement_start_offset, qs.statement_end_offset
            FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
            WHERE qs.execution_count > 0
        ),
        ranked AS (
            SELECT TOP 20
                query_hash, query_plan_hash, plan_handle, execution_count,
                total_cpu, total_elapsed, total_reads, total_grant_kb,
                last_execution_time, sql_handle, statement_start_offset, statement_end_offset,
                -- Normalizacao: valor / max_global * 100
                (CAST(total_cpu AS FLOAT)    / NULLIF(MAX(total_cpu)    OVER (), 0)) * 30 AS cpu_score,
                (CAST(total_reads AS FLOAT)  / NULLIF(MAX(total_reads)  OVER (), 0)) * 25 AS reads_score,
                (CAST(total_elapsed AS FLOAT)/ NULLIF(MAX(total_elapsed)OVER (), 0)) * 20 AS duration_score,
                (CAST(total_grant_kb AS FLOAT)/ NULLIF(MAX(total_grant_kb) OVER (), 0)) * 15 AS memory_score,
                (CAST(execution_count AS FLOAT)/ NULLIF(MAX(execution_count) OVER (), 0)) * 10 AS frequency_score
            FROM stats
            ORDER BY (
                (CAST(total_cpu AS FLOAT)    / NULLIF(MAX(total_cpu)    OVER (), 0)) * 30 +
                (CAST(total_reads AS FLOAT)  / NULLIF(MAX(total_reads)  OVER (), 0)) * 25 +
                (CAST(total_elapsed AS FLOAT)/ NULLIF(MAX(total_elapsed)OVER (), 0)) * 20 +
                (CAST(total_grant_kb AS FLOAT)/ NULLIF(MAX(total_grant_kb) OVER (), 0)) * 15 +
                (CAST(execution_count AS FLOAT)/ NULLIF(MAX(execution_count) OVER (), 0)) * 10
            ) DESC
        )
        SELECT
            r.query_hash, r.query_plan_hash, r.plan_handle, r.sql_handle,
            r.statement_start_offset, r.statement_end_offset,
            r.execution_count,
            r.total_cpu / 1000 AS total_cpu_ms,
            r.total_cpu / r.execution_count / 1000 AS avg_cpu_ms,
            r.total_reads,
            r.total_reads / r.execution_count AS avg_reads,
            r.total_elapsed / 1000 AS total_elapsed_ms,
            r.total_elapsed / r.execution_count / 1000 AS avg_elapsed_ms,
            r.total_grant_kb,
            CAST(r.cpu_score + r.reads_score + r.duration_score + r.memory_score + r.frequency_score AS DECIMAL(5,1)) AS heavy_score,
            CAST(r.cpu_score AS DECIMAL(5,1)) AS cpu_score,
            CAST(r.reads_score AS DECIMAL(5,1)) AS reads_score,
            CAST(r.duration_score AS DECIMAL(5,1)) AS duration_score,
            CAST(r.memory_score AS DECIMAL(5,1)) AS memory_score,
            CAST(r.frequency_score AS DECIMAL(5,1)) AS frequency_score,
            r.last_execution_time,
            SUBSTRING(qt.text, (r.statement_start_offset/2)+1,
                ((CASE r.statement_end_offset
                    WHEN -1 THEN DATALENGTH(qt.text)
                    ELSE r.statement_end_offset END - r.statement_start_offset)/2)+1
            ) AS sql_text,
            DB_NAME(qt.dbid) AS database_name
        FROM ranked r
        CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) qt
        ORDER BY heavy_score DESC
        """
        try:
            rows = await async_execute_on_server(instance, q1) or []
            data["steps"]["step_1_top_combined"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q1}
        except Exception as e:
            data["_errors"].append(("step_1_top_combined", str(e)))
            data["steps"]["step_1_top_combined"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # Step 2: high CPU AND high I/O (intersection)
        t0 = time.time()
        q2 = """
        WITH top_cpu AS (
            SELECT TOP 20 query_hash
            FROM sys.dm_exec_query_stats WITH (NOLOCK)
            ORDER BY total_worker_time DESC
        ),
        top_io AS (
            SELECT TOP 20 query_hash
            FROM sys.dm_exec_query_stats WITH (NOLOCK)
            ORDER BY total_logical_reads DESC
        )
        SELECT TOP 20
            qs.query_hash, qs.execution_count,
            qs.total_worker_time / 1000 AS total_cpu_ms,
            qs.total_logical_reads AS total_reads,
            qs.total_elapsed_time / qs.execution_count / 1000 AS avg_elapsed_ms,
            SUBSTRING(qt.text, (qs.statement_start_offset/2)+1,
                ((CASE qs.statement_end_offset
                    WHEN -1 THEN DATALENGTH(qt.text)
                    ELSE qs.statement_end_offset END - qs.statement_start_offset)/2)+1
            ) AS sql_text,
            DB_NAME(qt.dbid) AS database_name
        FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
        WHERE qs.query_hash IN (SELECT query_hash FROM top_cpu)
          AND qs.query_hash IN (SELECT query_hash FROM top_io)
        ORDER BY qs.total_worker_time DESC
        """
        try:
            rows = await async_execute_on_server(instance, q2) or []
            data["steps"]["step_2_high_cpu_high_io"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q2}
        except Exception as e:
            data["_errors"].append(("step_2_high_cpu_high_io", str(e)))
            data["steps"]["step_2_high_cpu_high_io"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        # Step 3: frequent AND slow
        t0 = time.time()
        q3 = """
        SELECT TOP 20
            qs.query_hash, qs.execution_count,
            qs.total_elapsed_time / qs.execution_count / 1000 AS avg_elapsed_ms,
            qs.total_worker_time / qs.execution_count / 1000 AS avg_cpu_ms,
            qs.total_elapsed_time / 1000 AS total_elapsed_ms,
            SUBSTRING(qt.text, (qs.statement_start_offset/2)+1,
                ((CASE qs.statement_end_offset
                    WHEN -1 THEN DATALENGTH(qt.text)
                    ELSE qs.statement_end_offset END - qs.statement_start_offset)/2)+1
            ) AS sql_text,
            DB_NAME(qt.dbid) AS database_name
        FROM sys.dm_exec_query_stats qs WITH (NOLOCK)
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
        WHERE qs.execution_count > 100
          AND (qs.total_elapsed_time / qs.execution_count / 1000) > 1000
        ORDER BY qs.total_elapsed_time DESC
        """
        try:
            rows = await async_execute_on_server(instance, q3) or []
            data["steps"]["step_3_frequent_and_slow"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q3}
        except Exception as e:
            data["_errors"].append(("step_3_frequent_and_slow", str(e)))
            data["steps"]["step_3_frequent_and_slow"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        return data

    async def analyze(self, raw: Dict[str, Any], instance: str) -> InvestigationResult:
        top = raw["steps"].get("step_1_top_combined", {}).get("data", [])
        multi = raw["steps"].get("step_2_high_cpu_high_io", {}).get("data", [])
        freq_slow = raw["steps"].get("step_3_frequent_and_slow", {}).get("data", [])

        # Severity baseada em:
        #   - # queries com heavy_score > 70 (CRITICAL)
        #   - # queries com heavy_score > 40 (WARNING)
        #   - # multi-offenders (CPU+I/O)
        def _score(q):
            try: return float(q.get("heavy_score") or 0)
            except (TypeError, ValueError): return 0

        top_score = [q for q in top if _score(q) >= 70]
        warn_score = [q for q in top if 40 <= _score(q) < 70]

        if top_score or len(multi) >= 5:
            severity = SEVERITY_CRITICAL
        elif warn_score or len(multi) >= 2 or freq_slow:
            severity = SEVERITY_WARNING
        elif top:
            severity = SEVERITY_INFO
        else:
            severity = SEVERITY_OK

        count = len(top_score) + len(warn_score)
        databases = set(q.get("database_name") for q in top if q.get("database_name"))

        root_cause = "Nenhuma query com score combinado elevado."
        confidence = 80.0
        if top_score:
            w = top_score[0]
            execs = int(w.get("execution_count") or 0)
            db = w.get("database_name")
            db_label = f"DB: {db}" if db else "DB: nao identificada (ad-hoc/sp_executesql)"
            root_cause = (
                f"Top heavy offender: score {_score(w):.0f}/100. "
                f"{db_label}, {execs}x execucoes, "
                f"avg_cpu: {(w.get('avg_cpu_ms') or 0):.0f}ms, "
                f"avg_elapsed: {(w.get('avg_elapsed_ms') or 0):.0f}ms."
            )
            confidence = 85.0
        elif warn_score:
            root_cause = f"{len(warn_score)} queries com score combinado moderado. Candidatas a tuning preventivo."
            confidence = 70.0
        elif len(multi) >= 2:
            root_cause = f"{len(multi)} queries presentes simultaneamente em top CPU E top I/O — tuning prioritario."
            confidence = 75.0

        recs: List[Recommendation] = []
        if top_score or warn_score:
            target = (top_score or warn_score)[0]
            recs.append(Recommendation(
                action="Investigar query com maior heavy_score",
                effort='low',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt=(
                    f"Score {_score(target):.0f}/100 — examinar plano, procurar Missing Indexes, "
                    f"considerar reescrever query. Esta query afecta multiplas dimensoes ao mesmo tempo."
                ),
                estimated_impact_pct=75.0, requires_approval=False,
            ))
        if multi:
            recs.append(Recommendation(
                action="Priorizar multi-offenders (CPU+I/O)",
                effort='low',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt=f"{len(multi)} queries estao nos top-20 de CPU E I/O — ROI alto de tuning.",
                estimated_impact_pct=60.0, requires_approval=False,
            ))
        if freq_slow:
            recs.append(Recommendation(
                action="Tratar queries frequentes E lentas",
                effort='high',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt=(
                    f"{len(freq_slow)} queries executam >100x com avg>1s. "
                    f"Impacto real = frequencia x latencia — potencial grande em optimizar."
                ),
                estimated_impact_pct=55.0, requires_approval=False,
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
                f"{len(top_score)} crit / {len(warn_score)} warn / {len(multi)} multi"
                if count or multi else "Sem heavy queries"
            ),
            executive_summary_pt=(
                f"{count} queries com impacto combinado elevado em {instance}. "
                f"Estas queries consomem simultaneamente CPU, I/O, memoria e/ou duracao — tuning destas multiplica o beneficio."
            ) if count else f"{instance} — sem queries com impacto combinado elevado.",
            business_impact_pt=(
                "Multi-offenders afectam varios recursos simultaneamente — prioridade maxima de tuning."
                if severity in (SEVERITY_CRITICAL, SEVERITY_WARNING) else "Sem impacto."
            ),
            estimated_impact=EstimatedImpact(
                databases_affected=len(databases),
                sla_risk="HIGH" if severity == SEVERITY_CRITICAL else ("MEDIUM" if severity == SEVERITY_WARNING else "LOW"),
            ),
            root_cause_pt=root_cause, confidence_score=confidence,
            recommendations=recs, steps=steps,
            raw_dmv_data={
                "top_critical_count": len(top_score),
                "top_warning_count": len(warn_score),
                "multi_offenders": len(multi),
                "frequent_slow": len(freq_slow),
                "databases": list(databases),
            },
        )
