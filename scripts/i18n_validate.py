#!/usr/bin/env python3
"""
WatcherDB i18n Validation Script
=================================
Validates translation files for:
1. Missing keys between languages
2. Orphan keys (in JSON but not used in code)
3. Inconsistent interpolation variables ({var})
4. Inconsistent pluralization (pipe count)
5. Empty values
6. Duplicate values that may indicate untranslated strings

Usage:
    python scripts/i18n_validate.py
    python scripts/i18n_validate.py --strict    # fail on warnings too
    python scripts/i18n_validate.py --fix       # auto-add missing keys with TODO marker
"""

import json
import os
import re
import sys
import glob
from collections import defaultdict

# ========================================
# CONFIGURATION
# ========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..')
I18N_DIR = os.path.join(PROJECT_ROOT, 'static', 'i18n')
REFERENCE_LANG = 'pt'  # The "source of truth" language
SUPPORTED_LANGS = ['pt', 'en', 'es']

# Files to scan for key usage
SCAN_PATTERNS = [
    os.path.join(PROJECT_ROOT, 'templates', '*.html'),
    os.path.join(PROJECT_ROOT, 'static', 'js', '*.js'),
]

# ========================================
# HELPERS
# ========================================

def flatten_dict(d, prefix=''):
    """Flatten nested dict to dot-notation keys."""
    result = {}
    for k, v in d.items():
        key = f'{prefix}.{k}' if prefix else k
        if isinstance(v, dict):
            result.update(flatten_dict(v, key))
        else:
            result[key] = str(v)
    return result


def load_translations(lang):
    """Load and flatten a language JSON file."""
    path = os.path.join(I18N_DIR, f'{lang}.json')
    if not os.path.exists(path):
        print(f'  [ERROR] File not found: {path}')
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return flatten_dict(data)


def extract_interpolation_vars(value):
    """Extract {variable} names from a translation value."""
    return set(re.findall(r'\{(\w+)\}', value))


def count_plural_forms(value):
    """Count pipe-separated plural forms."""
    if '|' in value:
        return len(value.split('|'))
    return 0


def find_used_keys():
    """Scan source files for t('key') and data-i18n="key" usage."""
    used_keys = set()
    patterns = [
        r"""t\(\s*['"]([^'"]+)['"]\s*""",          # t('key') or t("key")
        r'data-i18n="([^"]+)"',                     # data-i18n="key"
        r'data-i18n-placeholder="([^"]+)"',          # data-i18n-placeholder="key"
        r'data-i18n-title="([^"]+)"',                # data-i18n-title="key"
        r'data-i18n-aria="([^"]+)"',                 # data-i18n-aria="key"
    ]

    for pattern_glob in SCAN_PATTERNS:
        for filepath in glob.glob(pattern_glob, recursive=True):
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                for regex in patterns:
                    matches = re.findall(regex, content)
                    used_keys.update(matches)
            except Exception as e:
                print(f'  [WARN] Could not scan {filepath}: {e}')

    return used_keys


# ========================================
# VALIDATORS
# ========================================

def validate_missing_keys(translations):
    """Check for keys missing in any language vs reference."""
    errors = []
    ref_keys = set(translations[REFERENCE_LANG].keys())

    for lang in SUPPORTED_LANGS:
        if lang == REFERENCE_LANG:
            continue
        lang_keys = set(translations[lang].keys())

        # Keys in reference but missing in this lang
        missing = ref_keys - lang_keys
        if missing:
            for key in sorted(missing):
                errors.append({
                    'level': 'ERROR',
                    'type': 'MISSING_KEY',
                    'lang': lang,
                    'key': key,
                    'message': f'Key "{key}" exists in {REFERENCE_LANG} but missing in {lang}'
                })

        # Extra keys in this lang not in reference
        extra = lang_keys - ref_keys
        if extra:
            for key in sorted(extra):
                errors.append({
                    'level': 'WARN',
                    'type': 'EXTRA_KEY',
                    'lang': lang,
                    'key': key,
                    'message': f'Key "{key}" exists in {lang} but not in {REFERENCE_LANG}'
                })

    return errors


def validate_interpolation(translations):
    """Check that {variables} are consistent across languages."""
    errors = []
    ref = translations[REFERENCE_LANG]

    for key, ref_value in ref.items():
        ref_vars = extract_interpolation_vars(ref_value)
        if not ref_vars:
            continue

        for lang in SUPPORTED_LANGS:
            if lang == REFERENCE_LANG:
                continue
            if key not in translations[lang]:
                continue

            lang_vars = extract_interpolation_vars(translations[lang][key])

            if ref_vars != lang_vars:
                errors.append({
                    'level': 'ERROR',
                    'type': 'INTERPOLATION_MISMATCH',
                    'lang': lang,
                    'key': key,
                    'message': f'Interpolation vars differ: {REFERENCE_LANG}={ref_vars}, {lang}={lang_vars}'
                })

    return errors


def validate_pluralization(translations):
    """Check that pipe-separated plural forms are consistent."""
    errors = []
    ref = translations[REFERENCE_LANG]

    for key, ref_value in ref.items():
        ref_forms = count_plural_forms(ref_value)
        if ref_forms == 0:
            continue

        for lang in SUPPORTED_LANGS:
            if lang == REFERENCE_LANG:
                continue
            if key not in translations[lang]:
                continue

            lang_forms = count_plural_forms(translations[lang][key])

            if ref_forms != lang_forms:
                errors.append({
                    'level': 'ERROR',
                    'type': 'PLURAL_MISMATCH',
                    'lang': lang,
                    'key': key,
                    'message': f'Plural forms differ: {REFERENCE_LANG}={ref_forms} forms, {lang}={lang_forms} forms'
                })

    return errors


def validate_empty_values(translations):
    """Check for empty string values."""
    errors = []
    for lang in SUPPORTED_LANGS:
        for key, value in translations[lang].items():
            if value.strip() == '':
                errors.append({
                    'level': 'WARN',
                    'type': 'EMPTY_VALUE',
                    'lang': lang,
                    'key': key,
                    'message': f'Empty value for key "{key}" in {lang}'
                })
    return errors


def validate_untranslated(translations):
    """Detect keys where EN/ES value is same as PT (possibly untranslated)."""
    errors = []
    ref = translations[REFERENCE_LANG]

    # Skip keys that are legitimately the same (technical terms, proper nouns)
    skip_patterns = [
        r'^cat\.',   # categories
        r'.*\.sql_', # SQL-related terms
    ]
    # Common words that should be different across languages
    same_ok_values = {
        'OK', 'N/A', '-', 'CPU', 'RAM', 'SQL', 'TDE', 'IOPS', 'SLA', 'KPI',
        'Always On', 'Backup', 'Dashboard', 'Login', 'Logout', 'API', 'CSV',
        'JSON', 'NULL', 'TempDB', 'Performance', 'Email', 'Ping', 'DNS',
        'TCP', 'ODBC', 'Collation', 'Recovery Model', 'Full', 'Differential',
        'Log', 'Online', 'Offline', 'High', 'Medium', 'Low',
    }

    for key, ref_value in ref.items():
        if ref_value.strip() in same_ok_values:
            continue
        if any(re.match(p, key) for p in skip_patterns):
            continue

        for lang in SUPPORTED_LANGS:
            if lang == REFERENCE_LANG:
                continue
            if key not in translations[lang]:
                continue
            if translations[lang][key] == ref_value and len(ref_value) > 3:
                errors.append({
                    'level': 'WARN',
                    'type': 'POSSIBLY_UNTRANSLATED',
                    'lang': lang,
                    'key': key,
                    'message': f'Value in {lang} identical to {REFERENCE_LANG}: "{ref_value[:60]}"'
                })

    return errors


def validate_orphan_keys(translations):
    """Check for keys in JSON that are never used in code."""
    used_keys = find_used_keys()
    if not used_keys:
        print('  [INFO] No source files scanned — skipping orphan check')
        return []

    all_keys = set(translations[REFERENCE_LANG].keys())
    orphans = all_keys - used_keys

    errors = []
    for key in sorted(orphans):
        errors.append({
            'level': 'INFO',
            'type': 'ORPHAN_KEY',
            'lang': REFERENCE_LANG,
            'key': key,
            'message': f'Key "{key}" not found in any source file (may be dynamically constructed)'
        })

    return errors


# ========================================
# AUTO-FIX
# ========================================

def auto_fix_missing(translations):
    """Add missing keys with a TODO marker."""
    ref = translations[REFERENCE_LANG]
    ref_keys = set(ref.keys())
    fixed = 0

    for lang in SUPPORTED_LANGS:
        if lang == REFERENCE_LANG:
            continue
        lang_keys = set(translations[lang].keys())
        missing = ref_keys - lang_keys

        if not missing:
            continue

        # Load original JSON
        path = os.path.join(I18N_DIR, f'{lang}.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for key in sorted(missing):
            # Add the PT value prefixed with [TODO]
            parts = key.split('.')
            current = data
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = f'[TODO] {ref[key]}'
            fixed += 1

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)

        print(f'  [FIX] Added {len(missing)} missing keys to {lang}.json with [TODO] prefix')

    return fixed


# ========================================
# MAIN
# ========================================

def main():
    strict = '--strict' in sys.argv
    fix = '--fix' in sys.argv

    print('=' * 60)
    print('WatcherDB i18n Validation')
    print('=' * 60)

    # Load all translations
    translations = {}
    for lang in SUPPORTED_LANGS:
        translations[lang] = load_translations(lang)
        print(f'  {lang}: {len(translations[lang])} keys loaded')

    print()
    all_issues = []

    # Run validators
    print('[1/6] Checking missing keys...')
    all_issues.extend(validate_missing_keys(translations))

    print('[2/6] Checking interpolation consistency...')
    all_issues.extend(validate_interpolation(translations))

    print('[3/6] Checking pluralization consistency...')
    all_issues.extend(validate_pluralization(translations))

    print('[4/6] Checking empty values...')
    all_issues.extend(validate_empty_values(translations))

    print('[5/6] Checking possibly untranslated strings...')
    all_issues.extend(validate_untranslated(translations))

    print('[6/6] Checking orphan keys...')
    all_issues.extend(validate_orphan_keys(translations))

    # Report
    print()
    print('=' * 60)
    print('RESULTS')
    print('=' * 60)

    by_level = defaultdict(list)
    for issue in all_issues:
        by_level[issue['level']].append(issue)

    for level in ['ERROR', 'WARN', 'INFO']:
        issues = by_level.get(level, [])
        if issues:
            print(f'\n  [{level}] {len(issues)} issues:')
            # Group by type
            by_type = defaultdict(list)
            for i in issues:
                by_type[i['type']].append(i)
            for itype, items in sorted(by_type.items()):
                print(f'    {itype}: {len(items)}')
                for item in items[:5]:  # show first 5
                    print(f'      - {item["message"]}')
                if len(items) > 5:
                    print(f'      ... and {len(items) - 5} more')

    # Summary
    errors = len(by_level.get('ERROR', []))
    warns = len(by_level.get('WARN', []))
    infos = len(by_level.get('INFO', []))

    print(f'\n  Summary: {errors} errors, {warns} warnings, {infos} info')

    # Auto-fix if requested
    if fix and errors > 0:
        print('\n[FIX] Auto-fixing missing keys...')
        fixed = auto_fix_missing(translations)
        print(f'  Fixed {fixed} issues')

    # Exit code
    if errors > 0:
        print('\n  FAILED — fix errors above')
        return 1
    if strict and warns > 0:
        print('\n  FAILED (strict mode) — fix warnings above')
        return 1

    print('\n  PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
