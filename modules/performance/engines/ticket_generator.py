"""TicketResponseGenerator — gera texto PT para TBSM/Dynatrace/generico.

Usa o InvestigationResult completo e produz um resumo copy-paste-ready
que o DBA pode colar no ticket para informar stakeholders.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TicketResponseGenerator:
    """Gera resposta a ticket em PT, adaptada ao template escolhido."""

    def generate(
        self,
        result,
        template: str = "default",       # "tbsm" | "dynatrace" | "default" | "executive"
        action_taken: bool = False,
        pending_approval: bool = False,
        dba_name: str = "DBA Team",
    ) -> str:
        """Gera texto formatado para o ticket."""

        if template == "executive":
            return self._executive_only(result)

        triggered_str = result.triggered_at.strftime("%H:%M") if result.triggered_at else "N/A"
        duration_min = result.estimated_impact.duration_min if result.estimated_impact else 0

        action_desc = (
            "Accao ja aplicada (ver detalhes no modal de investigacao)."
            if action_taken
            else "Accao proposta, pendente de aprovacao."
        )
        approval_note = (
            "\n⚠ Requer aprovacao previa antes da implementacao em producao."
            if pending_approval and not action_taken
            else ""
        )

        # Lista de entidades criticas (top 3 recommendations)
        critical_entities = []
        for rec in (result.recommendations or [])[:3]:
            critical_entities.append(f"  • {rec.description_pt}")
        critical_list = "\n".join(critical_entities) or "  (sem entidades especificas identificadas)"

        business_impact = (
            result.business_impact_pt
            or f"{result.estimated_impact.users_affected} utilizadores potencialmente afectados"
        )

        txt = f"""Caros,

O alerta foi recebido e a investigacao foi concluida.

**Contexto**
{result.executive_summary_pt or 'Investigacao automatica executada pelo WatcherDB.'}

Instancia: {result.instance}
Investigador: {result.investigator_id}
Detectado as: {triggered_str} (duracao: {duration_min} min)
Severity: {result.severity}
Confidence: {result.confidence_score:.0f}%

**Causa raiz identificada**
{result.root_cause_pt or 'Em analise.'}

As entidades mais criticas identificadas:
{critical_list}

**Impacto estimado**
• Utilizadores afectados: {result.estimated_impact.users_affected}
• Risco SLA: {result.estimated_impact.sla_risk}
• Processos de negocio: {business_impact}

**Accao {'tomada' if action_taken else 'proposta'}**
{action_desc}{approval_note}

**Monitorizacao**
Investigacao registada no WatcherDB (ID: {result.investigation_id}).
{self._correlated_note(result)}

Qualquer questao, estamos disponiveis.

Cumprimentos,
{dba_name} — Equipa DBA
"""
        return txt

    def _executive_only(self, result) -> str:
        """Versao curta — 1 paragrafo para email/Slack rapido."""
        return (
            f"[{result.severity}] {result.investigator_id} em {result.instance}: "
            f"{result.executive_summary_pt} "
            f"Impacto: {result.estimated_impact.users_affected} utilizadores, "
            f"SLA {result.estimated_impact.sla_risk}. "
            f"Investigacao: {result.investigation_id}."
        )

    def _correlated_note(self, result) -> str:
        if not result.correlated_investigations:
            return ""
        n = len(result.correlated_investigations)
        return f"Correlacionado com {n} outras investigacoes nos ultimos 10min."
