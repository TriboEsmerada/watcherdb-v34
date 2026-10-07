"""
farm_inventory_parser.py — SQL Server farm inventory → servers.json canonical.

Sprint install flow v0.2 B7 (FIND-20260424-001). Desde 2026-10-07 (lote B do instalador) a implementacao vive em
watcherdb/install/inventory.py, para viajar no watcherdb.exe (`watcherdb.exe inventory`); este ficheiro e' um shim
que mantem a API e a linha de comandos antigas para uso no repo:

    python deploy/farm_inventory_parser.py --input farm.csv --master-host SQLMASTER --master-username sql_monitoring --output servers.json

Aceita .csv, .json (array ou servers.json canonico) e, agora, .xlsx (modelo: `watcherdb.exe inventory-template`).
Passwords nunca no inventario: placeholder @ENCRYPT_AT_INSTALL@.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Repo root no sys.path para `python deploy/farm_inventory_parser.py` directo (os testes ja' o tem).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from watcherdb.install.inventory import (  # noqa: E402,F401 - re-export da API antiga
    PASSWORD_PLACEHOLDER, REQUIRED_COLUMNS, DEFAULT_COLUMNS,
    ServerEntry, ParseIssue, ParseResult,
    _str_to_bool, _sanitize_hostname, _build_id, _parse_row, _validate_tcp,
    parse_csv, parse_json, parse_xlsx, parse_servers_json, ler_inventario,
    build_master_server, write_servers_json, gerar_rollout, write_rollout_json,
    escrever_scripts_grants, gerar_modelo_xlsx, main,
)

if __name__ == "__main__":
    sys.exit(main())
