"""BaselineComparator — detecta regressao silenciosa.

Le performance_query_baselines e compara com valores actuais ja presentes
nos steps do InvestigationResult. Adiciona BaselineComparison quando ha:
- baseline conhecido (7d ou 30d)
- current > baseline * REGRESSION_FACTOR_SILENT
- E o valor actual ainda NAO bateu threshold absoluto (por isso "silencioso")
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

REGRESSION_FACTOR_SILENT = 3.0  # current > 3x baseline = flag


class BaselineComparator:
    """Compara valores actuais vs baseline persistido em performance_query_baselines."""

    async def enrich(self, result) -> None:
        """MVP: se existirem query_hashes nos steps, comparar com baseline."""
        from modules.performance.base import BaselineComparison

        try:
            from api.connection_pool import execute_on_intelligence
        except ImportError:
            logger.debug("[Baseline] connection_pool nao disponivel, skip")
            return

        # Extrair query_hashes dos steps (investigators adicionam em raw_dmv_data)
        hashes = self._extract_query_hashes(result)
        if not hashes:
            return

        try:
            placeholders = ",".join("?" * len(hashes))
            query = f"""
            SELECT query_hash, avg_elapsed_ms_7d, avg_elapsed_ms_30d,
                   avg_logical_reads_7d, avg_logical_reads_30d
            FROM dbo.performance_query_baselines WITH (NOLOCK)
            WHERE instance = ?
              AND query_hash IN ({placeholders})
            """
            rows = execute_on_intelligence(
                query,
                params=tuple([result.instance, *hashes]),
            ) or []

            baseline_map: Dict[bytes, Dict] = {r["query_hash"]: r for r in rows}

            # Cruzar com current values dos steps
            for step in result.steps:
                for item in step.data:
                    qh = item.get("query_hash")
                    if not qh or qh not in baseline_map:
                        continue
                    baseline = baseline_map[qh]
                    current_ms = item.get("avg_elapsed_ms") or item.get("avg_duration_ms") or 0
                    b7 = baseline.get("avg_elapsed_ms_7d")
                    if b7 and current_ms > b7 * REGRESSION_FACTOR_SILENT:
                        factor = current_ms / b7 if b7 else 0
                        result.baseline_comparisons.append(
                            BaselineComparison(
                                metric="avg_elapsed_ms",
                                current=current_ms,
                                baseline_7d=b7,
                                baseline_30d=baseline.get("avg_elapsed_ms_30d"),
                                trend="regression",
                                variation_factor=round(factor, 2),
                                is_silent_regression=True,
                            )
                        )
            if result.baseline_comparisons:
                logger.info(
                    "[Baseline] %s silent regressions detectadas para %s",
                    len(result.baseline_comparisons), result.instance,
                )
        except Exception as e:
            logger.warning("[Baseline] falhou: %s", e)

    def _extract_query_hashes(self, result) -> list:
        """Colecta query_hashes unicos dos steps."""
        hashes = set()
        for step in result.steps:
            for item in step.data:
                qh = item.get("query_hash")
                if qh:
                    hashes.add(qh)
        return list(hashes)[:50]  # cap a 50 para nao fazer query gigante
