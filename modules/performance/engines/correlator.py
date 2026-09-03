"""IncidentCorrelator — agrupa investigacoes relacionadas em 1 incident.

Heuristica MVP (simples e explicavel):
- Janela temporal: investigacoes iniciadas em < 10min entre si
- Mesma instancia
- Pelo menos 1 campo em comum (database_name, object_name)

Resultado: preenche result.correlated_investigations com IDs de outras investigacoes ligadas.
Opcionalmente cria/actualiza row em performance_incidents.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)

CORRELATION_WINDOW_MINUTES = 10


class IncidentCorrelator:
    """Liga investigacoes relacionadas."""

    async def link(self, result) -> None:
        """Enrich do result com correlated_investigations."""
        try:
            from api.connection_pool import execute_on_intelligence
        except ImportError:
            logger.debug("[Correlator] connection_pool nao disponivel, skip")
            return

        cutoff = datetime.utcnow() - timedelta(minutes=CORRELATION_WINDOW_MINUTES)

        query = """
        SELECT TOP 10 investigation_id, investigator_id, triggered_at
        FROM dbo.performance_investigations WITH (NOLOCK)
        WHERE instance = ?
          AND triggered_at >= ?
          AND investigation_id <> ?
          AND severity IN ('CRITICAL', 'WARNING')
        ORDER BY triggered_at DESC
        """
        try:
            rows = execute_on_intelligence(
                query,
                params=(result.instance, cutoff, result.investigation_id),
            ) or []
            result.correlated_investigations = [
                r.get("investigation_id") for r in rows if r.get("investigation_id")
            ]
            if result.correlated_investigations:
                logger.info(
                    "[Correlator] %s correlated: %s",
                    result.investigation_id,
                    result.correlated_investigations,
                )
        except Exception as e:
            logger.warning("[Correlator] falhou (nao fatal): %s", e)
