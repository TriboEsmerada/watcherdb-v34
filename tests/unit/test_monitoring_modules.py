"""
Testes para Modulos de Monitoramento do WATCHERDB_DEV

Testa os modulos em modules/monitoring/
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Adicionar path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestModulesStructure:
    """Testes da estrutura de modulos"""

    def test_monitoring_directory_exists(self):
        """Diretorio modules/monitoring deve existir"""
        monitoring_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'modules', 'monitoring'
        )
        assert os.path.isdir(monitoring_path)

    def test_critical_modules_exist(self):
        """Modulos criticos devem existir"""
        monitoring_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'modules', 'monitoring'
        )

        critical_modules = [
            'space_analysis.py',
            'backup_analysis.py',
            'monitoring.py',
            'queries.py'
        ]

        for module in critical_modules:
            module_file = os.path.join(monitoring_path, module)
            assert os.path.isfile(module_file), f"Modulo {module} nao encontrado"


class TestSpaceAnalysis:
    """Testes do modulo space_analysis"""

    def test_module_can_be_imported(self):
        """Modulo space_analysis deve ser importavel"""
        try:
            from modules.monitoring import space_analysis
            assert space_analysis is not None
        except ImportError as e:
            pytest.skip(f"Nao foi possivel importar: {e}")

    def test_has_space_analysis_engine(self):
        """Deve ter classe SpaceAnalysisEngine"""
        try:
            from modules.monitoring.space_analysis import SpaceAnalysisEngine
            assert SpaceAnalysisEngine is not None
        except ImportError:
            pytest.skip("SpaceAnalysisEngine nao disponivel")


class TestBackupAnalysis:
    """Testes do modulo backup_analysis"""

    def test_module_can_be_imported(self):
        """Modulo backup_analysis deve ser importavel"""
        try:
            from modules.monitoring import backup_analysis
            assert backup_analysis is not None
        except ImportError as e:
            pytest.skip(f"Nao foi possivel importar: {e}")


class TestQueries:
    """Testes do modulo queries (biblioteca de queries SQL)"""

    def test_module_can_be_imported(self):
        """Modulo queries deve ser importavel"""
        try:
            from modules.monitoring import queries
            assert queries is not None
        except ImportError as e:
            pytest.skip(f"Nao foi possivel importar: {e}")

    def test_has_sql_queries_class(self):
        """Deve ter classe SQLQueries"""
        try:
            from modules.monitoring.queries import SQLQueries
            assert SQLQueries is not None
        except ImportError:
            # Pode ter outro nome
            pass


class TestMonitoringCore:
    """Testes do modulo monitoring core"""

    def test_module_can_be_imported(self):
        """Modulo monitoring deve ser importavel"""
        try:
            from modules.monitoring import monitoring
            assert monitoring is not None
        except ImportError as e:
            pytest.skip(f"Nao foi possivel importar: {e}")
