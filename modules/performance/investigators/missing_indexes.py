"""MissingIndexesInvestigator — sugestoes de indices do query optimizer."""

import logging
import time
from typing import Any, Dict, List

from modules.performance.base import (
    InvestigationResult, InvestigationStep, PerformanceInvestigator,
    Recommendation, EstimatedImpact,
    SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO, SEVERITY_OK,
)

logger = logging.getLogger(__name__)


class MissingIndexesInvestigator(PerformanceInvestigator):
    investigator_id = "missing_indexes"
    display_name_pt = "Missing Indexes"
    category = "SCHEMA_HEALTH"
    icon = "fa-search-plus"
    help_text_pt = (
        "O QUE E: sugestoes de indices geradas pelo query optimizer durante a "
        "compilacao de planos. Sao registadas em sys.dm_db_missing_index_* quando "
        "o optimizer estima que um indice adicional reduziria custo de execucao.\n\n"
        "PROBLEMA CAUSADO: ausencia do indice forca table scans ou index scans "
        "completos, aumentando CPU, I/O logico e latencia. Em tabelas grandes, "
        "uma unica query ad-hoc pode ler milhoes de linhas para devolver dezenas.\n\n"
        "COMO MEDIMOS: priority_score = avg_total_user_cost * avg_user_impact * "
        "(user_seeks + user_scans). CRITICAL quando priority_score > 1.000.000; "
        "WARNING quando > 100.000. Nota: sao SUGESTOES — o optimizer nao avalia "
        "custo de manutencao do indice nem colisao com indices existentes."
    )

    THRESHOLD_CRITICAL = 1_000_000
    THRESHOLD_WARNING = 100_000

    def get_steps_schema(self) -> List[Dict[str, str]]:
        return [
            {"id": "step_1_top_indexes", "label": "Top 20 missing indexes por priority_score",
             "description_pt": (
                 "Sugestoes ordenadas por impacto estimado. A formula combina o "
                 "custo medio da query afectada, a melhoria estimada e a "
                 "frequencia de acesso (seeks + scans). Valida sempre a sugestao "
                 "em QLT/TST antes de aplicar em PRD: o optimizer nao considera "
                 "custo de escrita/manutencao nem indices redundantes pre-existentes."
             )},
        ]

    async def collect(self, instance: str) -> Dict[str, Any]:
        from api.async_db import async_execute_on_server
        data = {"instance": instance, "steps": {}, "_errors": []}

        t0 = time.time()
        q1 = """
        SELECT TOP 20
            mid.database_id,
            DB_NAME(mid.database_id) AS database_name,
            mid.[statement] AS table_statement,
            CAST(migs.avg_total_user_cost * migs.avg_user_impact *
                 (migs.user_seeks + migs.user_scans) AS DECIMAL(18,2)) AS priority_score,
            CAST(migs.avg_user_impact AS DECIMAL(5,2)) AS impact_pct,
            migs.user_seeks, migs.user_scans,
            mid.equality_columns, mid.inequality_columns, mid.included_columns,
            'CREATE INDEX IX_' +
                REPLACE(REPLACE(REPLACE(OBJECT_NAME(mid.object_id, mid.database_id), ' ', '_'), '[', ''), ']', '') +
                '_missing ON ' + mid.[statement] +
                ' (' + ISNULL(mid.equality_columns, '') +
                CASE WHEN mid.inequality_columns IS NOT NULL
                     THEN ',' + mid.inequality_columns ELSE '' END + ')' +
                CASE WHEN mid.included_columns IS NOT NULL
                     THEN ' INCLUDE (' + mid.included_columns + ')' ELSE '' END
                AS create_index_sql
        FROM sys.dm_db_missing_index_group_stats migs WITH (NOLOCK)
        JOIN sys.dm_db_missing_index_groups mig WITH (NOLOCK)
            ON migs.group_handle = mig.index_group_handle
        JOIN sys.dm_db_missing_index_details mid WITH (NOLOCK)
            ON mig.index_handle = mid.index_handle
        WHERE mid.database_id > 4  -- exclui system DBs
        ORDER BY priority_score DESC
        """
        try:
            rows = await async_execute_on_server(instance, q1) or []
            data["steps"]["step_1_top_indexes"] = {"data": rows, "duration_ms": int((time.time() - t0) * 1000), "query": q1}
        except Exception as e:
            data["_errors"].append(("step_1_top_indexes", str(e)))
            data["steps"]["step_1_top_indexes"] = {"data": [], "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}

        return data

    async def analyze(self, raw: Dict[str, Any], instance: str) -> InvestigationResult:
        indexes = raw["steps"].get("step_1_top_indexes", {}).get("data", [])

        critical = [i for i in indexes if float(i.get("priority_score", 0) or 0) >= self.THRESHOLD_CRITICAL]
        warning = [i for i in indexes if self.THRESHOLD_WARNING <= float(i.get("priority_score", 0) or 0) < self.THRESHOLD_CRITICAL]
        info = [i for i in indexes if 0 < float(i.get("priority_score", 0) or 0) < self.THRESHOLD_WARNING]

        if critical:
            severity = SEVERITY_CRITICAL
        elif warning:
            severity = SEVERITY_WARNING
        elif info:
            severity = SEVERITY_INFO
        else:
            severity = SEVERITY_OK

        count = len(critical) + len(warning)
        databases = set(i.get("database_name") for i in indexes if i.get("database_name"))

        recs = []
        for idx in critical[:3]:
            recs.append(Recommendation(
                action=f"CREATE INDEX em {idx.get('database_name')}.{idx.get('table_statement', '')}",
                effort='medium',  # 2026-08-17 layout Diagnostico (mapa fixo por tipo)
                description_pt=(
                    f"Priority score {float(idx.get('priority_score', 0) or 0):,.0f} — "
                    f"impact {float(idx.get('impact_pct', 0) or 0):.1f}%. "
                    f"Testar em TST antes de aplicar em PRD."
                ),
                estimated_impact_pct=float(idx.get("impact_pct", 0) or 0),
                requires_approval=True,
                sql_script=idx.get("create_index_sql"),
                risk_if_ignored_pt="Queries continuam com table scans — CPU e I/O elevados.",
            ))

        root_cause_pt = "Sem indices em falta significativos." if severity == SEVERITY_OK else (
            f"{len(critical)} CRITICAL + {len(warning)} WARNING indices sugeridos pelo optimizer. "
            f"Top hotspot: {indexes[0].get('database_name', '?')}.{indexes[0].get('table_statement', '?')}."
            if indexes else "Sem dados."
        )

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
            subtitle_pt=f"{len(critical)} CRIT / {len(warning)} WARN / {len(info)} INFO" if indexes else "Sem sugestoes",
            executive_summary_pt=(
                f"{count} missing indexes significativos em {instance} "
                f"({len(critical)} criticos em {len(databases)} DBs)."
            ) if count else f"{instance} sem missing indexes criticos.",
            business_impact_pt=(
                "Table scans em tabelas grandes causam CPU elevado e latencia percebida."
                if severity in (SEVERITY_CRITICAL, SEVERITY_WARNING) else "Sem impacto."
            ),
            estimated_impact=EstimatedImpact(
                databases_affected=len(databases),
                sla_risk="HIGH" if severity == SEVERITY_CRITICAL else ("MEDIUM" if severity == SEVERITY_WARNING else "LOW"),
            ),
            root_cause_pt=root_cause_pt,
            confidence_score=85.0 if count else 60.0,
            recommendations=recs, steps=steps,
            raw_dmv_data={"critical_count": len(critical), "warning_count": len(warning), "databases": list(databases)},
        )
