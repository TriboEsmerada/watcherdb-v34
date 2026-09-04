#!/usr/bin/env python3
"""Wave BUG-003 -- Lote F2c: defeitos nas chaves ANTIGAS de pt.json/es.json (achados incidentais do v33-i18n-linguist no F2).

So' texto nos JSON (edicao por TEXTO, pt.json tem chaves duplicadas -- nunca round-trip):
- es: "Critico" -> "Crítico" (acentuacao, exigencia owner), "Memoria Critico" -> "Memoria Crítica",
      "Trabajos Backup Deshabilitados" -> "Jobs de Backup Deshabilitados" (glossario), "DB Disco File System" ->
      "DB Disk File System", "Advertencia" -> "Aviso" (harmonizado com kpi_adv/kpi_meta; TempDB mantem "Atención"),
      "Uso FileGroups" -> "Uso de FileGroups".
- pt: "Memória Crítico" -> "Memória Crítica" (concordancia), processes_alarm_count com acentos, "Warning"/"Critical"
      nunca traduzidos -> "Aviso"/"Crítico", "Backup Jobs Disabled" -> "Jobs de Backup Desativados",
      "FileGroups Usage" -> "Utilização de FileGroups" (como kpi_meta).
Identidade: owner. Onde: raiz do V3.4.
    py -3.14 docs/context/I18N_F2C_PASSO1_apply.py --dry-run
    py -3.14 docs/context/I18N_F2C_PASSO1_apply.py
Rollback: git checkout -- static/i18n/pt.json static/i18n/es.json docs/changelog/CHANGELOG.md
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PT, ES, CHG = "static/i18n/pt.json", "static/i18n/es.json", "docs/changelog/CHANGELOG.md"

def kv(k, old, new, comma=True):
    c = "," if comma else ""
    return ('"%s": "%s"%s' % (k, old, c), '"%s": "%s"%s' % (k, new, c))

PATCHES = [
    # ---------------- pt.json ----------------
    (PT, *kv("memory_critical", "Memória Crítico", "Memória Crítica"), 1),
    (PT, *kv("memory_critical_modal", "Memória Crítico - Instâncias com Memória Alta", "Memória Crítica - Instâncias com Memória Alta"), 1),
    (PT, *kv("memory_critical", "Memória Crítico - Instâncias com Memória Alta", "Memória Crítica - Instâncias com Memória Alta"), 1),
    (PT, *kv("processes_alarm_count", "Instancias com sessoes RUNNABLE acima do threshold", "Instâncias com sessões RUNNABLE acima do threshold"), 1),
    (PT, *kv("disk_latency_critical", "Critical (>= 50ms)", "Crítico (>= 50ms)"), 1),
    (PT, *kv("backup_jobs_disabled", "Backup Jobs Disabled", "Jobs de Backup Desativados"), 2),
    (PT, *kv("disk_warning", "DB Disk File System - Warning", "DB Disk File System - Aviso"), 1),
    (PT, *kv("filegroup_critical", "FileGroups Usage - Critical", "Utilização de FileGroups - Crítico"), 1),
    (PT, *kv("filegroup_warning", "FileGroups Usage - Warning", "Utilização de FileGroups - Aviso"), 1),
    (PT, *kv("tlog_warning", "DB Transaction Logs - Warning", "DB Transaction Logs - Aviso", comma=False), 1),
    # ---------------- es.json ----------------
    (ES, *kv("backup_jobs_disabled", "Trabajos Backup Deshabilitados", "Jobs de Backup Deshabilitados"), 2),
    (ES, *kv("cpu_critical", "CPU Critico", "CPU Crítico"), 1),
    (ES, *kv("cpu_critical_modal", "CPU Critico - Instancias con CPU Alto", "CPU Crítico - Instancias con CPU Alto"), 1),
    (ES, *kv("disk_latency_critical", "Critico (>= 50ms)", "Crítico (>= 50ms)"), 1),
    (ES, *kv("memory_critical", "Memoria Critico", "Memoria Crítica"), 1),
    (ES, *kv("memory_critical_modal", "Memoria Critico - Instancias con Memoria Alta", "Memoria Crítica - Instancias con Memoria Alta"), 1),
    (ES, *kv("cpu_critical", "CPU Critico - Instancias con CPU Alto", "CPU Crítico - Instancias con CPU Alto"), 1),
    (ES, *kv("disk_critical", "DB Disco File System - Critico", "DB Disk File System - Crítico"), 1),
    (ES, *kv("disk_latency_critical", "Latencia de Disco Critico - Drives con Alta Latencia", "Latencia de Disco Crítico - Drives con Alta Latencia"), 1),
    (ES, *kv("disk_warning", "DB Disco File System - Advertencia", "DB Disk File System - Aviso"), 1),
    (ES, *kv("filegroup_critical", "Uso FileGroups - Critico", "Uso de FileGroups - Crítico"), 1),
    (ES, *kv("filegroup_warning", "Uso FileGroups - Advertencia", "Uso de FileGroups - Aviso"), 1),
    (ES, *kv("memory_critical", "Memoria Critico - Instancias con Memoria Alta", "Memoria Crítica - Instancias con Memoria Alta"), 1),
    (ES, *kv("tempdb_critical", "TempDB - Disco Critico", "TempDB - Disco Crítico"), 1),
    (ES, *kv("tempdb_warning", "TempDB - Disco Advertencia", "TempDB - Disco Atención"), 1),
    (ES, *kv("tlog_critical", "DB Transaction Logs - Critico", "DB Transaction Logs - Crítico"), 1),
    (ES, *kv("tlog_warning", "DB Transaction Logs - Advertencia", "DB Transaction Logs - Aviso", comma=False), 1),
    (ES, *kv("disk_critical", "Disco Critico", "Disco Crítico"), 1),
    (ES, *kv("filegroup_critical", "Filegroup Critico", "Filegroup Crítico"), 1),
    (ES, *kv("tlog_critical", "Transaction Log Critico", "Transaction Log Crítico", comma=False), 1),
    # ---- varrimento completo de "Critico"/"Advertencia" em es.json (regra: acentuacao rigorosa) ----
    (ES, *kv("severity_critical", "Critico", "Crítico"), 2),
    (ES, *kv("critical_95", "Critico >=95%", "Crítico >=95%"), 1),
    (ES, *kv("critical_95", "Critico (>=95%)", "Crítico (>=95%)"), 1),
    (ES, *kv("legend_critical", "Critico >=95%", "Crítico >=95%"), 1),
    (ES, *kv("critical_conflicts", "Conflictos Criticos", "Conflictos Críticos"), 1),
    (ES, *kv("cpu_critico", "CPU Critico", "CPU Crítico"), 1),
    (ES, *kv("critical", "Critico", "Crítico"), 3),
    (ES, *kv("memoria_critico", "Memoria Critico", "Memoria Crítica"), 1),
    (ES, *kv("disk_latency_warning", "Advertencia (>= 20ms)", "Aviso (>= 20ms)"), 1),
    (ES, *kv("warning", "Advertencia", "Aviso"), 1),
    (ES, *kv("disk_threshold_col_warn", "Advertencia si libre <", "Aviso si libre <"), 1),
    (ES, *kv("disk_threshold_col_crit", "Critico si libre <", "Crítico si libre <"), 1),
    (ES, *kv("disk_latency_warning", "Latencia de Disco Advertencia - Drives con Latencia Elevada", "Latencia de Disco Aviso - Drives con Latencia Elevada"), 1),
    (ES, *kv("critical_down", "Criticos Caidos", "Críticos Caídos"), 1),
    (ES, *kv("warning_90", "Advertencia (>=90%)", "Aviso (>=90%)", comma=False), 1),
    # ---- pt: chave irma que a lista do linguista nao tinha ----
    (PT, *kv("memoria_critico", "Memória Crítico", "Memória Crítica"), 1),
]

CHANGELOG_ENTRY = """- **i18n lote F2c: defeitos nas chaves antigas de `pt.json` e `es.json`** (achados do
  v33-i18n-linguist ao reutilizar chaves no F2). Espanhol: "Critico" → "Crítico" em 11 chaves,
  "Memoria Critico" → "Memoria Crítica", "Trabajos" → "Jobs" (glossário), "DB Disco File System" →
  "DB Disk File System", "Advertencia" → "Aviso" (TempDB mantém "Atención"). Português: "Memória
  Crítico" → "Memória Crítica", acentos em `processes_alarm_count`, "Warning"/"Critical" nunca
  traduzidos → "Aviso"/"Crítico", "Backup Jobs Disabled" → "Jobs de Backup Desativados",
  "FileGroups Usage" → "Utilização de FileGroups". Varrimento completo: zero "Critico"/"Advertencia"
  restantes em `es.json`. Só texto, 47 chaves. [tier: Std]
"""


def read(p):
    raw = p.read_bytes().decode("utf-8"); return raw, ("\r\n" if "\r\n" in raw else "\n")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(); root = Path(a.root).resolve(); print(f"root: {root}  dry-run={a.dry_run}")
    texts, problems = {}, []
    for rel, old, new, n in PATCHES:
        texts.setdefault(rel, read(root / rel)); raw, _ = texts[rel]
        c = raw.count(old)
        if c != n: problems.append(f"{rel}: esperado {n}x, encontrado {c}x -> {old}")
    craw, cnl = read(root / CHG)
    anchor = "## [Unreleased]" + cnl + cnl + "### Changed" + cnl + cnl
    if craw.count(anchor) != 1: problems.append("CHANGELOG: ancora nao encontrada 1x")
    if "lote F2c" in craw: problems.append("CHANGELOG: entrada F2c ja existe")
    if problems:
        print("[ABORT] nada foi escrito:"); [print("   -", x) for x in problems]; sys.exit(2)
    for rel, old, new, n in PATCHES:
        raw, nl = texts[rel]; texts[rel] = (raw.replace(old, new), nl)
    for rel, (raw, _) in texts.items():
        json.loads(raw)  # continua JSON valido
    if a.dry_run:
        print(f"[DRY] {len(PATCHES)} patches OK ({sum(n for *_, n in PATCHES)} ocorrencias) + CHANGELOG"); return
    for rel, (raw, _) in texts.items():
        (root / rel).write_bytes(raw.encode("utf-8")); print(f"[OK] {rel}")
    (root / CHG).write_bytes(craw.replace(anchor, anchor + CHANGELOG_ENTRY.replace("\n", cnl) + cnl, 1).encode("utf-8")); print(f"[OK] {CHG}")
    print("\nSeguir com: py -3.14 -m pytest tests/unit/test_i18n_parity.py -q --no-cov ; py -3.14 scripts/i18n_validate.py")


if __name__ == "__main__":
    main()
