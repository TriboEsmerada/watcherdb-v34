#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_backup_diff_card_smoke.py -- card "Gaps DIFF Backup" coerente (2026-06-26).

Bug (reportado pelo owner): o card mostrava o numero `diffReal.length` (ex.: 5) mas o
subtitulo so verificava `diffHigh > 0`; com 5 gaps que nao sao severidade HIGH, mostrava
"Sem gaps significativos" -- contradizendo o 5.

Fix: "Sem gaps significativos" SO quando diffReal.length === 0; senao "{diffHigh} Alto"
(se houver HIGH) ou um chip neutro "{n} gap(s)".

Check estrutural sobre a fonte (portal), sem UI. <0.3s.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


class TestDiffGapCardConsistent(unittest.TestCase):
    def test_no_significant_gaps_gated_by_count(self):
        # "Sem gaps significativos" do card DIFF tem de estar atras de diffReal.length === 0
        self.assertIn("diffReal.length === 0 ?", PORTAL)

    def test_neutral_chip_when_gaps_without_high(self):
        # com gaps mas sem HIGH -> chip neutro com a contagem (nao contradiz o numero)
        self.assertIn("${diffReal.length} gap(s)", PORTAL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
