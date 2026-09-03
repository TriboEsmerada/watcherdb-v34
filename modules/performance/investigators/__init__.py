"""Registry de investigators do modulo Performance."""

from typing import Dict, Type

from modules.performance.base import PerformanceInvestigator

# Registry populado em get_registry() via lazy import para evitar ciclos
_REGISTRY: Dict[str, Type[PerformanceInvestigator]] = {}


def get_registry() -> Dict[str, Type[PerformanceInvestigator]]:
    """Retorna registry lazy. Importa todos os investigators na primeira chamada."""
    global _REGISTRY
    if not _REGISTRY:
        from modules.performance.investigators.deadlocks import DeadlocksInvestigator
        from modules.performance.investigators.slow_queries import SlowQueriesInvestigator
        from modules.performance.investigators.missing_indexes import MissingIndexesInvestigator
        from modules.performance.investigators.blocking_chains import BlockingChainsInvestigator
        from modules.performance.investigators.problematic_sessions import ProblematicSessionsInvestigator
        from modules.performance.investigators.cpu_queries import CPUQueriesInvestigator
        from modules.performance.investigators.memory_queries import MemoryQueriesInvestigator
        from modules.performance.investigators.heavy_queries import HeavyQueriesInvestigator

        # Ordem dos cards na UI segue especificidade: especificos primeiro,
        # vistas agregadas por ultimo. ProblematicSessions e a vista mais ampla.
        for cls in (
            DeadlocksInvestigator,
            BlockingChainsInvestigator,
            MissingIndexesInvestigator,
            SlowQueriesInvestigator,
            CPUQueriesInvestigator,
            MemoryQueriesInvestigator,
            HeavyQueriesInvestigator,
            ProblematicSessionsInvestigator,
        ):
            _REGISTRY[cls.investigator_id] = cls
    return _REGISTRY


def get_investigator(investigator_id: str) -> PerformanceInvestigator:
    """Instancia o investigator pelo ID."""
    registry = get_registry()
    if investigator_id not in registry:
        raise KeyError(f"Investigator '{investigator_id}' nao registado")
    return registry[investigator_id]()
