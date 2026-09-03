#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_predictive_disk_real_or_abstain_smoke.py -- disco real OU ABSTAIN (2026-07-01).

Bug: `disk_available_gb = 100.0  # TODO` estava hardcoded em _aggregate_by_filegroup.
Consequencia: o alerta DISK_SATURATION corria sobre um valor inventado -> nunca disparava
(100.0 nunca e < 50) e, se disparasse, reportava "100.0GB livres" fabricados ao DBA.

Fix: espaco livre real por drive via sys.dm_os_volume_stats (query SEPARADA, try/except
proprio -> se faltar VIEW SERVER STATE, disco fica 'desconhecido' = ABSTAIN honesto, o
resto dos alertas continua a funcionar). Nunca fabricar (licao cross_instance do council).

Checks: (1) anchors de fonte + no-regression do hardcode; (2) comportamento ABSTAIN vs real
em _aggregate_by_filegroup (sync, sem DB). <0.5s.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SRC_PATH = ROOT / "modules" / "monitoring" / "predictive_alerts.py"
SRC = SRC_PATH.read_text(encoding="utf-8")

from modules.monitoring.predictive_alerts import PredictiveAlertsEngine, FileGroupAnalysis


def _fake_datafile(volume="C"):
    return {
        "database_name": "TESTDB",
        "filegroup_name": "DATA",
        "size_mb": 1000.0,
        "used_mb": 500.0,
        "max_size_mb": 2000.0,
        "max_size_formatted": "2000 MB",
        "volume": volume,
        "server_id": "SRV1",
    }


class TestPredictiveDiskSource(unittest.TestCase):
    def test_hardcode_gone(self):
        self.assertNotIn("disk_available_gb = 100.0", SRC)

    def test_real_source_present(self):
        self.assertIn("sys.dm_os_volume_stats", SRC)
        self.assertIn("_get_volume_free_gb", SRC)
        self.assertIn("disk_available_known", SRC)


class TestPredictiveDiskBehaviour(unittest.TestCase):
    def setUp(self):
        # _aggregate_by_filegroup e sincrono e nao toca a DB -> sql_monitoring nao e usado.
        self.engine = PredictiveAlertsEngine(sql_monitoring=None)

    def test_abstain_when_no_volume_data(self):
        fgs = self.engine._aggregate_by_filegroup([_fake_datafile()], volume_free={})
        fg = next(iter(fgs.values()))
        self.assertFalse(fg.disk_available_known, "sem dado de volume -> known=False (ABSTAIN)")
        self.assertEqual(fg.disk_available_gb, 0.0, "nao fabricar 100.0 nem outro valor")
        self.assertNotEqual(fg.risk_type, "DISK", "sem dado real nao afirmar risco DISK")

    def test_real_value_when_volume_data(self):
        fgs = self.engine._aggregate_by_filegroup([_fake_datafile("C")], volume_free={"C": 30.0})
        fg = next(iter(fgs.values()))
        self.assertTrue(fg.disk_available_known, "com dado de volume -> known=True")
        self.assertEqual(fg.disk_available_gb, 30.0, "usar o valor real do drive")

    def test_default_known_true_backward_compat(self):
        # Campo novo tem default True -> construcao existente noutro sitio nao regride.
        self.assertTrue(FileGroupAnalysis.__dataclass_fields__["disk_available_known"].default)


if __name__ == "__main__":
    unittest.main(verbosity=2)
