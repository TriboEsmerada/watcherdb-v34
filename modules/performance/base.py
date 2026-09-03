"""Performance Intelligence — Base protocol (dataclasses + ABC).

Contract para todos os investigators do modulo Performance.
Define o que cada investigacao deve produzir em 5 niveis (L1..L5) de drill-down.
"""

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _json_safe(obj: Any) -> Any:
    """Converte recursivamente tipos nao-JSON-serializaveis.

    - bytes/bytearray -> hex string
    - datetime/date  -> ISO string
    - Decimal        -> float
    - dict/list/tuple -> recursao
    """
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return bytes(obj).hex()
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        try:
            return float(obj)
        except Exception:
            return str(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


# =============================================================================
# Severity levels (alinhado com o resto do sistema)
# =============================================================================
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"
SEVERITY_OK = "OK"

SEVERITY_ORDER = {
    SEVERITY_CRITICAL: 0,
    SEVERITY_WARNING: 1,
    SEVERITY_INFO: 2,
    SEVERITY_OK: 3,
}


# =============================================================================
# Dataclasses — building blocks de um InvestigationResult
# =============================================================================

@dataclass
class InvestigationStep:
    """1 step da investigacao — resultado de 1 query diagnostica."""
    id: str                           # "step_1_active_sessions"
    label: str                        # "Sessoes activas com CPU alto"
    description_pt: str               # texto "?" para o gestor
    data: List[Dict[str, Any]] = field(default_factory=list)
    query_sql: str = ""               # SQL usado (transparencia)
    duration_ms: int = 0              # quanto tempo demorou
    data_available: bool = True       # graceful degradation
    error_pt: Optional[str] = None    # mensagem de erro se data_available=False


@dataclass
class Recommendation:
    """Uma accao concreta recomendada ao DBA."""
    action: str                       # "CREATE INDEX IX_..." / "UPDATE STATISTICS"
    description_pt: str               # linguagem humana PT
    estimated_impact_pct: float = 0.0 # 0-100
    requires_approval: bool = True    # True por default em PRD
    sql_script: Optional[str] = None  # SQL pronto (se aplicavel)
    risk_if_ignored_pt: str = ""      # "SLA breach em ~2h se nao resolvido"
    # 2026-08-17 (layout Diagnostico): esforco de aplicar a accao, mapa FIXO por
    # tipo (nao calculado): 'low' = estatisticas/config/so' DBA sem release;
    # 'medium' = indice/DDL de DBA; 'high' = reescrita de codigo aplicacional.
    # Default '' = desconhecido (frontend mostra "n/d", nao inventa). Campo com
    # default -> backward-compatible; ficheiro partilhado com V5 (sincronizar).
    effort: str = ""
    # Ids de problemas (do bloco "Porque") que esta accao endereca — o portal
    # filtra recomendacoes ao clicar num problema. Opcional.
    problem_ids: List[str] = field(default_factory=list)


@dataclass
class DetectedProblem:
    """2026-08-17 (layout Diagnostico, bloco "Porque"): 1 problema DISCRETO com
    evidencia e origem. Substitui progressivamente a prosa unica de root_cause_pt.
    Regra: objecto real + numero + origem + timestamp; heuristica marcada."""
    id: str                           # "scan_heap_vendas"
    title_pt: str                     # "Table Scan em HEAP dbo.Vendas"
    evidence_pt: str                  # "5,1M linhas estimadas, 92% do custo do plano"
    impact_pt: str = ""               # "Alto custo I/O e CPU"
    severity: str = "WARNING"         # CRITICAL | WARNING | INFO
    source: str = "dmv"               # dmv | plan_estimated | plan_actual | history
    confidence: str = "measured"      # measured | heuristic
    icon: str = "fa-exclamation-triangle"
    object_name: str = ""             # objecto principal (tabela/indice/query_hash)
    metric_value: Optional[float] = None
    metric_unit: str = ""
    recommendation_ids: List[str] = field(default_factory=list)


@dataclass
class BaselineComparison:
    """Comparacao actual vs baseline (regressao silenciosa)."""
    metric: str                       # "avg_duration_ms"
    current: float
    baseline_7d: Optional[float] = None
    baseline_30d: Optional[float] = None
    trend: str = "stable"             # "regression" | "improvement" | "stable"
    variation_factor: float = 1.0     # 40.0 == 40x worse
    is_silent_regression: bool = False


@dataclass
class EstimatedImpact:
    """Impacto quantificado para o Executive Summary."""
    users_affected: int = 0
    sla_risk: str = "LOW"             # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    duration_min: int = 0
    databases_affected: int = 0
    transactions_at_risk: int = 0


@dataclass
class InvestigationResult:
    """Contract completo — 5 niveis de drill-down.

    L1: card summary (investigator_id, severity, count, subtitle_pt)
    L2: executive (executive_summary_pt, business_impact_pt, estimated_impact)
    L3: investigation (root_cause_pt, confidence, baselines, recommendations, runbook, correlated)
    L4: technical (steps[])
    L5: raw (raw_dmv_data)
    """

    # --- L1: card summary ---
    investigator_id: str              # "slow_queries"
    instance: str
    severity: str = SEVERITY_OK
    count: int = 0                    # numero que aparece no card
    subtitle_pt: str = ""             # "5 queries lentas em 12 DBs"

    # --- L2: executive ---
    executive_summary_pt: str = ""
    business_impact_pt: str = ""
    estimated_impact: EstimatedImpact = field(default_factory=EstimatedImpact)

    # --- L3: investigation ---
    root_cause_pt: str = ""
    confidence_score: float = 0.0     # 0-100
    # 2026-08-17: lista estruturada de problemas (bloco "Porque" do layout
    # Diagnostico). Vazia = portal sintetiza a partir de root_cause_pt +
    # baseline_comparisons (nunca inventa 5 cards).
    problems: List[DetectedProblem] = field(default_factory=list)
    baseline_comparisons: List[BaselineComparison] = field(default_factory=list)
    recommendations: List[Recommendation] = field(default_factory=list)
    correlated_investigations: List[str] = field(default_factory=list)
    runbook_steps: List[str] = field(default_factory=list)

    # --- L4: technical ---
    steps: List[InvestigationStep] = field(default_factory=list)

    # --- L5: raw ---
    raw_dmv_data: Dict[str, Any] = field(default_factory=dict)

    # --- Meta ---
    investigation_id: str = ""
    triggered_at: datetime = field(default_factory=datetime.utcnow)
    triggered_by: str = "manual"      # "manual" | "scheduler" | "threshold"
    duration_ms: int = 0
    ticket_response_pt: str = ""

    # --- Fase 2 (placeholders) ---
    timeline_snapshots: Optional[List[Dict[str, Any]]] = None
    peer_benchmark: Optional[Dict[str, Any]] = None
    cost_estimate: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializa para JSON (converte datetime/bytes/Decimal para tipos JSON-safe)."""
        d = asdict(self)
        return _json_safe(d)


# =============================================================================
# ABC — PerformanceInvestigator
# =============================================================================

class PerformanceInvestigator(ABC):
    """Base class para todos os investigators do modulo Performance.

    Subclasses DEVEM implementar:
    - collect(instance) -> dict           # executa queries, retorna raw data
    - analyze(raw_data) -> InvestigationResult  # transforma em resultado estruturado
    - get_steps_schema() -> list[dict]    # declara steps (para UI dinamica)

    Subclasses PODEM sobreescrever:
    - investigate(instance, triggered_by) -> InvestigationResult  # orchestration
    """

    # --- Class attributes (override em cada subclass) ---
    investigator_id: str = ""         # "slow_queries", "deadlocks"
    display_name_pt: str = ""         # "Queries Lentas"
    category: str = ""                # "LOCKS" | "CPU_QUERIES" | "SCHEMA_HEALTH"
    icon: str = "fa-chart-line"
    help_text_pt: str = ""

    def __init__(self):
        if not self.investigator_id:
            raise ValueError(f"{self.__class__.__name__} must define investigator_id")
        if not self.display_name_pt:
            raise ValueError(f"{self.__class__.__name__} must define display_name_pt")

    # --- Abstract ---
    @abstractmethod
    async def collect(self, instance: str) -> Dict[str, Any]:
        """Executa as queries de diagnostico contra a instancia. Retorna raw data.

        Implementacao deve ser graceful: se uma DMV falha, retornar dict parcial
        com chave `_errors` listando os steps que falharam.
        """

    @abstractmethod
    async def analyze(self, raw_data: Dict[str, Any], instance: str) -> InvestigationResult:
        """Transforma raw data em InvestigationResult estruturado."""

    @abstractmethod
    def get_steps_schema(self) -> List[Dict[str, str]]:
        """Declara os steps expostos por este investigator.

        Formato: [{"id": "step_1", "label": "...", "description_pt": "..."}]
        Usado pela UI para renderizar dinamicamente L4 mesmo antes de haver dados.
        """

    # --- Orchestration (override apenas se necessario) ---
    async def investigate(
        self,
        instance: str,
        triggered_by: str = "manual",
    ) -> InvestigationResult:
        """Collect + analyze + enrich. Fluxo padrao para todos os investigators."""
        start = time.time()
        investigation_id = f"{self.investigator_id}_{int(start)}_{uuid.uuid4().hex[:6]}"
        logger.info(
            "[Performance] Investigacao iniciada: %s / %s / triggered_by=%s",
            self.investigator_id, instance, triggered_by,
        )

        try:
            raw = await self.collect(instance)
        except Exception as e:
            logger.error("[Performance] collect() falhou: %s", e)
            return self._error_result(instance, investigation_id, f"Falha na colecta: {e}")

        try:
            result = await self.analyze(raw, instance)
        except Exception as e:
            logger.error("[Performance] analyze() falhou: %s", e)
            return self._error_result(instance, investigation_id, f"Falha na analise: {e}")

        # Meta
        result.investigation_id = investigation_id
        result.triggered_by = triggered_by
        result.duration_ms = int((time.time() - start) * 1000)

        # Enrich com engines (lazy imports para evitar ciclos)
        try:
            from modules.performance.engines.correlator import IncidentCorrelator
            from modules.performance.engines.baseline import BaselineComparator
            from modules.performance.engines.runbook import RunbookEngine
            from modules.performance.engines.ticket_generator import TicketResponseGenerator

            await IncidentCorrelator().link(result)
            await BaselineComparator().enrich(result)
            RunbookEngine().attach(result)
            result.ticket_response_pt = TicketResponseGenerator().generate(result)
        except Exception as e:
            logger.warning("[Performance] Enrichment falhou (nao fatal): %s", e)

        logger.info(
            "[Performance] Investigacao concluida: %s / sev=%s / count=%s / %dms",
            result.investigation_id, result.severity, result.count, result.duration_ms,
        )
        return result

    # --- Helpers ---
    def _error_result(self, instance: str, inv_id: str, msg: str) -> InvestigationResult:
        return InvestigationResult(
            investigator_id=self.investigator_id,
            instance=instance,
            investigation_id=inv_id,
            severity=SEVERITY_INFO,
            subtitle_pt="Nao foi possivel completar a investigacao",
            executive_summary_pt=msg,
            root_cause_pt=msg,
        )
