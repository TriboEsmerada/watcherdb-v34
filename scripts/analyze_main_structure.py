#!/usr/bin/env python3
"""
Analyze watcherdb_main.py structure
Extract routes, HTML templates, functions, and classes
"""

import re
import json
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
MAIN_FILE = PROJECT_ROOT / "watcherdb_main.py"


def analyze_routes(content: str) -> list:
    """Extract all FastAPI routes"""
    route_pattern = r'@app\.(get|post|put|delete|websocket)\(["\']([^"\']+)["\']\)'
    matches = re.finditer(route_pattern, content)

    routes = []
    for match in matches:
        method = match.group(1).upper()
        path = match.group(2)
        line_num = content[:match.start()].count('\n') + 1
        routes.append({
            'method': method,
            'path': path,
            'line': line_num
        })

    return routes


def analyze_html_blocks(content: str) -> list:
    """Extract HTML template blocks"""
    html_blocks = []

    # Find HTMLResponse blocks
    html_pattern = r'HTMLResponse\(content=(?:"""|\'\'\')(.*?)(?:"""|\'\'\')(?:,|\))'
    matches = re.finditer(html_pattern, content, re.DOTALL)

    for match in matches:
        line_num = content[:match.start()].count('\n') + 1
        html_content = match.group(1)
        lines_count = html_content.count('\n')

        html_blocks.append({
            'start_line': line_num,
            'end_line': line_num + lines_count,
            'lines_count': lines_count,
            'preview': html_content[:100].replace('\n', ' ')
        })

    return html_blocks


def analyze_functions(content: str) -> list:
    """Extract function definitions"""
    func_pattern = r'^(?:async )?def ([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
    matches = re.finditer(func_pattern, content, re.MULTILINE)

    functions = []
    for match in matches:
        func_name = match.group(1)
        line_num = content[:match.start()].count('\n') + 1
        is_async = 'async' in match.group(0)

        functions.append({
            'name': func_name,
            'line': line_num,
            'is_async': is_async
        })

    return functions


def analyze_classes(content: str) -> list:
    """Extract class definitions"""
    class_pattern = r'^class ([a-zA-Z_][a-zA-Z0-9_]*)'
    matches = re.finditer(class_pattern, content, re.MULTILINE)

    classes = []
    for match in matches:
        class_name = match.group(1)
        line_num = content[:match.start()].count('\n') + 1

        classes.append({
            'name': class_name,
            'line': line_num
        })

    return classes


def categorize_routes(routes: list) -> dict:
    """Categorize routes by domain"""
    categories = defaultdict(list)

    for route in routes:
        path = route['path']

        if '/api/monitoring/space' in path:
            categories['space'].append(route)
        elif '/api/monitoring/memory' in path:
            categories['memory'].append(route)
        elif '/api/monitoring/cpu' in path:
            categories['cpu'].append(route)
        elif '/api/monitoring/backup' in path:
            categories['backup'].append(route)
        elif '/api/monitoring/alwayson' in path:
            categories['alwayson'].append(route)
        elif '/api/monitoring' in path:
            categories['monitoring'].append(route)
        elif '/api/queries' in path:
            categories['queries'].append(route)
        elif '/api/config' in path:
            categories['config'].append(route)
        elif '/api/v3' in path:
            categories['v3_api'].append(route)
        elif '/ws' in path:
            categories['websocket'].append(route)
        elif path == '/' or 'favicon' in path:
            categories['static'].append(route)
        else:
            categories['other'].append(route)

    return dict(categories)


def generate_report(content: str) -> dict:
    """Generate comprehensive analysis report"""
    lines = content.split('\n')
    total_lines = len(lines)

    # Basic stats
    imports_count = sum(1 for line in lines if line.strip().startswith('import ') or line.strip().startswith('from '))
    comments_count = sum(1 for line in lines if line.strip().startswith('#'))
    blank_lines = sum(1 for line in lines if not line.strip())
    code_lines = total_lines - blank_lines - comments_count

    # Extract components
    routes = analyze_routes(content)
    html_blocks = analyze_html_blocks(content)
    functions = analyze_functions(content)
    classes = analyze_classes(content)
    categorized_routes = categorize_routes(routes)

    # Calculate HTML lines
    html_lines_total = sum(block['lines_count'] for block in html_blocks)

    report = {
        'file': str(MAIN_FILE),
        'statistics': {
            'total_lines': total_lines,
            'code_lines': code_lines,
            'blank_lines': blank_lines,
            'comment_lines': comments_count,
            'import_lines': imports_count,
            'html_lines': html_lines_total,
            'pure_python_lines': code_lines - html_lines_total
        },
        'components': {
            'routes_count': len(routes),
            'html_blocks_count': len(html_blocks),
            'functions_count': len(functions),
            'classes_count': len(classes)
        },
        'routes': routes,
        'routes_by_category': {k: len(v) for k, v in categorized_routes.items()},
        'categorized_routes': categorized_routes,
        'html_blocks': html_blocks,
        'functions': functions[:50],  # First 50
        'classes': classes
    }

    return report


def print_report(report: dict):
    """Print formatted report"""
    print("=" * 80)
    print("WATCHERDB_MAIN.PY - STRUCTURE ANALYSIS")
    print("=" * 80)
    print()

    print("[STATISTICS]")
    print("-" * 80)
    stats = report['statistics']
    print(f"Total Lines:          {stats['total_lines']:,}")
    print(f"Code Lines:           {stats['code_lines']:,}")
    print(f"HTML Lines:           {stats['html_lines']:,} ({stats['html_lines']/stats['total_lines']*100:.1f}%)")
    print(f"Pure Python Lines:    {stats['pure_python_lines']:,} ({stats['pure_python_lines']/stats['total_lines']*100:.1f}%)")
    print(f"Blank Lines:          {stats['blank_lines']:,}")
    print(f"Comment Lines:        {stats['comment_lines']:,}")
    print(f"Import Lines:         {stats['import_lines']:,}")
    print()

    print("[COMPONENTS]")
    print("-" * 80)
    comp = report['components']
    print(f"API Routes:           {comp['routes_count']}")
    print(f"HTML Blocks:          {comp['html_blocks_count']}")
    print(f"Functions:            {comp['functions_count']}")
    print(f"Classes:              {comp['classes_count']}")
    print()

    print("[ROUTES BY CATEGORY]")
    print("-" * 80)
    for category, count in sorted(report['routes_by_category'].items(), key=lambda x: -x[1]):
        print(f"{category:20} {count:3} routes")
    print()

    print("[HTML BLOCKS - Largest]")
    print("-" * 80)
    html_blocks = sorted(report['html_blocks'], key=lambda x: -x['lines_count'])[:10]
    for i, block in enumerate(html_blocks, 1):
        print(f"{i:2}. Lines {block['start_line']:5}-{block['end_line']:5} ({block['lines_count']:4} lines)")
        print(f"    Preview: {block['preview'][:70]}...")
    print()

    print("[REFACTORING RECOMMENDATIONS]")
    print("-" * 80)

    html_lines = stats['html_lines']
    total_lines = stats['total_lines']

    if html_lines > 1000:
        print(f"[CRITICAL] {html_lines:,} lines of HTML ({html_lines/total_lines*100:.1f}%)")
        print("   -> Extract all HTML to Jinja2 templates")
        print(f"   -> Estimated reduction: {html_lines:,} lines")

    if comp['routes_count'] > 50:
        print(f"[WARNING] {comp['routes_count']} routes in single file")
        print("   -> Split routes into api/routers/ modules")
        print(f"   -> Recommended: {len(report['routes_by_category'])} separate router files")

    if comp['functions_count'] > 100:
        print(f"[WARNING] {comp['functions_count']} functions")
        print("   -> Extract business logic to watcherdb/services/")

    if comp['classes_count'] > 10:
        print(f"[INFO] {comp['classes_count']} classes defined")
        print("   -> Consider moving to watcherdb/models/ or watcherdb/core/")

    print()
    estimated_reduction = html_lines + (comp['routes_count'] * 15)
    final_lines = total_lines - estimated_reduction
    print(f"[ESTIMATED LINE REDUCTION]")
    print(f"   Current:  {total_lines:,} lines")
    print(f"   Target:   {final_lines:,} lines ({final_lines/total_lines*100:.1f}%)")
    print(f"   Reduction: {estimated_reduction:,} lines ({estimated_reduction/total_lines*100:.1f}%)")
    print()


def save_report(report: dict, output_file: Path):
    """Save report to JSON"""
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"[OK] Full report saved to: {output_file}")


def main():
    print("Analyzing watcherdb_main.py...\n")

    if not MAIN_FILE.exists():
        print(f"❌ File not found: {MAIN_FILE}")
        return

    content = MAIN_FILE.read_text(encoding='utf-8')
    report = generate_report(content)

    print_report(report)

    # Save detailed report
    output_file = PROJECT_ROOT / "logs" / "watcherdb_main_analysis.json"
    output_file.parent.mkdir(exist_ok=True)
    save_report(report, output_file)

    print()
    print("=" * 80)
    print("[NEXT STEPS]")
    print("=" * 80)
    print("1. Review report: logs/watcherdb_main_analysis.json")
    print("2. Start with Phase 4.1: Extract HTML templates")
    print("3. Continue with Phase 4.2: Extract routes")
    print("4. Complete with Phase 4.3: Extract business logic")
    print()


if __name__ == "__main__":
    main()
