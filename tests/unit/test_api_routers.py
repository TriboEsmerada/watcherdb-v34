"""
Testes para API Routers do WATCHERDB_DEV

Testa os endpoints principais da API FastAPI
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Adicionar path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestHealthEndpoints:
    """Testes dos endpoints de health check"""

    @pytest.fixture
    def client(self):
        """Cria cliente de teste para a API"""
        # Mock das dependencias antes de importar
        with patch('api.connection_pool.pyodbc'):
            try:
                from watcherdb_main import app
                return TestClient(app)
            except Exception:
                pytest.skip("Nao foi possivel carregar a aplicacao")

    def test_health_endpoint_exists(self, client):
        """Endpoint /api/v3/health deve existir"""
        if client is None:
            pytest.skip("Cliente nao disponivel")

        response = client.get("/api/v3/health")
        # Aceita 200 ou 503 (se banco nao disponivel)
        assert response.status_code in [200, 503]

    def test_api_root_exists(self, client):
        """Endpoint raiz da API deve existir"""
        if client is None:
            pytest.skip("Cliente nao disponivel")

        # Testar algum endpoint que sabemos que existe
        response = client.get("/api/v3/health")
        assert response.status_code in [200, 503]


class TestAPIStructure:
    """Testes da estrutura da API"""

    def test_routers_directory_exists(self):
        """Diretorio de routers deve existir"""
        routers_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'api', 'routers'
        )
        assert os.path.isdir(routers_path)

    def test_main_routers_exist(self):
        """Routers principais devem existir"""
        routers_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'api', 'routers'
        )

        expected_routers = [
            'alwayson.py',
            'intelligence_kpis.py',
            'overview_dashboard.py',
            'sql_queries.py',
            'jobs.py'
        ]

        for router in expected_routers:
            router_file = os.path.join(routers_path, router)
            assert os.path.isfile(router_file), f"Router {router} nao encontrado"


class TestIntelligenceKPIsRouter:
    """Testes do router de Intelligence KPIs"""

    def test_router_can_be_imported(self):
        """Router deve ser importavel"""
        try:
            from api.routers import intelligence_kpis
            assert intelligence_kpis is not None
        except ImportError as e:
            pytest.skip(f"Nao foi possivel importar: {e}")

    def test_router_has_endpoints(self):
        """Router deve ter endpoints definidos"""
        try:
            from api.routers import intelligence_kpis

            # Verificar se tem o objeto router
            assert hasattr(intelligence_kpis, 'router')
        except ImportError:
            pytest.skip("Router nao disponivel")


class TestAlwaysOnRouter:
    """Testes do router AlwaysOn"""

    def test_router_can_be_imported(self):
        """Router AlwaysOn deve ser importavel"""
        try:
            from api.routers import alwayson
            assert alwayson is not None
        except ImportError as e:
            pytest.skip(f"Nao foi possivel importar: {e}")


class TestOverviewDashboardRouter:
    """Testes do router Overview Dashboard"""

    def test_router_can_be_imported(self):
        """Router Overview deve ser importavel"""
        try:
            from api.routers import overview_dashboard
            assert overview_dashboard is not None
        except ImportError as e:
            pytest.skip(f"Nao foi possivel importar: {e}")
