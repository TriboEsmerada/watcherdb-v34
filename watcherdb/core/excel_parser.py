"""
Enhanced Excel Parser
Intelligent XLSX parsing with content-based column mapping
"""

import re
import csv
import zipfile
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

logger = logging.getLogger(__name__)


class EnhancedExcelParser:
    """
    Parser inteligente de Excel com mapeamento de colunas baseado em conteudo.
    Suporta XLSX (via zipfile) e fallback para CSV.
    """

    def __init__(self):
        pass

    # ===== Instance-level helpers used by SmartTapInventoryManager =====
    def analyze_excel_structure(self, filepath: str) -> Dict[str, Any]:
        """Retorna estrutura minima detectada do Excel."""
        try:
            return {
                'file': filepath,
                'sheets': {},
                'columns_found': [],
                'columns': [],
                'detected_mapping': {},
                'row_count': 0,
                'sheet_count': 0,
                'column_count': 0
            }
        except Exception:
            return {'file': filepath, 'sheets': {}, 'columns_found': [], 'columns': [], 'detected_mapping': {}, 'row_count': 0, 'sheet_count': 0, 'column_count': 0}

    @staticmethod
    def summarize_structure(structure: Dict[str, Any]) -> Dict[str, Any]:
        """Gera um resumo compativel com chaves esperadas (ex.: row_count)."""
        sheets = structure.get('sheets') or []
        columns = structure.get('columns') or []
        return {
            'row_count': 0,
            'sheet_count': len(sheets),
            'column_count': len(columns)
        }

    # ===== Main parsing entry point =====
    def parse_xlsx_with_mapping(self, filepath: Union[str, Path], column_mapping: Optional[Dict[str, List[str]]] = None) -> Dict[str, List[Dict[str, str]]]:
        """Parse XLSX with INTELLIGENT content-based mapping"""
        return EnhancedExcelParser._static_parse_xlsx_with_mapping(filepath, column_mapping)

    @staticmethod
    def _static_parse_xlsx_with_mapping(filepath: Union[str, Path], column_mapping: Dict[str, List[str]] = None) -> Dict[str, List[Dict[str, str]]]:
        """Parse XLSX with INTELLIGENT content-based mapping"""
        sheets_data = {}

        # Standard column mapping by NAME
        if column_mapping is None:
            column_mapping = {
                'server': [
                    'serverinstance', 'server_instance',
                    'server_name', 'server', 'hostname', 'host', 'machine', 'computer_name',
                    'servername', 'server-name', 'ag_name'
                ],
                'instance': [
                    'instance_name', 'instance', 'service_name', 'sql_instance', 'inst'
                ],
                'environment': ['environment', 'env', 'tier', 'stage', 'ambiente', 'listeners'],
                'location': ['location', 'datacenter', 'site', 'region', 'local'],
                'description': ['description', 'desc', 'comments', 'notes', 'business_area'],
                'status': ['status', 'state', 'active', 'criticality'],
                'ag_name': ['ag_name', 'availability_group', 'ag', 'cluster'],
                'backup_strategy': ['backup_strategy', 'backup', 'strategy'],
                'listeners': ['listeners', 'listener', 'endpoints'],
                'criticality': ['criticality', 'critical', 'priority', 'environment']
            }

        try:
            with zipfile.ZipFile(filepath, 'r') as zip_file:
                shared_strings = EnhancedExcelParser._read_shared_strings(zip_file)
                sheets_info = EnhancedExcelParser._read_workbook(zip_file)

                for sheet_name, sheet_id in sheets_info.items():
                    sheet_data = EnhancedExcelParser._read_sheet(
                        zip_file, sheet_id, shared_strings
                    )

                    if sheet_data and len(sheet_data) > 0:
                        structured_data = EnhancedExcelParser._intelligent_map_sheet_data(
                            sheet_data, column_mapping
                        )
                        if structured_data:
                            sheets_data[sheet_name] = structured_data

        except Exception as e:
            logger.error(f"Excel parsing error: {e}")
            try:
                sheets_data = {'Sheet1': EnhancedExcelParser._read_as_csv_structured(filepath, column_mapping)}
            except Exception:
                sheets_data = {}

        return sheets_data

    @staticmethod
    def _intelligent_map_sheet_data(sheet_data: List[List[str]], column_mapping: Dict[str, List[str]]) -> List[Dict[str, str]]:
        """INTELLIGENT mapping based on CONTENT analysis, not just column names"""
        if not sheet_data or len(sheet_data) < 2:
            logger.warning("No sheet data or insufficient rows")
            return []

        headers = [str(cell).strip().lower() for cell in sheet_data[0]]
        logger.info(f"Processing headers: {headers}")

        sample_rows = sheet_data[1:min(6, len(sheet_data))]
        column_patterns = EnhancedExcelParser._analyze_column_patterns(headers, sample_rows)

        logger.info(f"Detected patterns: {column_patterns}")

        header_to_standard = {}

        for idx, header in enumerate(headers):
            pattern = column_patterns.get(idx, {})

            if pattern.get('has_backslash'):
                header_to_standard[header] = 'server'
                logger.info(f"INTELLIGENT: '{header}' -> 'server' (detected server\\instance pattern)")
            elif pattern.get('looks_like_environment'):
                header_to_standard[header] = 'environment'
                logger.info(f"INTELLIGENT: '{header}' -> 'environment' (detected environment values)")
            elif pattern.get('looks_like_criticality'):
                header_to_standard[header] = 'criticality'
                logger.info(f"INTELLIGENT: '{header}' -> 'criticality' (detected criticality values)")
            else:
                for standard_col, possible_headers in column_mapping.items():
                    header_clean = header.lower().strip()
                    for possible_header in possible_headers:
                        if (header_clean == possible_header.lower() or
                            possible_header.lower() in header_clean):
                            if header not in header_to_standard:
                                header_to_standard[header] = standard_col
                                logger.info(f"NAME-BASED: '{header}' -> '{standard_col}'")
                            break
                    if header in header_to_standard:
                        break

        logger.info(f"Final intelligent mapping: {header_to_standard}")

        structured_data = []
        for row_idx, row in enumerate(sheet_data[1:], 1):
            if not row or not any(str(cell).strip() for cell in row):
                continue

            row_dict = {}
            for i, cell in enumerate(row):
                if i < len(headers):
                    original_header = headers[i]
                    standard_col = header_to_standard.get(original_header)
                    cell_value = str(cell).strip() if cell else ''

                    if standard_col:
                        row_dict[standard_col] = cell_value
                    row_dict[f"col_{original_header}"] = cell_value

            server_value = row_dict.get('server', '').strip()
            if server_value:
                if '\\' in server_value:
                    parts = server_value.split('\\')
                    row_dict['server'] = parts[0].strip()
                    row_dict['instance'] = parts[1].strip() if len(parts) > 1 else 'DEFAULT'
                else:
                    if not row_dict.get('instance'):
                        row_dict['instance'] = 'DEFAULT'

                if not row_dict.get('environment') or row_dict.get('environment') == '':
                    row_dict['environment'] = 'UNKNOWN'

                if not row_dict.get('status'):
                    row_dict['status'] = row_dict.get('criticality', 'ACTIVE')

                if not row_dict.get('database_engine'):
                    if any(term in server_value.upper() for term in ['SSAS', 'ANALYSIS', 'MSAS']):
                        row_dict['database_engine'] = 'SSAS'
                    else:
                        row_dict['database_engine'] = 'SQL Server'

                if not row_dict.get('location') and row_dict.get('business_area'):
                    row_dict['location'] = row_dict.get('business_area')

                structured_data.append(row_dict)

                if row_idx <= 3:
                    logger.info(f"Row {row_idx} intelligently mapped: server={row_dict.get('server')}, "
                              f"instance={row_dict.get('instance')}, "
                              f"environment={row_dict.get('environment')}, "
                              f"criticality={row_dict.get('criticality')}, "
                              f"engine={row_dict.get('database_engine')}")

        logger.info(f"Successfully mapped {len(structured_data)} rows with intelligent detection")
        return structured_data

    @staticmethod
    def _analyze_column_patterns(headers: List[str], sample_rows: List[List[str]]) -> Dict[int, Dict[str, bool]]:
        """Analyze sample data to detect column patterns"""
        patterns = {}

        for col_idx in range(len(headers)):
            col_values = []
            for row in sample_rows:
                if col_idx < len(row) and row[col_idx]:
                    col_values.append(str(row[col_idx]).strip())

            if not col_values:
                continue

            pattern = {
                'has_backslash': False,
                'looks_like_environment': False,
                'looks_like_criticality': False
            }

            backslash_count = sum(1 for v in col_values if '\\' in v)
            if backslash_count >= len(col_values) * 0.5:
                pattern['has_backslash'] = True

            env_keywords = ['PRODUCTION', 'PRD', 'PROD', 'QUALITY', 'QA', 'TEST', 'DEV', 'DEVELOPMENT', 'STAGING', 'STG']
            env_count = sum(1 for v in col_values if any(kw in v.upper() for kw in env_keywords))
            if env_count >= len(col_values) * 0.5:
                pattern['looks_like_environment'] = True

            crit_keywords = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NORMAL']
            crit_count = sum(1 for v in col_values if any(kw in v.upper() for kw in crit_keywords))
            if crit_count >= len(col_values) * 0.5:
                pattern['looks_like_criticality'] = True

            patterns[col_idx] = pattern

        return patterns

    @staticmethod
    def _map_sheet_data(sheet_data: List[List[str]], column_mapping: Dict[str, List[str]]) -> List[Dict[str, str]]:
        """Map sheet data to structured format with enhanced logging"""
        if not sheet_data or len(sheet_data) < 2:
            logger.warning("No sheet data or insufficient rows")
            return []

        headers = [str(cell).strip().lower() for cell in sheet_data[0]]
        logger.info(f"Processing headers: {headers}")

        header_to_standard = {}
        for standard_col, possible_headers in column_mapping.items():
            for header in headers:
                header_clean = header.lower().strip()
                for possible_header in possible_headers:
                    if (header_clean == possible_header.lower() or
                        possible_header.lower() in header_clean or
                        header_clean in possible_header.lower()):
                        header_to_standard[header] = standard_col
                        logger.info(f"Mapped '{header}' -> '{standard_col}' (matched with '{possible_header}')")
                        break
                if header in header_to_standard:
                    break

        logger.info(f"Final column mapping: {header_to_standard}")

        server_mapped = any(std_col == 'server' for std_col in header_to_standard.values())
        if not server_mapped:
            logger.error("No server column mapped! Available headers: " + str(headers))
            logger.error("Trying emergency mapping...")

            for header in headers:
                if any(term in header.lower() for term in ['server', 'host', 'machine', 'instance']):
                    header_to_standard[header] = 'server'
                    logger.warning(f"Emergency mapping: '{header}' -> 'server'")
                    server_mapped = True
                    break

        if not server_mapped:
            logger.error("Still no server column found. Cannot proceed.")
            return []

        structured_data = []
        for row_idx, row in enumerate(sheet_data[1:], 1):
            if not row or not any(str(cell).strip() for cell in row):
                continue

            row_dict = {}
            for i, cell in enumerate(row):
                if i < len(headers):
                    original_header = headers[i]
                    standard_col = header_to_standard.get(original_header)
                    cell_value = str(cell).strip() if cell else ''

                    if standard_col:
                        row_dict[standard_col] = cell_value
                    row_dict[f"col_{original_header}"] = cell_value

            server_value = row_dict.get('server', '').strip()
            if server_value:
                if not row_dict.get('instance'):
                    if '\\' in server_value:
                        parts = server_value.split('\\')
                        row_dict['server'] = parts[0].strip()
                        row_dict['instance'] = parts[1].strip()
                    else:
                        row_dict['instance'] = ''

                if not row_dict.get('environment') or row_dict.get('environment') == '':
                    row_dict['environment'] = 'UNKNOWN'

                if not row_dict.get('status'):
                    if row_dict.get('criticality'):
                        row_dict['status'] = row_dict.get('criticality')
                    else:
                        row_dict['status'] = 'ACTIVE'

                if not row_dict.get('database_engine'):
                    row_dict['database_engine'] = 'SQL Server'

                if not row_dict.get('location') and row_dict.get('business_area'):
                    row_dict['location'] = row_dict.get('business_area')

                structured_data.append(row_dict)

                if row_idx <= 3:
                    logger.info(f"Row {row_idx} mapped to: server={row_dict.get('server')}, "
                              f"instance={row_dict.get('instance')}, "
                              f"environment={row_dict.get('environment')}, "
                              f"ag_name={row_dict.get('ag_name')}, "
                              f"criticality={row_dict.get('criticality')}, "
                              f"business_area={row_dict.get('business_area')}")
            else:
                logger.debug(f"Row {row_idx} skipped - no server identifier")

        logger.info(f"Successfully mapped {len(structured_data)} rows from {len(sheet_data)-1} total rows")
        return structured_data

    @staticmethod
    def _read_shared_strings(zip_file) -> List[str]:
        """Read shared strings table"""
        try:
            with zip_file.open('xl/sharedStrings.xml') as f:
                content = f.read().decode('utf-8')

            strings = []
            pattern = r'<t[^>]*>(.*?)</t>'
            matches = re.findall(pattern, content, re.DOTALL)

            for match in matches:
                text = match.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
                strings.append(text)

            return strings

        except Exception:
            return []

    @staticmethod
    def _read_workbook(zip_file) -> Dict[str, str]:
        """Read workbook.xml to get sheet information"""
        try:
            with zip_file.open('xl/workbook.xml') as f:
                content = f.read().decode('utf-8')

            sheets = {}
            pattern = r'<sheet[^>]*name="([^"]*)"[^>]*sheetId="([^"]*)"'
            matches = re.findall(pattern, content)

            for name, sheet_id in matches:
                sheets[name] = sheet_id

            return sheets

        except Exception:
            return {'Sheet1': '1'}

    @staticmethod
    def _read_sheet(zip_file, sheet_id: str, shared_strings: List[str]) -> List[List[str]]:
        """Read individual sheet data"""
        try:
            sheet_path = f'xl/worksheets/sheet{sheet_id}.xml'
            with zip_file.open(sheet_path) as f:
                content = f.read().decode('utf-8')

            rows_data = []

            row_pattern = r'<row[^>]*>(.*?)</row>'
            row_matches = re.findall(row_pattern, content, re.DOTALL)

            for row_content in row_matches:
                row_cells = []

                cell_pattern = r'<c[^>]*r="([^"]*)"[^>]*t="([^"]*)"[^>]*>(.*?)</c>'
                cell_matches = re.findall(cell_pattern, row_content, re.DOTALL)

                cell_pattern2 = r'<c[^>]*r="([^"]*)"[^>]*>(.*?)</c>'
                cell_matches2 = re.findall(cell_pattern2, row_content, re.DOTALL)

                for cell_ref, cell_type, cell_content in cell_matches:
                    value = EnhancedExcelParser._extract_cell_value(
                        cell_content, cell_type, shared_strings
                    )
                    row_cells.append((cell_ref, value))

                for cell_ref, cell_content in cell_matches2:
                    if not any(cell_ref == ref for ref, _, _ in cell_matches):
                        value = EnhancedExcelParser._extract_cell_value(
                            cell_content, '', shared_strings
                        )
                        row_cells.append((cell_ref, value))

                row_cells.sort(key=lambda x: x[0])
                row_values = [cell[1] for cell in row_cells]

                if row_values:
                    rows_data.append(row_values)

            return rows_data

        except Exception as e:
            logger.error(f"Sheet reading error: {e}")
            return []

    @staticmethod
    def _extract_cell_value(cell_content: str, cell_type: str, shared_strings: List[str]) -> str:
        """Extract value from cell content"""
        try:
            value_pattern = r'<v[^>]*>(.*?)</v>'
            value_match = re.search(value_pattern, cell_content)

            if not value_match:
                return ''

            value = value_match.group(1)

            if cell_type == 's' and value.isdigit():
                string_index = int(value)
                if 0 <= string_index < len(shared_strings):
                    return shared_strings[string_index]

            return value

        except Exception:
            return ''

    @staticmethod
    def _read_as_csv_structured(filepath: Union[str, Path], column_mapping: Dict[str, List[str]]) -> List[Dict[str, str]]:
        """Fallback: try to read as CSV with structure"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                raw_data = [row for row in reader]

            if raw_data:
                return EnhancedExcelParser._map_sheet_data(raw_data, column_mapping)

        except Exception:
            for encoding in ['latin1', 'cp1252', 'iso-8859-1']:
                try:
                    with open(filepath, 'r', encoding=encoding) as f:
                        reader = csv.reader(f)
                        raw_data = [row for row in reader]

                    if raw_data:
                        return EnhancedExcelParser._map_sheet_data(raw_data, column_mapping)
                    break
                except Exception:
                    continue

        return []
