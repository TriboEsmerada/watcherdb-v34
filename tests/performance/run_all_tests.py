"""
Master Runner - Executa todos os cenarios de performance em sequencia.
=====================================================================

Uso:
    python run_all_tests.py                    # todos os cenarios
    python run_all_tests.py --scenario baseline  # apenas baseline
    python run_all_tests.py --host http://server:8445  # servidor remoto

Requisitos:
    pip install locust psutil

Relatorio gerado em: ./reports/perf_report_YYYYMMDD_HHMMSS/
"""

import subprocess
import sys
import os
import time
import argparse
from datetime import datetime
from pathlib import Path


# Directorio base
BASE_DIR = Path(__file__).parent
REPORTS_DIR = BASE_DIR / "reports"


SCENARIOS = {
    "baseline": {
        "file": "locustfile_baseline.py",
        "users": 1,
        "spawn_rate": 1,
        "duration": "2m",
        "description": "Baseline - latencia individual de cada endpoint",
    },
    "concurrent": {
        "file": "locustfile_concurrent.py",
        "users": 10,
        "spawn_rate": 2,
        "duration": "5m",
        "description": "Carga concorrente - 10 users com refresh 30s",
    },
    "stress": {
        "file": "locustfile_stress.py",
        "users": 10,
        "spawn_rate": 5,
        "duration": "3m",
        "description": "Stress - bcrypt, pool, preferences storm",
    },
    "exhaustion": {
        "file": "locustfile_resource_exhaustion.py",
        "users": 5,
        "spawn_rate": 1,
        "duration": "15m",
        "description": "Resource exhaustion - memory leak, JWT revogacao",
    },
}


def run_scenario(name, config, host, report_dir):
    """Executa um cenario Locust e grava relatorio."""
    print(f"\n{'='*70}")
    print(f"SCENARIO: {name}")
    print(f"  {config['description']}")
    print(f"  Users: {config['users']}, Duration: {config['duration']}")
    print(f"{'='*70}")

    locustfile = str(BASE_DIR / config["file"])
    csv_prefix = str(report_dir / name)
    html_report = str(report_dir / f"{name}_report.html")

    cmd = [
        sys.executable, "-m", "locust",
        "-f", locustfile,
        "--headless",
        "-u", str(config["users"]),
        "-r", str(config["spawn_rate"]),
        "--run-time", config["duration"],
        "--host", host,
        "--csv", csv_prefix,
        "--html", html_report,
    ]

    print(f"  CMD: {' '.join(cmd)}")
    print()

    start = time.time()
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    elapsed = time.time() - start

    status = "PASS" if result.returncode == 0 else "FAIL"
    print(f"\n  Result: {status} (exit code {result.returncode}, {elapsed:.0f}s)")

    return {
        "name": name,
        "status": status,
        "exit_code": result.returncode,
        "duration_s": elapsed,
    }


def main():
    parser = argparse.ArgumentParser(description="WatcherDB V3.1 Performance Test Runner")
    parser.add_argument("--host", default="http://localhost:8000",
                        help="Base URL do WatcherDB (default: http://localhost:8000)")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()),
                        help="Executar apenas um cenario especifico")
    parser.add_argument("--list", action="store_true",
                        help="Listar cenarios disponiveis")
    args = parser.parse_args()

    if args.list:
        print("Cenarios disponiveis:")
        for name, cfg in SCENARIOS.items():
            print(f"  {name:15s} - {cfg['description']} (u={cfg['users']}, t={cfg['duration']})")
        return

    # Criar directorio de relatorio
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = REPORTS_DIR / f"perf_report_{timestamp}"
    report_dir.mkdir(parents=True, exist_ok=True)
    print(f"Reports directory: {report_dir}")

    # Executar cenarios
    scenarios_to_run = {args.scenario: SCENARIOS[args.scenario]} if args.scenario else SCENARIOS
    results = []

    for name, config in scenarios_to_run.items():
        result = run_scenario(name, config, args.host, report_dir)
        results.append(result)

    # Sumario final
    print(f"\n{'='*70}")
    print("FINAL SUMMARY")
    print(f"{'='*70}")
    for r in results:
        print(f"  {r['status']:4s}  {r['name']:15s}  ({r['duration_s']:.0f}s)")

    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    print(f"\n  {passed}/{total} scenarios passed")
    print(f"  Reports: {report_dir}")

    # Monitorizar recursos do processo (se psutil disponivel)
    try:
        import psutil
        print(f"\n  System resources:")
        print(f"    CPU usage: {psutil.cpu_percent(interval=1):.1f}%")
        print(f"    Memory available: {psutil.virtual_memory().available / 1024**3:.1f} GB")
    except ImportError:
        pass

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
