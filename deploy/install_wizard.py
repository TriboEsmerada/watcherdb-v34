#!/usr/bin/env python3
"""
[DEPRECATED] WatcherDB V3.2 Installation Wizard — audit 2026-04-22 / S2-8

Este script foi deprecado em Sprint 2. Valores V3.2 + porta 8449 +
servico WatcherDBWebServiceV32 desalinhados com produto actual V3.3.
O MSI e o artefacto canonico.

CAMINHO CANONICO DE INSTALACAO:
    dist\\msi\\WatcherDB_V3.3_Standard.msi
    Guia: docs\\external\\standard\\INSTALL_GUIDE.md
"""
import sys

BANNER = """
[DEPRECATED] install_wizard.py foi deprecado em audit 2026-04-22 (S2-8).

Instalacao canonica actual:
  msiexec /i dist\\msi\\WatcherDB_V3.3_Standard.msi /qn /l*v install.log

Guia completo:
  docs\\external\\standard\\INSTALL_GUIDE.md
"""

print(BANNER, file=sys.stderr)
sys.exit(1)
