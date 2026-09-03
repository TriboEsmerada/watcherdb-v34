"""
Smart Schema Manager
Creates database schema based on real Excel data
"""

import json
import sqlite3
import logging
from datetime import datetime
from typing import Dict, List

from watcherdb.core.excel_parser import EnhancedExcelParser

logger = logging.getLogger(__name__)


class SmartSchemaManager:
    """
    Gerenciador inteligente que cria o schema baseado nos dados reais do Excel
    """

    def __init__(self, db_path: str, excel_path: str):
        self.db_path = db_path
        self.excel_path = excel_path
        self.excel_parser = EnhancedExcelParser()

    def analyze_and_create_schema(self) -> bool:
        """Analisa o Excel e cria o schema correto"""
        try:
            # Silencioso - dados vem do JSON, Excel e opcional
            analysis = self.excel_parser.analyze_excel_structure(self.excel_path)

            if analysis['row_count'] == 0:
                # Excel vazio - silencioso, dados vem do SQLite/JSON
                return False

            # Step 2: Parse Excel with intelligent mapping
            excel_data = self.excel_parser.parse_xlsx_with_mapping(self.excel_path)

            if not excel_data:
                # Silencioso
                return False

            # Step 3: Create database schema
            self._create_database_schema()

            # Step 4: Import real data
            total_imported = 0
            for sheet_name, sheet_data in excel_data.items():
                imported = self._import_sheet_data(sheet_name, sheet_data)
                total_imported += imported
            # Silencioso
            return total_imported > 0

        except Exception as e:
            logger.error(f"Schema creation error: {e}")
            return False

    def _create_database_schema(self):
        """Create the correct database schema with TAP-specific fields"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Drop existing table if it exists
        cursor.execute("DROP TABLE IF EXISTS servers")

        # Create new table with all TAP-specific columns
        cursor.execute('''
            CREATE TABLE servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_name TEXT NOT NULL,
                instance_name TEXT DEFAULT 'DEFAULT',
                environment TEXT DEFAULT 'UNKNOWN',
                database_engine TEXT DEFAULT 'SQL Server',
                location TEXT DEFAULT '',
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'ACTIVE',
                last_updated TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                -- TAP-specific columns
                ag_name TEXT DEFAULT '',
                criticality TEXT DEFAULT '',
                backup_strategy TEXT DEFAULT '',
                listeners TEXT DEFAULT '',
                business_area TEXT DEFAULT '',
                -- Store all original Excel data as JSON for full data access
                original_data TEXT,
                sheet_source TEXT
            )
        ''')

        # Create indexes for faster searches
        cursor.execute("CREATE INDEX idx_server_name ON servers(server_name)")
        cursor.execute("CREATE INDEX idx_environment ON servers(environment)")
        cursor.execute("CREATE INDEX idx_ag_name ON servers(ag_name)")
        cursor.execute("CREATE INDEX idx_criticality ON servers(criticality)")

        conn.commit()
        conn.close()

        logger.info("Database schema created successfully with TAP-specific fields")

    def _import_sheet_data(self, sheet_name: str, sheet_data: List[Dict[str, str]]) -> int:
        """Import data from a sheet with all TAP fields"""
        if not sheet_data:
            return 0

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        imported_count = 0
        current_time = datetime.now().isoformat()

        for row_data in sheet_data:
            try:
                # Extract standard fields
                server_name = row_data.get('server', '').strip()
                if not server_name:
                    continue  # Skip rows without server name

                instance_name = (row_data.get('instance') or '').strip() or ''
                environment = row_data.get('environment', 'UNKNOWN').strip() or 'UNKNOWN'
                database_engine = row_data.get('database_engine', 'SQL Server').strip() or 'SQL Server'
                location = row_data.get('location', '').strip()
                description = row_data.get('description', '').strip()
                status = row_data.get('status', 'ACTIVE').strip() or 'ACTIVE'

                # Extract TAP-specific fields
                ag_name = row_data.get('ag_name', '').strip()
                criticality = row_data.get('criticality', '').strip()
                backup_strategy = row_data.get('backup_strategy', '').strip()
                listeners = row_data.get('listeners', '').strip()
                business_area = row_data.get('business_area', '').strip()

                # Use business_area as location if location is empty
                if not location and business_area:
                    location = business_area

                # Store original data as JSON for full data access
                original_data = json.dumps(row_data, ensure_ascii=False)

                cursor.execute('''
                    INSERT INTO servers
                    (server_name, instance_name, environment, database_engine,
                     location, description, status, last_updated,
                     ag_name, criticality, backup_strategy, listeners, business_area,
                     original_data, sheet_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    server_name, instance_name, environment, database_engine,
                    location, description, status, current_time,
                    ag_name, criticality, backup_strategy, listeners, business_area,
                    original_data, sheet_name
                ))

                imported_count += 1

                if imported_count <= 3:  # Log first few imports
                    logger.info(f"Imported: {server_name}\\{instance_name} - Env:{environment} - AG:{ag_name} - Crit:{criticality}")

            except Exception as e:
                logger.error(f"Error importing row {row_data.get('server', 'UNKNOWN')}: {e}")
                continue

        conn.commit()
        conn.close()

        return imported_count
