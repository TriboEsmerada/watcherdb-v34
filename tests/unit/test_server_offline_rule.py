"""
Regression test para business rule "server-offline-vs-service-down":

    Um servico SQL parado num servidor OFFLINE e consequencia, nao causa
    independente. Logo nao deve double-count:
      - Se server ping=OK e service parado -> conta em servers_sql_down
      - Se server ping=FAIL -> conta em servers_offline APENAS (mesmo que
        service tambem esteja parado — e consequencia)

Bug reportado 2026-04-23: card "SQL Services Down" mostrava valor inflado
porque servidores offline estavam a ser contados tambem em sql_down.

Fix em api/routers/intelligence/helpers.py — fallback DET re-escrito para
aplicar Ping_OK como discriminator.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


# Dados mock representativos: 14 servers offline + 5 sql_down real + 2 partial.
# Total = 21 eventos; com a regra, servers_sql_down deve ser 5 (nao 14+5=19).
_DET_MOCK_DATA: list[dict[str, Any]] = (
    # 14 offline (ping fail)
    [
        {"Server_Name": f"SRV_OFFLINE_{i:02d}", "Diagnosis": "offline", "Ping_OK": 0}
        for i in range(1, 15)
    ]
    # 5 sql_down real (ping OK mas service parado)
    + [
        {"Server_Name": f"SRV_SQL_{i}", "Diagnosis": "sql_down", "Ping_OK": 1}
        for i in range(1, 6)
    ]
    # 2 partial
    + [
        {"Server_Name": f"SRV_PART_{i}", "Diagnosis": "partial", "Ping_OK": 1}
        for i in range(1, 3)
    ]
)


class TestServerOfflineBusinessRule:
    """Exercita collect_server_offline() em helpers.py com DET mockado."""

    @pytest.fixture
    def results_skeleton(self) -> dict:
        """Estrutura esperada pelo collector (inicializacao vazia)."""
        return {
            "server_offline_status": {
                "servers_offline": 0,
                "servers_sql_down": 0,
                "servers_partial": 0,
                "total_events": 0,
                "overall_status": "OK",
                "last_event_time": None,
                "instances": [],
                "by_env": {},
            }
        }

    @pytest.mark.asyncio
    async def test_offline_not_double_counted_as_sql_down(self, results_skeleton):
        """14 offline + 5 sql_down + 2 partial = 14 offline, 5 sql_down, 2 partial."""
        from api.routers.intelligence.helpers import collect_server_offline

        async def _mock_query(q: str, **kwargs):
            # AGG retorna vazio (coluna Servers_SQL_Down nao existe na view actual)
            if "AGG_VIEW" in q:
                return []
            # DET retorna dados mockados
            if "DET_VIEW" in q:
                return list(_DET_MOCK_DATA)
            return []

        with patch(
            "api.routers.intelligence.helpers.execute_intelligence_query_async",
            new=AsyncMock(side_effect=_mock_query),
        ):
            await collect_server_offline(results_skeleton)

        status = results_skeleton["server_offline_status"]
        assert status["servers_offline"] == 14, (
            f"Expected 14 offline (ping=0), got {status['servers_offline']}"
        )
        assert status["servers_sql_down"] == 5, (
            f"Expected 5 sql_down (ping=1), got {status['servers_sql_down']}. "
            f"Se >5: os servidores offline estao a ser contados como sql_down tambem "
            f"(double-count bug regressou)."
        )
        assert status["servers_partial"] == 2, (
            f"Expected 2 partial (ping=1), got {status['servers_partial']}"
        )
        assert status["total_events"] == 21  # 14 + 5 + 2
        assert status["overall_status"] == "CRITICAL"  # offline > 0

    @pytest.mark.asyncio
    async def test_edge_case_offline_with_sql_down_diagnosis(self, results_skeleton):
        """Servidor offline que tambem tem service parado NAO deve double-count.

        Este e o cenario do bug: collector pode registar 2 eventos (um offline,
        outro sql_down) para o mesmo servidor na mesma janela. A regra garante
        que so o offline conta.
        """
        from api.routers.intelligence.helpers import collect_server_offline

        # SRV01 tem DOIS eventos — ordem ORDER BY coloca offline primeiro
        det_ambig = [
            {"Server_Name": "SRV01", "Diagnosis": "offline", "Ping_OK": 0},
            {"Server_Name": "SRV01", "Diagnosis": "sql_down", "Ping_OK": 0},  # ping=0 ainda
            # SRV02 e realmente sql_down (ping OK)
            {"Server_Name": "SRV02", "Diagnosis": "sql_down", "Ping_OK": 1},
        ]

        async def _mock_query(q: str, **kwargs):
            if "DET_VIEW" in q:
                return list(det_ambig)
            return []

        with patch(
            "api.routers.intelligence.helpers.execute_intelligence_query_async",
            new=AsyncMock(side_effect=_mock_query),
        ):
            await collect_server_offline(results_skeleton)

        status = results_skeleton["server_offline_status"]
        assert status["servers_offline"] == 1, "SRV01 (ping=0) -> offline"
        assert status["servers_sql_down"] == 1, "So SRV02 (ping=1) -> sql_down"
        # SRV01 NAO deve aparecer em sql_down mesmo que o collector tenha gravado
        # evento sql_down para ele (o servidor estava offline).

    @pytest.mark.asyncio
    async def test_sql_down_with_ping_zero_rejected(self, results_skeleton):
        """Se o collector gravou Diagnosis=sql_down mas Ping_OK=0, regra bloqueia."""
        from api.routers.intelligence.helpers import collect_server_offline

        det = [
            {"Server_Name": "SRV_A", "Diagnosis": "sql_down", "Ping_OK": 0},
            {"Server_Name": "SRV_B", "Diagnosis": "sql_down", "Ping_OK": 1},
        ]

        async def _mock_query(q: str, **kwargs):
            if "DET_VIEW" in q:
                return list(det)
            return []

        with patch(
            "api.routers.intelligence.helpers.execute_intelligence_query_async",
            new=AsyncMock(side_effect=_mock_query),
        ):
            await collect_server_offline(results_skeleton)

        status = results_skeleton["server_offline_status"]
        # SRV_A tem sql_down mas ping=0 -> nao conta em NENHUM dos counts
        # (nao e offline porque Diagnosis != 'offline' na regra tb)
        assert status["servers_sql_down"] == 1, "Apenas SRV_B (ping=1) conta"
        assert status["servers_offline"] == 0, "SRV_A nao e 'offline' diagnosis"

    @pytest.mark.asyncio
    async def test_empty_det_gives_all_ok(self, results_skeleton):
        """Sem dados -> tudo zero + status OK."""
        from api.routers.intelligence.helpers import collect_server_offline

        async def _mock_query(q: str, **kwargs):
            return []

        with patch(
            "api.routers.intelligence.helpers.execute_intelligence_query_async",
            new=AsyncMock(side_effect=_mock_query),
        ):
            await collect_server_offline(results_skeleton)

        status = results_skeleton["server_offline_status"]
        assert status["servers_offline"] == 0
        assert status["servers_sql_down"] == 0
        assert status["servers_partial"] == 0

    @pytest.mark.asyncio
    async def test_by_env_matches_card_count_not_total(self, results_skeleton):
        """Bug 2026-04-23: tooltip by_env inflado. by_env deve contar so
        sql_down+ping_ok=1 para bater com o count do card (nao todos os diagnosis).

        Cenario real do user: 40 PRD + 14 QLT + 4 TST = 58 no tooltip mas
        card mostrava 1. Apos fix: tooltip mostra apenas o 1 sql_down real.
        """
        from api.routers.intelligence.helpers import collect_server_offline

        # Simulacao: 40 offline PRD + 14 offline QLT + 4 offline TST + 1 sql_down QLT
        det = (
            [{"Server_Name": f"P{i}", "Diagnosis": "offline", "Ping_OK": 0, "Env": "PRD"} for i in range(40)]
            + [{"Server_Name": f"Q{i}", "Diagnosis": "offline", "Ping_OK": 0, "Env": "QLT"} for i in range(14)]
            + [{"Server_Name": f"T{i}", "Diagnosis": "offline", "Ping_OK": 0, "Env": "TST"} for i in range(4)]
            + [{"Server_Name": "SRV_QLT_REAL_SQL_DOWN", "Diagnosis": "sql_down", "Ping_OK": 1, "Env": "QLT"}]
        )

        async def _mock_query(q: str, **kwargs):
            if "DET_VIEW" in q:
                return list(det)
            return []

        with patch(
            "api.routers.intelligence.helpers.execute_intelligence_query_async",
            new=AsyncMock(side_effect=_mock_query),
        ):
            await collect_server_offline(results_skeleton)

        status = results_skeleton["server_offline_status"]
        # Card count = 1 (so o sql_down+ping_ok=1)
        assert status["servers_sql_down"] == 1
        # by_env (tooltip do card SQL Services Down) = 1 QLT (nao 58)
        assert status["by_env"] == {"QLT": 1}, (
            f"tooltip by_env deve bater com card. Esperado {{'QLT': 1}}, got {status['by_env']}"
        )
        # by_env_offline separado tem os 58
        assert status["by_env_offline"] == {"PRD": 40, "QLT": 14, "TST": 4}
        # Total offline = 58, nao deve contribuir para sql_down count nem tooltip
        assert status["servers_offline"] == 58

    @pytest.mark.asyncio
    async def test_only_warning_when_sql_down_but_no_offline(self, results_skeleton):
        """sql_down sem offline -> overall_status=WARNING, nao CRITICAL."""
        from api.routers.intelligence.helpers import collect_server_offline

        det = [
            {"Server_Name": f"SRV_{i}", "Diagnosis": "sql_down", "Ping_OK": 1}
            for i in range(3)
        ]

        async def _mock_query(q: str, **kwargs):
            if "DET_VIEW" in q:
                return list(det)
            return []

        with patch(
            "api.routers.intelligence.helpers.execute_intelligence_query_async",
            new=AsyncMock(side_effect=_mock_query),
        ):
            await collect_server_offline(results_skeleton)

        status = results_skeleton["server_offline_status"]
        assert status["servers_offline"] == 0
        assert status["servers_sql_down"] == 3
        assert status["overall_status"] == "WARNING"
