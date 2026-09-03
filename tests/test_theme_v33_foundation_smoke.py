#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_theme_v33_foundation_smoke.py -- Propagacao theme switcher V6 -> V3.3 (2026-06-24)

Recipe (propagado do V6): cor de severidade lê getSevTokens() (helper unico),
nao hardcoda hex. Adaptado a escala de tokens V3.3 (-solid/-tint/-text, NAO fill/bg).

  F1 fundacao: getSevTokens() + _ADVC tokenizado.
  F2 anti-FOUC + High-Contrast (3o tema + botao).
  F3 token --sev-attention (dark no design-system.css + light no monolito) + utility classes .sev-*.
  F4 tokenizacao das ladders (batch 1: sevColor de severidade-string).

Checks estruturais sobre a fonte, sem UI. <0.3s. Padrão Fable 5.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")
DS = (ROOT / "static" / "css" / "watcherdb-design-system.css").read_text(encoding="utf-8")


class TestF1Foundation(unittest.TestCase):
    def test_getsevtokens_defined(self):
        self.assertIn("function getSevTokens(severity)", PORTAL)

    def test_reads_v33_scale(self):
        self.assertIn("g('--sev-critical-solid')", PORTAL)
        self.assertIn("g('--sev-critical-tint')", PORTAL)

    def test_advc_tokenized(self):
        self.assertIn("const _ADVC = { crit: getSevTokens('CRITICAL').fill, warn: getSevTokens('WARNING').fill, ok: getSevTokens('OK').fill, info: getSevTokens('INFO').fill, gray: 'var(--color-text-tertiary)' };", PORTAL)


class TestF2HighContrast(unittest.TestCase):
    def test_gettheme_accepts_hc(self):
        self.assertIn("s === 'high-contrast'", PORTAL)

    def test_applytheme_accepts_hc(self):
        self.assertIn("theme = (theme === 'light' || theme === 'high-contrast') ? theme : 'dark';", PORTAL)

    def test_cycletheme_3way(self):
        self.assertIn("var o = ['dark', 'light', 'high-contrast'];", PORTAL)

    def test_antifouc_in_head(self):
        head = PORTAL.split("<title>")[0]
        self.assertIn("anti-FOUC", head)
        self.assertIn("setAttribute('data-theme'", head)

    def test_hc_css_block(self):
        self.assertIn('html[data-theme="high-contrast"] {', PORTAL)

    def test_hc_button(self):
        self.assertIn('data-kpi-theme-btn="high-contrast" onclick="applyTheme(\'high-contrast\')"', PORTAL)


class TestF3AttentionToken(unittest.TestCase):
    def test_attention_base_dark_in_ds(self):
        self.assertIn("--sev-attention-solid:  #ca8a04;", DS)

    def test_attention_light_in_monolith(self):
        self.assertIn("--sev-attention-text: #854d0e;", PORTAL)

    def test_utility_classes_in_ds(self):
        self.assertIn(".sev-critical { border-left-color: var(--sev-critical-solid);", DS)
        self.assertIn(".sev-ok       { border-left-color: var(--sev-ok-solid);", DS)


class TestF4LaddersBatch1(unittest.TestCase):
    def test_disk_trend_sevcolor(self):
        self.assertIn("var sevColor = getSevTokens(t.severity).fill;", PORTAL)

    def test_generic_sevcolor(self):
        self.assertIn("const sevColor = getSevTokens(severity).fill;", PORTAL)

    def test_muted_ok_preserved(self):
        self.assertIn("(severity === 'CRITICAL' || severity === 'WARNING') ? getSevTokens(severity).fill : 'var(--color-text-tertiary)'", PORTAL)


class TestF4LaddersBatch2(unittest.TestCase):
    """Batch 2: seguranca/logins + latencia + disco (espelha V6 inc4/inc8)."""

    def test_lat_color(self):
        self.assertIn("const latColor = l.avg_ms > 500 ? getSevTokens('CRITICAL').fill", PORTAL)

    def test_security_status(self):
        self.assertIn("const statusColor = u.enabled === false ? getSevTokens('CRITICAL').fill : getSevTokens('OK').fill;", PORTAL)
        self.assertIn("const lockedColor = data.locked_out ? getSevTokens('CRITICAL').fill : getSevTokens('OK').fill;", PORTAL)

    def test_orphaned_weakpwd(self):
        self.assertGreaterEqual(PORTAL.count("totalOrphaned > 0 ? getSevTokens('CRITICAL').fill : getSevTokens('OK').fill"), 2)
        self.assertGreaterEqual(PORTAL.count("totalWeakPwd > 0 ? getSevTokens('CRITICAL').fill : getSevTokens('OK').fill"), 2)

    def test_free_read_write(self):
        self.assertIn("const freeColor = group.free < 50 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("const readColor = readLat >= 50 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("const writeColor = writeLat >= 50 ? getSevTokens('CRITICAL').fill", PORTAL)


class TestF4LaddersBatch3(unittest.TestCase):
    """Batch 3: jobs/manutencao + disk-trends (espelha V6 inc5/inc6)."""

    def test_proj_color(self):
        self.assertIn("var projColor = t.daysUntilFull < 30 ? getSevTokens('CRITICAL').fill", PORTAL)

    def test_critcount_cards(self):
        self.assertGreaterEqual(PORTAL.count("critCount > 0 ? getSevTokens('CRITICAL').fill : getSevTokens('WARNING').fill"), 3)

    def test_maintenance_cards(self):
        self.assertGreaterEqual(PORTAL.count("hasIndexMaintenance ? getSevTokens('OK').fill : getSevTokens('CRITICAL').fill"), 2)
        self.assertGreaterEqual(PORTAL.count("maintenanceCoveragePct >= 80 ? getSevTokens('OK').fill"), 2)

    def test_failed24h(self):
        self.assertGreaterEqual(PORTAL.count("totalFailed24h > 0 ? getSevTokens('CRITICAL').fill : getSevTokens('OK').fill"), 2)


class TestF4LaddersBatch4(unittest.TestCase):
    """Batch 4: perf/espaco/conectividade (espelha V6 inc7/inc8/inc11)."""

    def test_overflow_db_problems(self):
        self.assertGreaterEqual(PORTAL.count("overflowCount > 0 ? getSevTokens('CRITICAL').fill : getSevTokens('OK').fill"), 2)
        # 2026-08-31: commit 9029a42 antepos guard de no-data ao ternario; a
        # intencao do teste (ladder tokenizada, sem hex) mantem-se -- ancora
        # relaxada para o troco tokenizado, sem prender o prefixo.
        self.assertIn("dbProblemsCount === 0 ? getSevTokens('OK').fill", PORTAL)

    def test_ple_rec_usage_cpu(self):
        self.assertIn("const pleColor = pleData.Status === 'CRITICAL' ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("const recColor = maxServerMemoryGB > recommendationMaxMemoryGB * 1.1 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("const usageColor = usagePct > 90 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("const cpuColor = cpuTime > 100 ? getSevTokens('CRITICAL').fill", PORTAL)

    def test_oom_free_error_env(self):
        self.assertIn("const oomColor = oom > 0 ? getSevTokens('CRITICAL').fill : 'var(--color-text-disabled)';", PORTAL)
        self.assertIn("const freePercentColor = freePercent < 2 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("const errorColor = details.type === 'Overflow' ? getSevTokens('CRITICAL').fill : getSevTokens('WARNING').fill;", PORTAL)
        self.assertIn("const envColor = env === 'PRD' ? getSevTokens('CRITICAL').fill : env === 'QLT' ? getSevTokens('WARNING').fill : getSevTokens('OK').fill;", PORTAL)


class TestF4LaddersBatch5(unittest.TestCase):
    """Batch 5: multi-linha + gold->ATTENTION (job status, severityColor 4-tier, health, envColor TST)."""

    def test_job_status_gold_attention(self):
        self.assertGreaterEqual(PORTAL.count("j.last_run_status === 'Sucesso' ? getSevTokens('OK').fill : getSevTokens('ATTENTION').fill"), 1)
        self.assertIn("j.run_status === 1 ? getSevTokens('OK').fill : getSevTokens('ATTENTION').fill", PORTAL)

    def test_severity_4tier(self):
        self.assertIn("g.Severity === 'HIGH' ? getSevTokens('ATTENTION').fill", PORTAL)
        self.assertIn("g.Severity === 'MEDIUM' ? getSevTokens('WARNING').fill", PORTAL)

    def test_health_env(self):
        self.assertIn("const healthColor = r.sync_health === 'HEALTHY' ? getSevTokens('OK').fill", PORTAL)
        self.assertIn("env === 'TST' ? getSevTokens('OK').fill : 'var(--color-text-tertiary)'", PORTAL)

    def test_memory_3tier(self):
        self.assertIn("const memoryColor = memoryMB > 2048 ? getSevTokens('CRITICAL').fill : memoryMB > 1024 ? getSevTokens('WARNING').fill : getSevTokens('OK').fill;", PORTAL)


class TestF4LaddersBatch6(unittest.TestCase):
    """Batch 6: overview health + perf CPU (espelha V6 inc3/inc8)."""

    def test_overview_cpu_memory_null(self):
        self.assertIn("cpuPercent !== null ? (cpuPercent >= 80 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("memoryPercent !== null ? (memoryPercent >= 90 ? getSevTokens('CRITICAL').fill", PORTAL)

    def test_minicard_calc(self):
        self.assertIn("const miniCardColor = (pct) => pct !== null ? (pct >= 95 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("const calcColor = (pct) => pct >= 95 ? getSevTokens('CRITICAL').fill", PORTAL)

    def test_os_sql_cpu(self):
        self.assertIn("${osCpuPct > 80 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("${sqlCpuPct > 80 ? getSevTokens('CRITICAL').fill", PORTAL)


class TestF4LaddersBatch7(unittest.TestCase):
    """Batch 7: borderColor isCritical (banda KPI-Avancada 34xxx)."""

    def test_border_iscritical(self):
        self.assertGreaterEqual(PORTAL.count("const borderColor = isCritical ? getSevTokens('CRITICAL').fill : getSevTokens('WARNING').fill;"), 2)

    def test_sevcolor_iscritical_attention(self):
        self.assertIn("const sevColor = isCritical ? getSevTokens('CRITICAL').fill : getSevTokens('ATTENTION').fill;", PORTAL)


class TestF4LaddersBatch8(unittest.TestCase):
    """Batch 8: cluster KPI-Avancada 34xxx -- env 5-way + metricas."""

    def test_env_5way(self):
        # PRD/QLT/TST/DEV/else -> CRIT/WARN/OK/INFO/text-disabled (5 variantes de var)
        self.assertGreaterEqual(PORTAL.count("=== 'DEV' ? getSevTokens('INFO').fill : 'var(--color-text-disabled)'"), 5)

    def test_metrics(self):
        self.assertIn("const pctColor = parseFloat(currentPctUsed) >= 95 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("const cpuColor = parseFloat(cpuPct) >= 95 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("const sevColor = itemSev === 'CRITICAL' ? getSevTokens('CRITICAL').fill", PORTAL)


class TestF4LaddersBatch9(unittest.TestCase):
    """Batch 9: single-liners dispersos (gap/count/pct/mb/rc/isAbove/hasFail)."""

    def test_misc_singleliners(self):
        self.assertIn("const gapColor = gapH >= 72 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("const countColor = dlCount >= 20 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("const mbColor = mb > 1024 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("const rcColor = rc > 20 ? getSevTokens('CRITICAL').fill", PORTAL)
        self.assertIn("const statusColor = isAbove ? getSevTokens('CRITICAL').fill", PORTAL)


class TestNoRegression(unittest.TestCase):
    def test_no_hardcoded_env5way(self):
        self.assertNotIn("=== 'DEV' ? '#3b82f6' : 'var(--color-text-disabled)'", PORTAL)

    def test_no_hardcoded_oscpu(self):
        self.assertNotIn("${osCpuPct > 80 ? '#ef4444'", PORTAL)

    def test_no_hardcoded_severity_high(self):
        self.assertNotIn("g.Severity === 'HIGH' ? '#f97316'", PORTAL)

    def test_no_hardcoded_ple(self):
        self.assertNotIn("const pleColor = pleData.Status === 'CRITICAL' ? '#ef4444'", PORTAL)

    def test_no_hardcoded_proj(self):
        self.assertNotIn("var projColor = t.daysUntilFull < 30 ? '#ef4444'", PORTAL)

    def test_no_hardcoded_security(self):
        self.assertNotIn("const statusColor = u.enabled === false ? '#ef4444' : '#10b981';", PORTAL)

    def test_no_hardcoded_advc(self):
        self.assertNotIn("const _ADVC = { crit: '#ef4444', warn: '#f59e0b', ok: '#22c55e', info: '#3b82f6'", PORTAL)

    def test_applytheme_no_longer_binary(self):
        self.assertNotIn("theme = (theme === 'light') ? 'light' : 'dark';", PORTAL)

    def test_batch1_sevcolor_gone(self):
        self.assertNotIn("var sevColor = t.severity === 'CRITICAL' ? '#ef4444'", PORTAL)


class TestF4Complete(unittest.TestCase):
    """F4 COMPLETO -- todas as ladders de severidade tokenizadas.
    So fica o roxo #8b5cf6 categorico (AON saudavel / acentos decorativos), por decisao."""

    def test_no_severity_ladders_remain(self):
        # nenhuma escada de severidade hardcoded resta (excl. decorativos)
        self.assertNotIn("=== 'CRITICAL' ? '#ef4444'", PORTAL)
        self.assertNotIn("severity === 'CRITICAL' ? '#ef4444'", PORTAL)

    def test_purple_categorical_kept(self):
        self.assertIn("8b5cf6", PORTAL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
