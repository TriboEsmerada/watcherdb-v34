"""
Testes para Connection Pool do WATCHERDB_DEV

Derivados da Auditoria Arquitetural
Modulo testado: api/connection_pool.py

Impacto se falhar: Corrupcao de estado do pool, conexoes duplicadas,
memory leaks, race conditions
"""

import pytest
import threading
import time
import os
import sys
from unittest.mock import patch, MagicMock

# Adicionar path para importar api/connection_pool
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestSQLServerConnectionPoolSingleton:
    """Testes do padrao Singleton do SQLServerConnectionPool"""

    def setup_method(self):
        """Reset singleton antes de cada teste"""
        from api.connection_pool import SQLServerConnectionPool
        SQLServerConnectionPool._instance = None

    def test_singleton_returns_same_instance(self):
        """Pool deve retornar mesma instancia"""
        from api.connection_pool import SQLServerConnectionPool

        pool1 = SQLServerConnectionPool()
        pool2 = SQLServerConnectionPool()

        assert pool1 is pool2
        assert id(pool1) == id(pool2)

    def test_singleton_thread_safety(self):
        """
        OBJETIVO: Verificar que apenas UMA instancia do pool e criada
        mesmo com multiplas threads instanciando simultaneamente.

        IMPACTO SE FALHAR: Multiplos pools, conexoes duplicadas,
        estatisticas incorretas
        """
        from api.connection_pool import SQLServerConnectionPool

        instances = []
        errors = []

        def create_instance():
            try:
                pool = SQLServerConnectionPool()
                instances.append(id(pool))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=create_instance) for _ in range(100)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Erros: {errors}"
        unique_ids = set(instances)
        assert len(unique_ids) == 1, f"Multiplas instancias criadas: {len(unique_ids)}"


class TestPoolLockThreadSafety:
    """Testes de thread-safety do sistema de locks do pool"""

    def setup_method(self):
        """Reset singleton antes de cada teste"""
        from api.connection_pool import SQLServerConnectionPool
        SQLServerConnectionPool._instance = None

    def test_get_pool_lock_returns_same_lock_for_same_key(self):
        """
        OBJETIVO: Verificar que _get_pool_lock retorna o MESMO lock
        para a mesma chave, mesmo com chamadas concorrentes.

        IMPACTO SE FALHAR: Duas threads podem entrar na secao critica
        simultaneamente, corrompendo o estado do pool
        """
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        pool._locks_dict.clear()

        locks_obtained = []
        errors = []

        def get_lock():
            try:
                lock = pool._get_pool_lock("TEST_KEY")
                locks_obtained.append(id(lock))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=get_lock) for _ in range(50)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Erros: {errors}"
        unique_locks = set(locks_obtained)
        assert len(unique_locks) == 1, f"Locks diferentes criados: {len(unique_locks)}"

    def test_get_pool_lock_returns_different_locks_for_different_keys(self):
        """Chaves diferentes devem ter locks diferentes"""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        pool._locks_dict.clear()

        lock_a = pool._get_pool_lock("KEY_A")
        lock_b = pool._get_pool_lock("KEY_B")

        assert lock_a is not lock_b

    def test_concurrent_access_to_different_pools_no_blocking(self):
        """Acesso concorrente a pools diferentes nao deve bloquear"""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        pool._locks_dict.clear()

        results = {'a_acquired': False, 'b_acquired': False}
        lock_a = pool._get_pool_lock("POOL_A")
        lock_b = pool._get_pool_lock("POOL_B")

        def thread_a():
            with lock_a:
                results['a_acquired'] = True
                time.sleep(0.1)

        def thread_b():
            time.sleep(0.02)
            with lock_b:
                results['b_acquired'] = True

        t1 = threading.Thread(target=thread_a)
        t2 = threading.Thread(target=thread_b)

        t1.start()
        t2.start()
        t1.join(timeout=2)
        t2.join(timeout=2)

        assert results['a_acquired'] is True
        assert results['b_acquired'] is True


class TestConnectionPoolStats:
    """Testes de estatisticas do pool"""

    def setup_method(self):
        from api.connection_pool import SQLServerConnectionPool
        SQLServerConnectionPool._instance = None

    def test_stats_structure(self):
        """get_stats deve retornar estrutura correta"""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        stats = pool.get_stats()

        assert 'total_connections_created' in stats
        assert 'active_connections' in stats
        assert 'pooled_connections' in stats
        assert 'connection_errors' in stats
        assert 'pool_hits' in stats
        assert 'pool_misses' in stats
        assert 'pool_hit_rate' in stats
        assert 'pools' in stats

    def test_pool_miss_increments_on_new_connection(self):
        """pool_misses deve incrementar quando nao ha conexao no pool"""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        initial_misses = pool.stats['pool_misses']

        with patch('api.connection_pool.pyodbc.connect') as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")
            pool.get_connection("FAKE_SERVER", "master")

        assert pool.stats['pool_misses'] == initial_misses + 1

    def test_connection_error_increments_on_failure(self):
        """connection_errors deve incrementar em caso de falha"""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        initial_errors = pool.stats['connection_errors']

        with patch('api.connection_pool.pyodbc.connect') as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")
            result = pool.get_connection("FAKE_SERVER", "master")

        assert result is None
        assert pool.stats['connection_errors'] == initial_errors + 1


class TestConnectionString:
    """Testes de construcao de connection string"""

    def setup_method(self):
        from api.connection_pool import SQLServerConnectionPool
        SQLServerConnectionPool._instance = None

    def test_converts_underscore_to_backslash(self):
        """server_id com underscore deve ser convertido para backslash"""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        conn_str = pool._build_connection_string("SERVIDOR_INSTANCIA", "master")

        assert "SERVER=SERVIDOR\\INSTANCIA" in conn_str

    def test_preserves_backslash_format(self):
        """server_id ja com backslash deve ser preservado"""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        conn_str = pool._build_connection_string("SERVIDOR\\INSTANCIA", "master")

        assert "SERVER=SERVIDOR\\INSTANCIA" in conn_str

    def test_uses_trusted_connection(self):
        """Connection string deve usar Windows Authentication"""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        conn_str = pool._build_connection_string("SERVER", "master")

        assert "Trusted_Connection=yes" in conn_str

    def test_includes_database(self):
        """Connection string deve incluir database"""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        conn_str = pool._build_connection_string("SERVER", "WatcherDB")

        assert "DATABASE=WatcherDB" in conn_str


class TestSQLAuthRollout:
    """FASE 1 least-privilege: branch SQL Auth guardado por allowlist de rollout.

    O ponto central: use_windows_auth ja' esta False em toda a frota no
    servers.json, por isso o branch NAO se liga a essa flag -- so' a allowlist
    explicita (_sql_auth_enabled_for) autoriza SQL Auth. Deploy do codigo com
    allowlist vazia tem de ser NEUTRO (todos Trusted).
    """

    def setup_method(self):
        from api.connection_pool import SQLServerConnectionPool
        SQLServerConnectionPool._instance = None

    def test_sql_auth_used_when_in_rollout(self):
        """Servidor NA allowlist + creds SQL Auth completas -> UID/PWD, sem Trusted."""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        pool._sql_auth_enabled_for = lambda sid: True
        pool._resolve_credentials = lambda sid: {
            'use_windows_auth': False, 'username': 'sql_monitoring', 'password': 'p@ss',
        }

        conn_str = pool._build_connection_string("SRV_INST", "master")

        assert "UID=sql_monitoring" in conn_str
        assert "PWD=p@ss" in conn_str
        assert "Trusted_Connection" not in conn_str

    def test_trusted_when_not_in_rollout_despite_sql_config(self):
        """Servidor FORA da allowlist continua Trusted, mesmo com use_windows_auth
        False no servers.json -- prova que o deploy inicial (allowlist vazia) e neutro."""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        pool._sql_auth_enabled_for = lambda sid: False
        pool._resolve_credentials = lambda sid: {
            'use_windows_auth': False, 'username': 'sql_monitoring', 'password': 'p@ss',
        }

        conn_str = pool._build_connection_string("SRV_INST", "master")

        assert "Trusted_Connection=yes" in conn_str
        assert "UID=" not in conn_str

    def test_fallback_trusted_when_creds_incomplete(self):
        """Servidor na allowlist mas sem password -> fallback Trusted (nao rebenta)."""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        pool._sql_auth_enabled_for = lambda sid: True
        pool._resolve_credentials = lambda sid: {
            'use_windows_auth': False, 'username': 'sql_monitoring', 'password': '',
        }

        conn_str = pool._build_connection_string("SRV_INST", "master")

        assert "Trusted_Connection=yes" in conn_str
        assert "UID=" not in conn_str

    def test_rollout_default_empty_when_file_missing(self, tmp_path):
        """Ficheiro de allowlist ausente -> fail-closed (nenhum servidor em SQL Auth)."""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        pool._sql_auth_rollout_path = str(tmp_path / "nao_existe.json")

        assert pool._sql_auth_enabled_for("ANY_SERVER") is False

    def test_rollout_reads_allowlist_and_wildcard(self, tmp_path):
        """Le a allowlist do ficheiro (case-insensitive) e honra o wildcard '*'."""
        import json
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        f = tmp_path / "sql_auth_rollout.json"
        f.write_text(json.dumps({"sql_auth_servers": ["SRV_INST"]}), encoding="utf-8")
        pool._sql_auth_rollout_path = str(f)

        assert pool._sql_auth_enabled_for("SRV_INST") is True
        assert pool._sql_auth_enabled_for("srv_inst") is True  # case-insensitive
        assert pool._sql_auth_enabled_for("OUTRO") is False

        # wildcard liga todos
        f.write_text(json.dumps({"sql_auth_servers": ["*"]}), encoding="utf-8")
        pool._sql_auth_rollout_loaded_at = 0.0  # forcar reload
        assert pool._sql_auth_enabled_for("QUALQUER_COISA") is True


class TestIntelligenceConnectionPool:
    """Testes do IntelligenceConnectionPool"""

    def setup_method(self):
        from api.connection_pool import IntelligenceConnectionPool
        IntelligenceConnectionPool._instance = None

    def test_singleton_pattern(self):
        """IntelligenceConnectionPool deve ser singleton"""
        from api.connection_pool import IntelligenceConnectionPool

        pool1 = IntelligenceConnectionPool()
        pool2 = IntelligenceConnectionPool()

        assert pool1 is pool2

    def test_uses_settings_for_configuration(self):
        """Pool deve usar pydantic-settings para configuracao"""
        from api.connection_pool import IntelligenceConnectionPool

        with patch('api.connection_pool.settings') as mock_settings:
            mock_settings.intelligence_server = 'TEST_SERVER\\I01'
            mock_settings.intelligence_database = 'TEST_DB'
            mock_settings.intelligence_use_windows_auth = True
            mock_settings.intelligence_sql_user = 'sql_monitoring'
            mock_settings.intelligence_sql_password = ''

            IntelligenceConnectionPool._instance = None
            pool = IntelligenceConnectionPool()

            assert pool.server == 'TEST_SERVER\\I01'
            assert pool.database == 'TEST_DB'

    def test_windows_auth_connection_string(self):
        """Windows auth deve gerar connection string correta"""
        from api.connection_pool import IntelligenceConnectionPool

        with patch('api.connection_pool.settings') as mock_settings:
            mock_settings.intelligence_use_windows_auth = True
            mock_settings.intelligence_server = 'TEST_SERVER'
            mock_settings.intelligence_database = 'TEST_DB'
            mock_settings.intelligence_sql_user = ''
            mock_settings.intelligence_sql_password = ''

            IntelligenceConnectionPool._instance = None
            pool = IntelligenceConnectionPool()
            conn_str = pool._build_connection_string()

            assert "Trusted_Connection=yes" in conn_str

    def test_sql_auth_requires_password(self):
        """SQL auth sem senha deve gerar erro.

        Audit 2026-04-22: adicionado mock de services.secrets.get_secret
        porque a pool resolve a password via os.environ (nao via settings),
        entao patch de settings nao e suficiente se o env real tiver
        INTELLIGENCE_SQL_PASSWORD definido (caso comum em dev).
        """
        from api.connection_pool import IntelligenceConnectionPool

        with patch('api.connection_pool.settings') as mock_settings, \
             patch('services.secrets.get_secret', return_value=''):
            mock_settings.intelligence_use_windows_auth = False
            mock_settings.intelligence_server = 'TEST_SERVER'
            mock_settings.intelligence_database = 'TEST_DB'
            mock_settings.intelligence_sql_user = 'user'
            mock_settings.intelligence_sql_password = ''

            IntelligenceConnectionPool._instance = None
            pool = IntelligenceConnectionPool()

            with pytest.raises(ValueError, match="requer senha"):
                pool._build_connection_string()


class TestHelperFunctions:
    """Testes das funcoes helper"""

    def setup_method(self):
        from api.connection_pool import SQLServerConnectionPool, IntelligenceConnectionPool
        SQLServerConnectionPool._instance = None
        IntelligenceConnectionPool._instance = None

    def test_get_sql_server_pool_returns_singleton(self):
        """get_sql_server_pool deve retornar sempre a mesma instancia"""
        from api.connection_pool import get_sql_server_pool

        pool1 = get_sql_server_pool()
        pool2 = get_sql_server_pool()

        assert pool1 is pool2

    def test_get_intelligence_pool_returns_singleton(self):
        """get_intelligence_pool deve retornar sempre a mesma instancia"""
        from api.connection_pool import get_intelligence_pool

        pool1 = get_intelligence_pool()
        pool2 = get_intelligence_pool()

        assert pool1 is pool2

    def test_execute_on_server_handles_connection_failure(self):
        """execute_on_server deve levantar excecao se conexao falhar"""
        from api.connection_pool import execute_on_server

        with patch('api.connection_pool.pyodbc.connect') as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")

            with pytest.raises(Exception, match="Não foi possível conectar"):
                execute_on_server("FAKE_SERVER", "SELECT 1")


class TestConnectionLifecycle:
    """Testes do ciclo de vida das conexoes"""

    def setup_method(self):
        from api.connection_pool import SQLServerConnectionPool
        SQLServerConnectionPool._instance = None

    def test_return_connection_validates_before_pooling(self):
        """return_connection deve validar conexao antes de devolver ao pool"""
        import pyodbc
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()

        # Mock de conexao invalida — usa pyodbc.Error (tipo real capturado no pool)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = pyodbc.Error("HY000", "Connection closed")
        mock_conn.cursor.return_value = mock_cursor

        pool.return_connection("TEST_SERVER", mock_conn, "master")

        # Conexao invalida deve ser fechada, nao devolvida ao pool
        mock_conn.close.assert_called()

    def test_return_connection_pools_valid_connection(self):
        """return_connection deve adicionar conexao valida ao pool"""
        from api.connection_pool import SQLServerConnectionPool

        pool = SQLServerConnectionPool()
        pool_key = "TEST_SERVER_master"

        # Limpar pool
        pool.pools[pool_key] = []

        # Mock de conexao valida
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        pool.return_connection("TEST_SERVER", mock_conn, "master")

        # Conexao deve estar no pool
        assert len(pool.pools[pool_key]) == 1
