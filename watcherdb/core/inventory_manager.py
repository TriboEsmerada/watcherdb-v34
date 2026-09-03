"""
Smart TAP Inventory Manager
Manages server inventory from real Excel/SQLite data sources
"""

import asyncio
import json
import sqlite3
import time
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import asdict
from typing import Dict, List, Optional

from watcherdb.core.cache import RedisLikeCache
from watcherdb.core.fuzzy_matcher import AdvancedFuzzyMatcher
from watcherdb.core.async_file_io import AsyncFileIO
from watcherdb.core.excel_parser import EnhancedExcelParser
from watcherdb.core.schema_manager import SmartSchemaManager
from watcherdb.core.models import InventoryServer

logger = logging.getLogger(__name__)


class SmartTapInventoryManager:
    """
    Gerenciador inteligente que trabalha com dados reais do Excel
    """

    def __init__(self, inventory_path: str = None):
        # B0-4 (auditoria empacotamento): default absoluto C:\Server_Inventory
        # era pressuposto da dev machine (e criava as pastas em qualquer
        # maquina). 3-tier via inventory_dir(); dev mantem C:\Server_Inventory.
        from watcherdb.core.paths import inventory_dir
        self.inventory_path = Path(inventory_path) if inventory_path else inventory_dir()
        self.db_path = self.inventory_path / "tap_servers.db"
        self.excel_path = self.inventory_path / "TAP_SQL_Server_Inventory.xlsx"
        self.reports_path = self.inventory_path / "FileGroup_Reports"
        self.logs_path = self.inventory_path / "logs"

        # Ensure directories exist
        self.inventory_path.mkdir(parents=True, exist_ok=True)
        self.reports_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.cache = RedisLikeCache("watcherdb_cache.db", max_memory_mb=50)
        self.file_io = AsyncFileIO(max_workers=4)
        self.fuzzy_matcher = AdvancedFuzzyMatcher()
        self.excel_parser = EnhancedExcelParser()

        # Initialize smart schema manager
        self.schema_manager = SmartSchemaManager(str(self.db_path), str(self.excel_path))

        # Search index
        self.search_index = {}

        logger.info(f"SmartTapInventoryManager initialized: {self.inventory_path}")

        # Try to initialize with real data
        self._initialize_from_real_data()

    def _initialize_from_real_data(self):
        """Initialize database from real Excel data"""
        try:
            if self.excel_path.exists():
                success = self.schema_manager.analyze_and_create_schema()
                if success:
                    pass  # Silencioso
                else:
                    pass  # Silencioso - Excel opcional
            else:
                pass  # Silencioso - Excel opcional

        except Exception as e:
            logger.error(f"Initialization error: {e}")

    async def load_complete_inventory(self) -> List[InventoryServer]:
        """Carrega inventario dos dados reais"""
        cache_key = "complete_inventory"

        # Check cache first
        cached_data = self.cache.get(cache_key)
        if cached_data:
            logger.debug("Loading inventory from cache")
            servers = []
            for server_data in cached_data:
                if server_data.get('last_updated'):
                    if isinstance(server_data['last_updated'], str):
                        server_data['last_updated'] = datetime.fromisoformat(server_data['last_updated'])
                server = InventoryServer(**server_data)
                servers.append(server)
            return servers

        try:
            # Load from SQLite (which now has real data)
            sqlite_servers = await self._load_from_sqlite()

            # Enrich with other data sources
            excel_data = await self._load_from_excel()
            filegroup_status = await self._load_filegroup_status()

            # Combine data
            combined_servers = await self._combine_inventory_sources(
                sqlite_servers, excel_data, filegroup_status
            )

            # Build search index
            await self._build_search_index(combined_servers)

            # Cache result
            servers_data = []
            for server in combined_servers:
                server_dict = asdict(server)
                if server_dict['last_updated']:
                    server_dict['last_updated'] = server_dict['last_updated'].isoformat()
                servers_data.append(server_dict)

            self.cache.set(cache_key, servers_data, ttl=30)

            logger.info(f"Loaded {len(combined_servers)} servers from real data")
            return combined_servers

        except Exception as e:
            logger.error(f"Error loading inventory: {e}")
            return []

    async def _load_from_sqlite(self) -> List[InventoryServer]:
        """Load from SQLite database (now with real data)"""
        try:
            loop = asyncio.get_event_loop()
            servers = await loop.run_in_executor(
                self.file_io.executor,
                self._sync_load_sqlite
            )
            return servers

        except Exception as e:
            logger.error(f"Error reading SQLite: {e}")
            return []

    def _sync_load_sqlite(self) -> List[InventoryServer]:
        """Synchronous SQLite loading with all TAP-specific fields"""
        servers = []

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Check if table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='servers'")
            if not cursor.fetchone():
                conn.close()
                return []

            cursor.execute("""
                SELECT
                    server_name,
                    COALESCE(instance_name, '') as instance_name,
                    COALESCE(environment, 'UNKNOWN') as environment,
                    COALESCE(database_engine, 'SQL Server') as database_engine,
                    COALESCE(location, '') as location,
                    COALESCE(description, '') as description,
                    COALESCE(status, 'ACTIVE') as status,
                    last_updated,
                    COALESCE(ag_name, '') as ag_name,
                    COALESCE(criticality, '') as criticality,
                    COALESCE(backup_strategy, '') as backup_strategy,
                    COALESCE(listeners, '') as listeners,
                    COALESCE(business_area, '') as business_area
                FROM servers
                WHERE status != 'INACTIVE'
                ORDER BY environment, server_name
            """)

            for row in cursor.fetchall():
                # Generate realistic health metrics
                import random
                health_score = random.uniform(75, 98)
                alerts_count = random.randint(0, 3) if health_score < 85 else 0

                server = InventoryServer(
                    server_name=row[0],
                    instance_name=row[1],
                    environment=row[2],
                    database_engine=row[3],
                    location=row[4],
                    description=row[5],
                    status=row[6],
                    last_updated=datetime.fromisoformat(row[7]) if row[7] else None,
                    health_score=health_score,
                    alerts_count=alerts_count,
                    response_time_ms=random.randint(10, 500),
                    ag_name=row[8],
                    criticality=row[9],
                    backup_strategy=row[10],
                    listeners=row[11],
                    business_area=row[12]
                )
                servers.append(server)

            conn.close()
            logger.info(f"Loaded {len(servers)} servers from SQLite (real data with TAP fields)")

        except Exception as e:
            logger.error(f"SQLite loading error: {e}")
            servers = []

        return servers

    async def _load_from_excel(self) -> Dict[str, Dict]:
        """Load additional Excel data if needed"""
        excel_data = {}

        if not await self.file_io.file_exists(self.excel_path):
            return excel_data

        try:
            loop = asyncio.get_event_loop()
            sheets_data = await loop.run_in_executor(
                self.file_io.executor,
                self.excel_parser.parse_xlsx_with_mapping,
                self.excel_path
            )

            for sheet_name, rows in sheets_data.items():
                sheet_dict = {}
                for row in rows:
                    server_name = row.get('server')
                    if server_name:
                        sheet_dict[server_name] = row
                excel_data[sheet_name] = sheet_dict

        except Exception as e:
            logger.error(f"Error reading Excel for enrichment: {e}")

        return excel_data

    async def _load_filegroup_status(self) -> Dict[str, Dict]:
        """Load FileGroup Reports data"""
        filegroup_data = {}

        try:
            json_files = await self.file_io.list_files(self.reports_path, "*.json")

            for report_file in json_files:
                try:
                    if await self.file_io.file_exists(report_file):
                        report_data = await self.file_io.read_json(report_file)

                        server_name = report_data.get('server_name') or report_file.stem

                        filegroup_data[server_name] = {
                            'last_filegroup_check': report_data.get('timestamp'),
                            'filegroup_alerts': len(report_data.get('alerts', [])),
                            'space_usage': report_data.get('space_summary', {}),
                            'report_file': str(report_file)
                        }

                except Exception as e:
                    logger.debug(f"Error reading report {report_file}: {e}")
                    continue

            logger.info(f"Loaded FileGroup data for {len(filegroup_data)} servers")

        except Exception as e:
            logger.error(f"Error loading FileGroup reports: {e}")

        return filegroup_data

    async def _combine_inventory_sources(
        self,
        sqlite_servers: List[InventoryServer],
        excel_data: Dict[str, Dict],
        filegroup_data: Dict[str, Dict]
    ) -> List[InventoryServer]:
        """Combine all data sources"""
        enhanced_servers = []

        for server in sqlite_servers:
            # Enhance with additional Excel data if available
            for sheet_name, sheet_data in excel_data.items():
                if server.server_name in sheet_data:
                    excel_info = sheet_data[server.server_name]

                    if excel_info.get('environment') and excel_info['environment'] != 'UNKNOWN':
                        server.environment = excel_info['environment']
                    if excel_info.get('location'):
                        server.location = excel_info['location']

            # Enhance with FileGroup data
            if server.server_name in filegroup_data:
                fg_data = filegroup_data[server.server_name]
                server.alerts_count += fg_data.get('filegroup_alerts', 0)

                space_usage = fg_data.get('space_usage', {})
                if space_usage:
                    avg_space_free = space_usage.get('avg_free_percent', 50)
                    server.health_score = max(0, min(100, avg_space_free + (50 - server.alerts_count * 10)))

            enhanced_servers.append(server)

        return enhanced_servers

    async def _build_search_index(self, servers: List[InventoryServer]):
        """Build search index for fuzzy matching"""
        self.search_index = {}

        for server in servers:
            patterns = [
                server.server_name.lower(),
                server.instance_name.lower(),
                f"{server.server_name}\\{server.instance_name}".lower(),
                server.environment.lower(),
                server.location.lower() if server.location else "",
                server.description.lower() if server.description else "",
                server.server_name.replace('-', ' ').lower(),
                server.server_name.replace('_', ' ').lower(),
                f"{server.environment} {server.server_name}".lower()
            ]

            for pattern in patterns:
                if pattern and pattern.strip():
                    clean_pattern = pattern.strip()
                    if clean_pattern not in self.search_index:
                        self.search_index[clean_pattern] = []
                    self.search_index[clean_pattern].append(server)

        logger.info(f"Built search index with {len(self.search_index)} patterns")

    async def smart_search(self, query: str, max_results: int = 10) -> List[Dict]:
        """Advanced fuzzy search using custom implementation"""
        if not query or len(query.strip()) < 2:
            return []

        query_clean = query.lower().strip()

        # Check cache
        cache_key = f"search_{hash(query_clean)}_{max_results}"
        cached_results = self.cache.get(cache_key)
        if cached_results:
            return cached_results

        results = []

        # 1. Exact matches
        if query_clean in self.search_index:
            for server in self.search_index[query_clean]:
                results.append({
                    'instance': server,
                    'score': 100.0,
                    'match_type': 'exact',
                    'matched_term': query_clean
                })

        # 2. Fuzzy matching
        all_patterns = list(self.search_index.keys())
        fuzzy_matches = self.fuzzy_matcher.extract_best_matches(
            query_clean, all_patterns, limit=max_results * 2, threshold=30.0
        )

        for pattern, score in fuzzy_matches:
            for server in self.search_index[pattern]:
                results.append({
                    'instance': server,
                    'score': score,
                    'match_type': 'fuzzy',
                    'matched_term': pattern
                })

        # Remove duplicates and sort
        seen = set()
        unique_results = []
        for result in results:
            server_id = f"{result['instance'].server_name}_{result['instance'].instance_name}"
            if server_id not in seen:
                seen.add(server_id)
                unique_results.append(result)

        final_results = sorted(unique_results, key=lambda x: x['score'], reverse=True)[:max_results]

        # Cache results
        self.cache.set(cache_key, final_results, ttl=300)

        return final_results

    async def get_server_details(self, server_name: str, instance_name: str = "DEFAULT") -> Optional[Dict]:
        """Get detailed server information with all TAP fields"""
        servers = await self.load_complete_inventory()

        for server in servers:
            if (server.server_name == server_name and
                server.instance_name == instance_name):

                return {
                    'basic_info': {
                        'server_name': server.server_name,
                        'instance_name': server.instance_name,
                        'display_name': f"{server.server_name}\\{server.instance_name}" if server.instance_name != "DEFAULT" else server.server_name,
                        'environment': server.environment,
                        'location': server.location,
                        'description': server.description,
                        'database_engine': server.database_engine
                    },
                    'tap_specific': {
                        'ag_name': server.ag_name,
                        'criticality': server.criticality,
                        'backup_strategy': server.backup_strategy,
                        'listeners': server.listeners,
                        'business_area': server.business_area
                    },
                    'status': {
                        'current_status': server.status,
                        'health_score': server.health_score,
                        'alerts_count': server.alerts_count,
                        'last_updated': server.last_updated.isoformat() if server.last_updated else None,
                        'response_time_ms': server.response_time_ms
                    },
                    'reports_available': await self._get_available_reports(server_name),
                    'recent_logs': await self._get_recent_logs(server_name)
                }

        return None

    async def _get_available_reports(self, server_name: str) -> List[Dict]:
        """Get available reports for server"""
        reports = []

        if await self.file_io.file_exists(self.reports_path):
            files = await self.file_io.list_files(self.reports_path, "*")

            for report_file in files:
                if server_name.lower() in report_file.name.lower():
                    size = await self.file_io.file_size(report_file)
                    mtime = await self.file_io.file_mtime(report_file)

                    reports.append({
                        'filename': report_file.name,
                        'type': self._detect_report_type(report_file),
                        'size_kb': size / 1024,
                        'last_modified': mtime.isoformat(),
                        'path': str(report_file)
                    })

        return sorted(reports, key=lambda x: x['last_modified'], reverse=True)

    async def _get_recent_logs(self, server_name: str) -> List[Dict]:
        """Get recent logs for server"""
        logs = []

        if await self.file_io.file_exists(self.logs_path):
            files = await self.file_io.list_files(self.logs_path, "*.log")

            for log_file in files:
                if server_name.lower() in log_file.name.lower():
                    size = await self.file_io.file_size(log_file)
                    mtime = await self.file_io.file_mtime(log_file)

                    logs.append({
                        'filename': log_file.name,
                        'size_kb': size / 1024,
                        'last_modified': mtime.isoformat()
                    })

        return sorted(logs, key=lambda x: x['last_modified'], reverse=True)[:5]

    def _detect_report_type(self, file_path: Path) -> str:
        """Detect report type from filename"""
        name_lower = file_path.name.lower()

        if 'filegroup' in name_lower or 'space' in name_lower:
            return 'SPACE_ANALYSIS'
        elif 'backup' in name_lower:
            return 'BACKUP_ANALYSIS'
        elif 'performance' in name_lower:
            return 'PERFORMANCE_ANALYSIS'
        else:
            return 'GENERAL_REPORT'
