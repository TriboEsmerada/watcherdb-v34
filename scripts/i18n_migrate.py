#!/usr/bin/env python3
"""
WatcherDB i18n Migration Script: v1 -> v2
==========================================
Migrates from the old monolithic watcherdb_i18n.js to the new
JSON-based system (watcherdb_i18n_v2.js + static/i18n/*.json).

Steps:
1. Extract all translations from watcherdb_i18n.js (v1)
2. Merge with existing JSON files (preserving new keys)
3. Generate integration snippet for watcherdb_portal.html
4. Create backup of v1 file

Usage:
    python scripts/i18n_migrate.py              # dry-run (show changes)
    python scripts/i18n_migrate.py --apply       # apply migration
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..')
V1_FILE = os.path.join(PROJECT_ROOT, 'static', 'js', 'watcherdb_i18n.js')
V2_FILE = os.path.join(PROJECT_ROOT, 'static', 'js', 'watcherdb_i18n_v2.js')
I18N_DIR = os.path.join(PROJECT_ROOT, 'static', 'i18n')
PORTAL_FILE = os.path.join(PROJECT_ROOT, 'templates', 'watcherdb_portal.html')


def extract_v1_translations():
    """Extract translations from the v1 JS file."""
    with open(V1_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    langs = {}
    for lang in ['pt', 'en', 'es']:
        pattern = rf"    {lang}: \{{(.*?)\n    \}}"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            block = match.group(1)
            pairs = re.findall(r"'([^']+)'\s*:\s*'([^']*)'", block)
            langs[lang] = dict(pairs)
            print(f'  Extracted {len(langs[lang])} keys from v1 {lang}')

    return langs


def flat_to_nested(flat_dict):
    """Convert flat dot-notation keys to nested dict."""
    nested = {}
    for key, val in sorted(flat_dict.items()):
        parts = key.split('.')
        current = nested
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            elif not isinstance(current[part], dict):
                # Collision: key is both a leaf and a branch
                # Keep the leaf value and skip nesting
                break
            current = current[part]
        current[parts[-1]] = val
    return nested


def flatten_dict(d, prefix=''):
    """Flatten nested dict to dot-notation."""
    result = {}
    for k, v in d.items():
        key = f'{prefix}.{k}' if prefix else k
        if isinstance(v, dict):
            result.update(flatten_dict(v, key))
        else:
            result[key] = str(v)
    return result


def merge_translations(v1_flat, existing_json_nested):
    """Merge v1 translations into existing JSON, preserving new keys."""
    existing_flat = flatten_dict(existing_json_nested)

    merged = dict(existing_flat)  # Start with existing

    added = 0
    for key, value in v1_flat.items():
        if key not in merged:
            merged[key] = value
            added += 1

    return merged, added


def generate_integration_snippet():
    """Generate the HTML snippet to replace v1 script tag with v2."""
    snippet = """
<!-- ========================================
     i18n v2 Integration
     Replace the old <script src="/static/js/watcherdb_i18n.js"> with:
     ======================================== -->

<!-- i18n Selector CSS -->
<link rel="stylesheet" href="/static/css/i18n_selector.css">

<!-- i18n Engine v2 -->
<script src="/static/js/watcherdb_i18n_v2.js"></script>

<!-- Initialize i18n with PT dictionary (inline for instant availability) -->
<script>
(async function() {
    // Load PT dictionary eagerly (prevents FOUC)
    try {
        const resp = await fetch('/static/i18n/pt.json?v=' + Date.now());
        const ptDict = await resp.json();
        WatcherI18N.registerDictionary('pt', ptDict);
    } catch(e) {
        console.error('[I18N] Failed to load PT dictionary:', e);
    }

    // Initialize (restores saved language, starts MutationObserver)
    await WatcherI18N.init();

    // Create language selector in the header
    // Place this selector in your header toolbar, e.g.:
    //   <div id="headerToolbar"> ... </div>
    WatcherI18N.createLanguageSelector('#headerToolbar');
})();
</script>
"""
    return snippet


def main():
    apply = '--apply' in sys.argv

    print('=' * 60)
    print('WatcherDB i18n Migration: v1 -> v2')
    print('=' * 60)

    # Step 1: Extract v1 translations
    print('\n[1/4] Extracting v1 translations...')
    if not os.path.exists(V1_FILE):
        print(f'  ERROR: v1 file not found: {V1_FILE}')
        return 1
    v1_langs = extract_v1_translations()

    # Step 2: Merge with existing JSONs
    print('\n[2/4] Merging with existing JSON files...')
    for lang in ['pt', 'en', 'es']:
        json_path = os.path.join(I18N_DIR, f'{lang}.json')
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            merged, added = merge_translations(v1_langs.get(lang, {}), existing)
            print(f'  {lang}: {added} new keys from v1 merged (total: {len(merged)})')

            if apply and added > 0:
                nested = flat_to_nested(merged)
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(nested, f, ensure_ascii=False, indent=2, sort_keys=True)
                print(f'    -> Written to {json_path}')
        else:
            # Create new JSON from v1
            nested = flat_to_nested(v1_langs.get(lang, {}))
            print(f'  {lang}: creating new file with {len(v1_langs.get(lang, {}))} keys')
            if apply:
                os.makedirs(I18N_DIR, exist_ok=True)
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(nested, f, ensure_ascii=False, indent=2, sort_keys=True)

    # Step 3: Backup v1 file
    print('\n[3/4] Backup v1 file...')
    backup_name = f'watcherdb_i18n_v1_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.js'
    backup_path = os.path.join(PROJECT_ROOT, 'static', 'js', backup_name)
    if apply:
        shutil.copy2(V1_FILE, backup_path)
        print(f'  -> Backed up to {backup_name}')
    else:
        print(f'  Would backup to: {backup_name}')

    # Step 4: Generate integration snippet
    print('\n[4/4] Integration snippet:')
    snippet = generate_integration_snippet()
    print(snippet)

    if not apply:
        print('\n' + '=' * 60)
        print('DRY RUN -- no changes made. Run with --apply to apply.')
        print('=' * 60)
    else:
        print('\n' + '=' * 60)
        print('Migration applied successfully!')
        print('=' * 60)
        print('\nNext steps:')
        print('  1. Replace <script src="watcherdb_i18n.js"> in portal HTML')
        print('  2. Add the integration snippet shown above')
        print('  3. Add <div id="headerToolbar"> in your header for the lang selector')
        print('  4. Run: python scripts/i18n_validate.py')
        print('  5. Run: python scripts/i18n_scan_hardcoded.py --verbose')

    return 0


if __name__ == '__main__':
    sys.exit(main())
