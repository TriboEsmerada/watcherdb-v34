#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_live_gap_theming_smoke.py -- theming theme-aware V3.3 (2026-06-26).

Port do lote V6 (eabe9d1) para a Standard:
  (LIVE) container LIVE tinha background:#0a0e1a -> preto no tema Claro. Agora token.
  (gap cards) 4 cards de "Gaps Backup" com gradiente azul hardcoded -> classes
     .gap-card/.gap-pill com tints --sev-*-tint + border --sev-*-solid (nomes de token
     do V3.3: .fill->-solid, .bg->-tint).
  (P5) selects/inputs com background:#0b1220 -> token.

Check estrutural sobre a fonte (monolito), sem UI. <0.3s.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


class TestLiveBackgroundThemeAware(unittest.TestCase):
    def test_live_container_uses_token(self):
        self.assertIn("height:100%;background:var(--color-bg-primary)", PORTAL)

    def test_no_hardcoded_live_dark(self):
        self.assertNotIn("background:#0a0e1a", PORTAL)


class TestGapCardsTokenizedV33(unittest.TestCase):
    def test_gap_card_css_uses_v33_tokens(self):
        self.assertIn(".gap-card.crit { background: var(--sev-critical-tint); border-left-color: var(--sev-critical-solid); }", PORTAL)
        self.assertIn(".gap-card.warn { background: var(--sev-warning-tint)", PORTAL)
        self.assertIn(".gap-card.info { background: var(--sev-info-tint)", PORTAL)

    def test_gap_pills_v33_tokens(self):
        self.assertIn(".gap-pill.crit { background: var(--sev-critical-tint); color: var(--sev-critical-solid); }", PORTAL)

    def test_reduced_motion(self):
        self.assertIn("@media (prefers-reduced-motion: reduce) { .gap-card", PORTAL)

    def test_cards_use_classes(self):
        self.assertIn("gap-card ${fullCritical > 0 ? 'crit' : fullHigh > 0 ? 'warn' : 'info'}", PORTAL)
        self.assertIn("gap-card ${diffHigh > 0 ? 'warn' : 'info'}", PORTAL)

    def test_old_gradient_gone(self):
        self.assertNotIn("linear-gradient(135deg, ${fullCritical", PORTAL)


class TestBackupControlsTokenized(unittest.TestCase):
    def test_no_hardcoded_0b1220(self):
        self.assertEqual(PORTAL.count("background:#0b1220"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
