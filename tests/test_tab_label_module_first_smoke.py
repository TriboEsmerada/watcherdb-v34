#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_tab_label_module_first_smoke.py -- label de tab com modulo primeiro (2026-06-26).

Bug (reportado pelo owner como "tabs duplicadas"): NAO era dedup (createTab ja deduplica
por servidor+tabType). A label era "${serverName} - ${label}" -> com o nome longo do
servidor a frente, varias tabs do MESMO servidor (Overview/Backup/...) truncavam todas
para "SERVIDOR ..." e ficavam indistinguiveis (pareciam duplicadas).

Fix: modulo primeiro -> "Backup · SQLHDSPRD403\\I01" (o modulo sobrevive a truncagem).

Check estrutural sobre a fonte, sem UI. <0.3s.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


class TestTabLabelModuleFirst(unittest.TestCase):
    def test_module_first_format(self):
        self.assertIn("${label} · ${serverName}", PORTAL)

    def test_old_server_first_gone(self):
        self.assertNotIn("${serverName} - ${label}", PORTAL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
