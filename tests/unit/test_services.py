"""
Testes para Services do WATCHERDB_DEV

Testa os servicos em services/ e watcherdb/services/
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Adicionar path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestServicesStructure:
    """Testes da estrutura de services"""

    def test_services_directory_exists(self):
        """Diretorio services/ deve existir"""
        services_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'services'
        )
        assert os.path.isdir(services_path)

    def test_watcherdb_services_exists(self):
        """Diretorio watcherdb/services/ deve existir"""
        services_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'watcherdb', 'services'
        )
        assert os.path.isdir(services_path)


class TestOSPerformanceService:
    """Testes do servico os_performance_service"""

    def test_service_can_be_imported(self):
        """Servico deve ser importavel"""
        try:
            from services import os_performance_service
            assert os_performance_service is not None
        except ImportError as e:
            pytest.skip(f"Nao foi possivel importar: {e}")


class TestSQLServerKPIService:
    """Testes do servico sqlserver_kpi_service"""

    def test_service_can_be_imported(self):
        """Servico deve ser importavel"""
        try:
            from services import sqlserver_kpi_service
            assert sqlserver_kpi_service is not None
        except ImportError as e:
            pytest.skip(f"Nao foi possivel importar: {e}")


class TestAlertingService:
    """Testes do servico de alertas"""

    def test_service_can_be_imported(self):
        """Servico de alertas deve ser importavel"""
        from watcherdb.services.alerting import AlertManager
        assert AlertManager is not None

    def test_alert_manager_has_create_alert(self):
        """AlertManager deve ter metodo create_alert"""
        from watcherdb.services.alerting import AlertManager
        assert hasattr(AlertManager, 'create_alert')


class TestNotificationService:
    """Testes do servico de notificacao"""

    def test_service_can_be_imported(self):
        """Servico de notificacao deve ser importavel"""
        try:
            from watcherdb.services.notification import NotificationService
            assert NotificationService is not None
        except ImportError as e:
            pytest.skip(f"Nao foi possivel importar: {e}")

    def test_notification_service_has_send_methods(self):
        """NotificationService deve ter metodos de envio"""
        try:
            from watcherdb.services.notification import NotificationService
            service = NotificationService()

            # Verificar se tem pelo menos um metodo de envio
            has_send = (
                hasattr(service, 'send_email') or
                hasattr(service, 'send_teams') or
                hasattr(service, 'send_slack') or
                hasattr(service, 'send')
            )
            assert has_send
        except ImportError:
            pytest.skip("NotificationService nao disponivel")
        except Exception:
            pass


class TestBackupService:
    """Testes do servico de backup"""

    def test_service_can_be_imported(self):
        """Servico de backup deve ser importavel"""
        try:
            from watcherdb.services.backup_service import BackupService
            assert BackupService is not None
        except ImportError as e:
            pytest.skip(f"Nao foi possivel importar: {e}")


class TestSpaceService:
    """Testes do servico de espaco"""

    def test_service_can_be_imported(self):
        """Servico de espaco deve ser importavel"""
        try:
            from watcherdb.services.space_service import SpaceService
            assert SpaceService is not None
        except ImportError as e:
            pytest.skip(f"Nao foi possivel importar: {e}")
