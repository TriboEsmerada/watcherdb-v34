"""
Database Discovery Service - Descoberta automatica de databases por instancia

Este servico:
1. Varre todas as instancias configuradas
2. Descobre os databases existentes em cada uma
3. Atualiza os arquivos JSON (servers.json e sql_servers.json)
4. Mantem cache em memoria para consultas rapidas

Autor: WatcherDB
Data: 2026-01-21
"""

import logging
import json
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path
from decimal import Decimal

logger = logging.getLogger(__name__)

# Cache em memoria dos databases por servidor
_DATABASES_CACHE: Dict[str, Dict] = {}

# Cache de erros de descoberta
_ERRORS_CACHE: Dict[str, Dict] = {}


def _serialize_for_json(obj: Any) -> Any:
    """Serializa objetos para JSON (Decimal, datetime, etc)"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    return obj


class DatabaseDiscoveryService:
    """
    Servico para descoberta automatica de databases por instancia SQL Server.

    Uso:
        service = DatabaseDiscoveryService()
        await service.discover_all()  # Descobre em todas as instancias
        await service.discover_server("OATXP01")  # Descobre em uma instancia
    """

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.servers_json_path = self.config_dir / "servers.json"
        self.sql_servers_json_path = self.config_dir / "sql_servers.json"

        # Query para descobrir databases
        self.discovery_query = """
        SELECT
            name AS database_name,
            database_id,
            state_desc AS state,
            recovery_model_desc AS recovery_model,
            CAST(is_read_only AS INT) AS is_read_only,
            CASE
                WHEN state = 0 AND HAS_DBACCESS(name) = 1 THEN 1
                ELSE 0
            END AS is_accessible,
            create_date,
            compatibility_level
        FROM sys.databases WITH(NOLOCK)
        WHERE database_id > 0  -- Exclui resource database
        ORDER BY name
        """

    def _load_json(self, path: Path) -> Optional[Dict]:
        """Carrega arquivo JSON com tratamento de erro."""
        try:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao carregar {path}: {e}")
        return None

    def _save_json(self, path: Path, data: Dict) -> bool:
        """Salva arquivo JSON com backup."""
        try:
            # Criar backup antes de sobrescrever
            if path.exists():
                backup_path = path.with_suffix(f'.json.bak_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
                # Nao criar backup toda vez - apenas se nao existir um recente
                existing_backups = list(path.parent.glob(f"{path.stem}.json.bak_*"))
                if len(existing_backups) < 5:  # Manter no maximo 5 backups
                    import shutil
                    shutil.copy2(path, backup_path)

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(_serialize_for_json(data), f, indent=2, ensure_ascii=False)

            logger.info(f"Arquivo salvo: {path}")
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar {path}: {e}")
            return False

    async def discover_server(self, server_id: str, executor_func=None) -> Dict[str, Any]:
        """
        Descobre databases de uma instancia especifica.

        Args:
            server_id: ID do servidor (ex: "OATXP01" ou "SQLHDSPRD201_I01")
            executor_func: Funcao async para executar query (injetada)

        Returns:
            Dict com informacoes dos databases descobertos
        """
        result = {
            'server_id': server_id,
            'success': False,
            'databases': [],
            'discovered_at': datetime.now().isoformat(),
            'error': None
        }

        try:
            if executor_func is None:
                # Import tardio para evitar dependencia circular
                from api.routers.sql_queries import execute_query_on_server
                executor_func = execute_query_on_server

            # Executar query de descoberta
            query_result = await executor_func(server_id, self.discovery_query, command_timeout=15, connection_timeout=10)

            if query_result:
                databases = []
                for row in query_result:
                    db_info = {
                        'name': row.get('database_name', ''),
                        'database_id': row.get('database_id'),
                        'state': row.get('state', 'UNKNOWN'),
                        'recovery_model': row.get('recovery_model', ''),
                        'is_read_only': bool(row.get('is_read_only', 0)),
                        'is_accessible': bool(row.get('is_accessible', 0)),
                        'compatibility_level': row.get('compatibility_level')
                    }
                    databases.append(db_info)

                result['databases'] = databases
                result['success'] = True
                result['database_count'] = len(databases)

                # Atualizar cache em memoria
                _DATABASES_CACHE[server_id.upper()] = {
                    'databases': databases,
                    'discovered_at': result['discovered_at'],
                    'database_count': len(databases)
                }

                logger.info(f"Descobertos {len(databases)} databases em {server_id}")
            else:
                result['error'] = "Query retornou resultado vazio"

        except Exception as e:
            result['error'] = str(e)
            # Armazenar erro no cache
            _ERRORS_CACHE[server_id.upper()] = {
                'server_id': server_id,
                'error': str(e),
                'failed_at': result['discovered_at']
            }
            # Usar DEBUG para erros de conexao (esperados para servidores offline)
            if '08001' in str(e) or 'connection' in str(e).lower() or 'timeout' in str(e).lower():
                logger.debug(f"Servidor {server_id} inacessivel: {e}")
            else:
                logger.warning(f"Erro ao descobrir databases de {server_id}: {e}")

        return result

    async def discover_all(self, executor_func=None, max_concurrent: int = 5) -> Dict[str, Any]:
        """
        Descobre databases de todas as instancias configuradas.

        Args:
            executor_func: Funcao async para executar query
            max_concurrent: Maximo de descobertas simultaneas

        Returns:
            Dict com resumo da descoberta
        """
        # Carregar lista de servidores
        servers_data = self._load_json(self.servers_json_path)
        if not servers_data:
            return {'success': False, 'error': 'Falha ao carregar servers.json'}

        monitored = servers_data.get('monitored_servers', [])

        # Filtrar apenas servidores habilitados
        enabled_servers = [s for s in monitored if s.get('enabled', True)]

        logger.info(f"Iniciando descoberta em {len(enabled_servers)} servidores...")

        results = {
            'success': True,
            'started_at': datetime.now().isoformat(),
            'total_servers': len(enabled_servers),
            'successful': 0,
            'failed': 0,
            'total_databases': 0,
            'servers': {}
        }

        # Processar em lotes para nao sobrecarregar
        semaphore = asyncio.Semaphore(max_concurrent)

        async def discover_with_limit(server):
            async with semaphore:
                server_id = server.get('id', '')
                if not server_id:
                    return None
                return await self.discover_server(server_id, executor_func)

        tasks = [discover_with_limit(s) for s in enabled_servers]
        discoveries = await asyncio.gather(*tasks, return_exceptions=True)

        for discovery in discoveries:
            if isinstance(discovery, Exception):
                results['failed'] += 1
                continue

            if discovery and discovery.get('success'):
                results['successful'] += 1
                results['total_databases'] += discovery.get('database_count', 0)
                results['servers'][discovery['server_id']] = {
                    'database_count': discovery.get('database_count', 0),
                    'databases': [d['name'] for d in discovery.get('databases', [])]
                }
            else:
                results['failed'] += 1
                if discovery:
                    results['servers'][discovery.get('server_id', 'unknown')] = {
                        'error': discovery.get('error', 'Unknown error')
                    }

        results['completed_at'] = datetime.now().isoformat()

        # Atualizar arquivos JSON se teve sucesso
        if results['successful'] > 0:
            await self._update_json_files()

        logger.info(f"Descoberta completa: {results['successful']}/{results['total_servers']} servidores, {results['total_databases']} databases")

        return results

    async def _update_json_files(self) -> bool:
        """Atualiza os arquivos JSON com os databases descobertos.

        E6b (2026-08-19): com settings.inventory_source == "db" o catalogo de databases
        e' da discovery do collector V1 (servers.json canonico -> metadata.monitored_server_database);
        escrever aqui criaria uma 2a fonte. Mantem-se a cache em memoria (endpoints /api/discover/*),
        mas NAO se escreve nos ficheiros locais. settings.inventory_source="file" repoe o comportamento."""
        try:
            try:
                from watcherdb.core.settings import settings as _settings
                if (getattr(_settings, "inventory_source", "db") or "db").lower() == "db":
                    logger.info("[DISCOVERY_V33] inventory_source=db -> nao escreve servers.json/sql_servers.json locais "
                                "(catalogo de databases vem do collector V1); cache em memoria actualizada")
                    return True
            except Exception:
                pass
            # Atualizar servers.json
            servers_data = self._load_json(self.servers_json_path)
            if servers_data:
                for server in servers_data.get('monitored_servers', []):
                    server_id = server.get('id', '').upper()
                    if server_id in _DATABASES_CACHE:
                        cache_entry = _DATABASES_CACHE[server_id]
                        server['databases'] = cache_entry['databases']
                        server['databases_discovered_at'] = cache_entry['discovered_at']
                        server['database_count'] = cache_entry['database_count']

                self._save_json(self.servers_json_path, servers_data)

            # Atualizar sql_servers.json
            sql_servers_data = self._load_json(self.sql_servers_json_path)
            if sql_servers_data:
                for server in sql_servers_data.get('servers', []):
                    server_id = server.get('id', '').upper()
                    if server_id in _DATABASES_CACHE:
                        cache_entry = _DATABASES_CACHE[server_id]
                        # Versao simplificada para sql_servers.json
                        server['databases'] = [d['name'] for d in cache_entry['databases']]
                        server['databases_discovered_at'] = cache_entry['discovered_at']
                        server['database_count'] = cache_entry['database_count']

                # Atualizar metadata
                if 'metadata' in sql_servers_data:
                    sql_servers_data['metadata']['last_discovery'] = datetime.now().isoformat()

                self._save_json(self.sql_servers_json_path, sql_servers_data)

            return True
        except Exception as e:
            logger.error(f"Erro ao atualizar arquivos JSON: {e}")
            return False

    def get_cached_databases(self, server_id: str) -> Optional[Dict]:
        """Retorna databases do cache em memoria."""
        return _DATABASES_CACHE.get(server_id.upper())

    def get_all_cached(self) -> Dict[str, Dict]:
        """Retorna todo o cache de databases."""
        return _DATABASES_CACHE.copy()

    def clear_cache(self):
        """Limpa o cache em memoria."""
        _DATABASES_CACHE.clear()
        _ERRORS_CACHE.clear()
        logger.info("Cache de databases limpo")

    def get_failed_servers(self) -> Dict[str, Dict]:
        """Retorna servidores que falharam na descoberta."""
        return _ERRORS_CACHE.copy()

    def get_failed_count(self) -> int:
        """Retorna quantidade de servidores que falharam."""
        return len(_ERRORS_CACHE)


# Instancia global (singleton)
_discovery_service: Optional[DatabaseDiscoveryService] = None


def get_discovery_service() -> DatabaseDiscoveryService:
    """Retorna instancia do servico (singleton)."""
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = DatabaseDiscoveryService()
    return _discovery_service
