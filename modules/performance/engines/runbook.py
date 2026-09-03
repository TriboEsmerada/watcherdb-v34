"""RunbookEngine — carrega runbooks markdown e anexa historico de accoes.

Runbooks sao ficheiros markdown em modules/performance/runbooks/
Action history le performance_action_history para sugerir accoes passadas.
"""

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

RUNBOOKS_DIR = Path(__file__).parent.parent / "runbooks"


class RunbookEngine:
    """Carrega runbook.md + action history relevante."""

    def attach(self, result) -> None:
        """Preenche result.runbook_steps com passos do markdown."""
        runbook_path = RUNBOOKS_DIR / f"{result.investigator_id}.md"
        if runbook_path.exists():
            try:
                content = runbook_path.read_text(encoding="utf-8")
                result.runbook_steps = self._extract_steps(content)
            except Exception as e:
                logger.warning("[Runbook] falhou ao ler %s: %s", runbook_path, e)

        # Action history relevante (ex: "ja fizemos este mesmo CREATE INDEX antes?")
        try:
            self._attach_action_history(result)
        except Exception as e:
            logger.warning("[Runbook] action history falhou: %s", e)

    def _extract_steps(self, md: str) -> List[str]:
        """Extrai linhas que comecam com ## Passo N: ..."""
        steps = []
        for line in md.splitlines():
            s = line.strip()
            if s.startswith("## Passo") or s.startswith("## Step"):
                # Remove o prefixo markdown
                steps.append(s.lstrip("#").strip())
        return steps

    def _attach_action_history(self, result) -> None:
        """Procura accoes anteriores em objectos mencionados nas recommendations."""
        try:
            from api.connection_pool import execute_on_intelligence
        except ImportError:
            return

        # MVP: procurar accoes nos ultimos 90 dias na mesma instancia
        query = """
        SELECT TOP 5 action_id, action_type, action_sql, applied_at, applied_by,
               outcome_metric, outcome_before, outcome_after, notes_pt
        FROM dbo.performance_action_history WITH (NOLOCK)
        WHERE instance = ?
          AND applied_at >= DATEADD(DAY, -90, SYSUTCDATETIME())
          AND outcome_after IS NOT NULL
          AND outcome_before IS NOT NULL
          AND outcome_after < outcome_before  -- melhorou
        ORDER BY applied_at DESC
        """
        try:
            rows = execute_on_intelligence(
                query, params=(result.instance,)
            ) or []
            if rows:
                # Guardar em raw_dmv_data para L3 renderizar
                result.raw_dmv_data.setdefault("action_history", [])
                for r in rows:
                    result.raw_dmv_data["action_history"].append({
                        "applied_at": r["applied_at"].isoformat() if r.get("applied_at") else None,
                        "action_type": r.get("action_type"),
                        "outcome_metric": r.get("outcome_metric"),
                        "before": r.get("outcome_before"),
                        "after": r.get("outcome_after"),
                        "applied_by": r.get("applied_by"),
                        "notes_pt": r.get("notes_pt"),
                    })
        except Exception as e:
            logger.debug("[Runbook] action_history query falhou: %s", e)
