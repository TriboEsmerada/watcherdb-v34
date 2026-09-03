"""
Endpoint Usage Tracker
Rastreia uso de endpoints para identificar quais não são utilizados.

Este módulo fornece:
- Decorator para logging automático de chamadas a endpoints
- Estatísticas de uso por endpoint
- Identificação de endpoints não utilizados
- Exportação de métricas para análise

Autor: WatcherDB Team
Data: 2026-02-20
"""

import logging
import time
import json
from functools import wraps
from typing import Dict, List, Optional, Callable
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)

# ============================================================================
# STORAGE DE MÉTRICAS DE USO
# ============================================================================

# Dicionário thread-safe para armazenar métricas
_usage_stats_lock = threading.Lock()
_usage_stats: Dict[str, Dict] = defaultdict(lambda: {
    "total_calls": 0,
    "first_call": None,
    "last_call": None,
    "avg_response_time_ms": 0,
    "error_count": 0,
    "http_methods": defaultdict(int),
    "user_agents": defaultdict(int),
    "endpoints": []  # Lista de endpoints específicos chamados
})


class EndpointUsageTracker:
    """
    Tracker centralizado de uso de endpoints.

    Permite identificar endpoints não utilizados e gerar relatórios.
    """

    def __init__(self, log_file: Optional[str] = None):
        """
        Inicializa tracker.

        Args:
            log_file: Caminho para arquivo de log de métricas (opcional)
        """
        self.log_file = log_file
        if log_file:
            self.log_file_path = Path(log_file)
            self.log_file_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def track_usage(
        endpoint_name: str,
        deprecated: bool = False,
        alternative_endpoint: Optional[str] = None
    ) -> Callable:
        """
        Decorator para rastrear uso de endpoints.

        Args:
            endpoint_name: Nome do endpoint (ex: "/api/backup/server/{id}/pattern")
            deprecated: Se True, marca endpoint como deprecated
            alternative_endpoint: Endpoint alternativo recomendado (se deprecated)

        Returns:
            Decorator function

        Usage:
            @router.get("/old-endpoint")
            @EndpointUsageTracker.track_usage(
                "/api/backup/old-endpoint",
                deprecated=True,
                alternative_endpoint="/api/backup/new-endpoint"
            )
            async def old_endpoint():
                return {"data": "..."}
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                endpoint_key = endpoint_name

                # Registrar chamada
                with _usage_stats_lock:
                    stats = _usage_stats[endpoint_key]
                    stats["total_calls"] += 1
                    stats["deprecated"] = deprecated
                    stats["alternative"] = alternative_endpoint

                    now = datetime.now().isoformat()
                    if stats["first_call"] is None:
                        stats["first_call"] = now
                    stats["last_call"] = now

                # Log de uso
                if deprecated:
                    logger.warning(
                        f"⚠️  DEPRECATED ENDPOINT CALLED: {endpoint_name} | "
                        f"Use instead: {alternative_endpoint or 'N/A'} | "
                        f"Total calls: {stats['total_calls']}"
                    )
                else:
                    logger.info(
                        f"📊 ENDPOINT USAGE: {endpoint_name} | "
                        f"Total calls: {stats['total_calls']}"
                    )

                # Executar função original
                error_occurred = False
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    error_occurred = True
                    with _usage_stats_lock:
                        stats["error_count"] += 1
                    raise
                finally:
                    # Calcular tempo de resposta
                    response_time_ms = (time.time() - start_time) * 1000

                    with _usage_stats_lock:
                        # Atualizar média de tempo de resposta
                        current_avg = stats["avg_response_time_ms"]
                        total_calls = stats["total_calls"]
                        stats["avg_response_time_ms"] = (
                            (current_avg * (total_calls - 1) + response_time_ms) / total_calls
                        )

                        # Log detalhado
                        logger.debug(
                            f"📈 {endpoint_name}: "
                            f"Response time: {response_time_ms:.2f}ms | "
                            f"Avg: {stats['avg_response_time_ms']:.2f}ms | "
                            f"Error: {error_occurred}"
                        )

            return wrapper
        return decorator

    @staticmethod
    def get_usage_stats() -> Dict:
        """
        Retorna estatísticas de uso de todos endpoints rastreados.

        Returns:
            Dicionário com estatísticas por endpoint
        """
        with _usage_stats_lock:
            return dict(_usage_stats)

    @staticmethod
    def get_unused_endpoints(min_days_since_first_tracked: int = 30) -> List[Dict]:
        """
        Identifica endpoints que nunca foram chamados ou não são usados há muito tempo.

        Args:
            min_days_since_first_tracked: Mínimo de dias desde primeiro tracking

        Returns:
            Lista de endpoints não utilizados
        """
        unused = []
        now = datetime.now()

        with _usage_stats_lock:
            for endpoint, stats in _usage_stats.items():
                # Nunca foi chamado
                if stats["total_calls"] == 0:
                    unused.append({
                        "endpoint": endpoint,
                        "reason": "never_called",
                        "deprecated": stats.get("deprecated", False),
                        "alternative": stats.get("alternative")
                    })
                    continue

                # Não é chamado há muito tempo
                if stats["last_call"]:
                    last_call_dt = datetime.fromisoformat(stats["last_call"])
                    days_since_last = (now - last_call_dt).days

                    if days_since_last >= min_days_since_first_tracked:
                        unused.append({
                            "endpoint": endpoint,
                            "reason": f"not_called_for_{days_since_last}_days",
                            "last_call": stats["last_call"],
                            "total_calls": stats["total_calls"],
                            "deprecated": stats.get("deprecated", False),
                            "alternative": stats.get("alternative")
                        })

        return unused

    @staticmethod
    def export_usage_report(output_file: str = "endpoint_usage_report.json") -> str:
        """
        Exporta relatório completo de uso para arquivo JSON.

        Args:
            output_file: Caminho do arquivo de saída

        Returns:
            Caminho do arquivo gerado
        """
        try:
            stats = EndpointUsageTracker.get_usage_stats()
            unused = EndpointUsageTracker.get_unused_endpoints()

            report = {
                "generated_at": datetime.now().isoformat(),
                "summary": {
                    "total_endpoints_tracked": len(stats),
                    "total_endpoints_unused": len(unused),
                    "total_calls_all_endpoints": sum(s["total_calls"] for s in stats.values()),
                    "deprecated_endpoints_count": sum(1 for s in stats.values() if s.get("deprecated", False))
                },
                "endpoints": stats,
                "unused_endpoints": unused
            }

            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            logger.info(f"✅ Relatório de uso exportado para: {output_path.absolute()}")
            return str(output_path.absolute())

        except Exception as e:
            logger.error(f"❌ Erro ao exportar relatório: {e}", exc_info=True)
            raise

    @staticmethod
    def clear_stats():
        """Limpa todas as estatísticas (útil para testes)"""
        with _usage_stats_lock:
            _usage_stats.clear()
        logger.info("🗑️  Estatísticas de uso limpas")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def mark_endpoint_as_deprecated(
    endpoint_name: str,
    alternative: Optional[str] = None
):
    """
    Marca um endpoint como deprecated nas estatísticas.

    Args:
        endpoint_name: Nome do endpoint
        alternative: Endpoint alternativo recomendado
    """
    with _usage_stats_lock:
        _usage_stats[endpoint_name]["deprecated"] = True
        _usage_stats[endpoint_name]["alternative"] = alternative


def get_most_used_endpoints(top_n: int = 10) -> List[Dict]:
    """
    Retorna os N endpoints mais utilizados.

    Args:
        top_n: Número de endpoints a retornar

    Returns:
        Lista de endpoints ordenados por uso
    """
    with _usage_stats_lock:
        endpoints_list = [
            {
                "endpoint": endpoint,
                "total_calls": stats["total_calls"],
                "avg_response_time_ms": stats["avg_response_time_ms"],
                "error_rate": stats["error_count"] / max(stats["total_calls"], 1)
            }
            for endpoint, stats in _usage_stats.items()
            if stats["total_calls"] > 0
        ]

    # Ordenar por total de chamadas (descendente)
    endpoints_list.sort(key=lambda x: x["total_calls"], reverse=True)

    return endpoints_list[:top_n]


def get_slowest_endpoints(top_n: int = 10) -> List[Dict]:
    """
    Retorna os N endpoints mais lentos.

    Args:
        top_n: Número de endpoints a retornar

    Returns:
        Lista de endpoints ordenados por tempo de resposta
    """
    with _usage_stats_lock:
        endpoints_list = [
            {
                "endpoint": endpoint,
                "avg_response_time_ms": stats["avg_response_time_ms"],
                "total_calls": stats["total_calls"]
            }
            for endpoint, stats in _usage_stats.items()
            if stats["total_calls"] > 0
        ]

    # Ordenar por tempo de resposta (descendente)
    endpoints_list.sort(key=lambda x: x["avg_response_time_ms"], reverse=True)

    return endpoints_list[:top_n]
