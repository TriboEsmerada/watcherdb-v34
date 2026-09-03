#!/usr/bin/env python3
"""
WatcherDB i18n Hardcoded String Scanner
=========================================
Scans HTML templates and JS files for hardcoded Portuguese strings
that should be replaced with i18n t() calls.

Detects:
1. Portuguese text in HTML tags (not inside t() or data-i18n)
2. Hardcoded strings in JS template literals
3. Strings assigned to .textContent, .innerHTML, .innerText, .placeholder
4. Alert messages, confirm dialogs
5. Console messages (excluded by default)

Usage:
    python scripts/i18n_scan_hardcoded.py
    python scripts/i18n_scan_hardcoded.py --verbose     # show context
    python scripts/i18n_scan_hardcoded.py --output report.csv
"""

import os
import re
import sys
import csv
from collections import defaultdict

# ========================================
# CONFIGURATION
# ========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..')

SCAN_FILES = [
    os.path.join(PROJECT_ROOT, 'templates', 'watcherdb_portal.html'),
    os.path.join(PROJECT_ROOT, 'static', 'js', 'innovative_features.js'),
    os.path.join(PROJECT_ROOT, 'static', 'js', 'portal_fix_patch.js'),
]

# Portuguese indicators — words that signal a hardcoded PT string
PT_INDICATORS = [
    # Common Portuguese words (case-insensitive matching)
    r'\b(?:Carregando|Erro|Servidor|Instância|Instancia|Usuário|Usuario)\b',
    r'\b(?:Análise|Analise|Configurações|Configuracoes|Disponível|Disponivel)\b',
    r'\b(?:Último|Ultimo|Primeira|Segunda|Terceira|Quarta|Quinta|Sexta)\b',
    r'\b(?:Nenhum|Nenhuma|Resultado|Sucesso|Falha|Atenção|Atencao)\b',
    r'\b(?:Buscar|Pesquisar|Filtrar|Exportar|Importar|Atualizar)\b',
    r'\b(?:Selecione|Selecionar|Confirmar|Cancelar|Guardar|Eliminar)\b',
    r'\b(?:Detalhes|Relatório|Relatorio|Dados|Verificação|Verificacao)\b',
    r'\b(?:Ambiente|Produção|Producao|Qualidade|Teste)\b',
    r'\b(?:Tamanho|Espaço|Espaco|Memória|Memoria|Disco)\b',
    r'\b(?:Segurança|Seguranca|Senha|Permissão|Permissao)\b',
    r'\b(?:Bloqueio|Bloqueado|Parado|Executando|Habilitado|Desabilitado)\b',
    r'\b(?:Saudável|Saudavel|Crítico|Critico|Recuperável|Recuperavel)\b',
    r'\b(?:sem|com|para|entre|sobre|como|mais|menos|todos|todas)\b',
    r'\b(?:não|nao|sim|ou|aqui|agora|ainda|depois|antes)\b',
    # Accented characters (strong indicator of PT/ES)
    r'[àáâãéêíóôõúüçÀÁÂÃÉÊÍÓÔÕÚÜÇ]',
]

# Patterns to SKIP (not hardcoded strings)
SKIP_PATTERNS = [
    r"t\('",                    # Already using t()
    r't\("',                    # Already using t()
    r'data-i18n',               # Already using data-i18n
    r'console\.\w+\(',          # Console messages
    r'<!--',                    # HTML comments
    r'^\s*//',                  # JS comments
    r'^\s*\*',                  # JSDoc comments
    r'font-family',             # CSS
    r'class="',                 # CSS classes
    r'style="',                 # Inline styles
    r'id="',                    # Element IDs
    r'https?://',               # URLs
    r'\.json',                  # File references
    r'\.py',                    # File references
    r'\.sql',                   # File references
    r'SELECT|INSERT|UPDATE|DELETE|FROM|WHERE',  # SQL
    r'function\s+\w+',         # Function definitions
    r'var\s+\w+',              # Variable declarations
    r'const\s+\w+',            # Const declarations
    r'let\s+\w+',              # Let declarations
]

# ========================================
# SCANNER
# ========================================

def is_portuguese_string(text):
    """Check if a string contains Portuguese text indicators."""
    for pattern in PT_INDICATORS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def should_skip_line(line):
    """Check if a line should be skipped."""
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, line):
            return True
    return False


def scan_html_hardcoded(filepath):
    """Scan HTML for hardcoded text content."""
    findings = []

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or should_skip_line(stripped):
            continue

        # Pattern 1: Text between HTML tags that's not a variable
        # e.g., <span>Carregando...</span>
        tag_texts = re.findall(r'>([^<>{}\[\]]+)</', line)
        for text in tag_texts:
            text = text.strip()
            if len(text) > 2 and is_portuguese_string(text):
                findings.append({
                    'file': filepath,
                    'line': i,
                    'type': 'HTML_TAG_TEXT',
                    'text': text[:100],
                    'context': stripped[:150]
                })

        # Pattern 2: Placeholder attributes with PT text
        placeholders = re.findall(r'placeholder="([^"]+)"', line)
        for ph in placeholders:
            if is_portuguese_string(ph) and 'data-i18n-placeholder' not in line:
                findings.append({
                    'file': filepath,
                    'line': i,
                    'type': 'PLACEHOLDER',
                    'text': ph[:100],
                    'context': stripped[:150]
                })

        # Pattern 3: Title attributes with PT text
        titles = re.findall(r'title="([^"]+)"', line)
        for title in titles:
            if is_portuguese_string(title) and 'data-i18n-title' not in line:
                findings.append({
                    'file': filepath,
                    'line': i,
                    'type': 'TITLE_ATTR',
                    'text': title[:100],
                    'context': stripped[:150]
                })

    return findings


def scan_js_hardcoded(filepath):
    """Scan JS for hardcoded strings assigned to DOM properties."""
    findings = []

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or should_skip_line(stripped):
            continue

        # Pattern 1: .textContent = 'Portuguese text'
        # Pattern 2: .innerHTML = 'Portuguese text'
        # Pattern 3: .innerText = 'Portuguese text'
        dom_assigns = re.findall(
            r'\.(textContent|innerHTML|innerText|placeholder)\s*=\s*[\'"`]([^\'"`]+)[\'"`]',
            line
        )
        for prop, text in dom_assigns:
            if is_portuguese_string(text):
                findings.append({
                    'file': filepath,
                    'line': i,
                    'type': f'JS_{prop.upper()}',
                    'text': text[:100],
                    'context': stripped[:150]
                })

        # Pattern 4: Template literal with PT text (inside backticks)
        # Look for `...Portuguese text...`
        template_texts = re.findall(r'`([^`]+)`', line)
        for tmpl in template_texts:
            # Extract text between > and </ in template literals
            tag_texts = re.findall(r'>([^<>${}\[\]]{3,})</', tmpl)
            for text in tag_texts:
                text = text.strip()
                if len(text) > 2 and is_portuguese_string(text):
                    findings.append({
                        'file': filepath,
                        'line': i,
                        'type': 'JS_TEMPLATE',
                        'text': text[:100],
                        'context': stripped[:150]
                    })

        # Pattern 5: alert('Portuguese text') or confirm('Portuguese text')
        alerts = re.findall(r'(?:alert|confirm)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', line)
        for text in alerts:
            if is_portuguese_string(text):
                findings.append({
                    'file': filepath,
                    'line': i,
                    'type': 'JS_ALERT',
                    'text': text[:100],
                    'context': stripped[:150]
                })

        # Pattern 6: showToast('Portuguese text', ...)
        toasts = re.findall(r'showToast\s*\(\s*[\'"]([^\'"]+)[\'"]\s*', line)
        for text in toasts:
            if is_portuguese_string(text):
                findings.append({
                    'file': filepath,
                    'line': i,
                    'type': 'JS_TOAST',
                    'text': text[:100],
                    'context': stripped[:150]
                })

    return findings


def scan_file(filepath):
    """Scan a file for hardcoded strings based on extension."""
    if not os.path.exists(filepath):
        print(f'  [WARN] File not found: {filepath}')
        return []

    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.html':
        return scan_html_hardcoded(filepath)
    elif ext == '.js':
        return scan_js_hardcoded(filepath)
    return []


# ========================================
# REPORT
# ========================================

def print_report(all_findings, verbose=False):
    """Print findings grouped by file and type."""
    print()
    print('=' * 60)
    print('Hardcoded String Scan Results')
    print('=' * 60)

    by_file = defaultdict(list)
    for f in all_findings:
        by_file[f['file']].append(f)

    for filepath, findings in sorted(by_file.items()):
        basename = os.path.relpath(filepath, PROJECT_ROOT)
        print(f'\n  {basename}: {len(findings)} hardcoded strings found')

        by_type = defaultdict(list)
        for f in findings:
            by_type[f['type']].append(f)

        for ftype, items in sorted(by_type.items()):
            print(f'    [{ftype}]: {len(items)}')
            if verbose:
                for item in items[:10]:
                    print(f'      Line {item["line"]}: "{item["text"]}"')
                if len(items) > 10:
                    print(f'      ... and {len(items) - 10} more')

    print(f'\n  Total: {len(all_findings)} hardcoded strings across {len(by_file)} files')


def export_csv(all_findings, output_path):
    """Export findings to CSV for review."""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['file', 'line', 'type', 'text', 'context'])
        writer.writeheader()
        writer.writerows(all_findings)
    print(f'  [CSV] Exported {len(all_findings)} findings to {output_path}')


# ========================================
# MAIN
# ========================================

def main():
    verbose = '--verbose' in sys.argv
    output_csv = None

    for i, arg in enumerate(sys.argv):
        if arg == '--output' and i + 1 < len(sys.argv):
            output_csv = sys.argv[i + 1]

    print('=' * 60)
    print('WatcherDB i18n Hardcoded String Scanner')
    print('=' * 60)

    all_findings = []

    for filepath in SCAN_FILES:
        if not os.path.exists(filepath):
            # Try glob
            import glob as g
            matches = g.glob(filepath)
            for match in matches:
                print(f'  Scanning: {os.path.relpath(match, PROJECT_ROOT)}')
                all_findings.extend(scan_file(match))
        else:
            print(f'  Scanning: {os.path.relpath(filepath, PROJECT_ROOT)}')
            all_findings.extend(scan_file(filepath))

    print_report(all_findings, verbose)

    if output_csv:
        export_csv(all_findings, output_csv)

    return 0


if __name__ == '__main__':
    sys.exit(main())
