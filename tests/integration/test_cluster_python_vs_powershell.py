#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste de Performance: Python WMI vs PowerShell
"""

import sys
sys.path.insert(0, '.')

from modules.monitoring.cluster_analysis import check_cluster_health as powershell_check
from modules.monitoring.cluster_analysis_python import check_cluster_health_python as python_check
import time

server = 'SQLADSPRD002'

print("=" * 70)
print("TESTE: Python WMI vs PowerShell")
print("=" * 70)

# Teste 1: PowerShell (Plano A + B)
print("\n[1] PowerShell Plano A+B (timeout 15s)")
start = time.time()
result_ps = powershell_check(server, timeout=15)
elapsed_ps = time.time() - start

print(f"   Tempo: {elapsed_ps:.2f}s")
print(f"   Success: {result_ps.get('success')}")
print(f"   Plano: {result_ps.get('plan_used')}")
print(f"   Cluster: {result_ps.get('cluster_name')}")
print(f"   Nodes: {len(result_ps.get('nodes', []))}")
print(f"   Resources: {len(result_ps.get('resources', []))}")
print(f"   AG Resources: {len(result_ps.get('ag_resources', []))}")

# Teste 2: Python WMI (Plano A + B)
print("\n[2] Python WMI Plano A+B (timeout 10s)")
start = time.time()
result_py = python_check(server, timeout=10)
elapsed_py = time.time() - start

print(f"   Tempo: {elapsed_py:.2f}s")
print(f"   Success: {result_py.get('success')}")
print(f"   Plano: {result_py.get('plan_used')}")
print(f"   Cluster: {result_py.get('cluster_name')}")
print(f"   Nodes: {len(result_py.get('nodes', []))}")
print(f"   Resources: {len(result_py.get('resources', []))}")
print(f"   AG Resources: {len(result_py.get('ag_resources', []))}")

# Comparação
print("\n" + "=" * 70)
print("COMPARACAO")
print("=" * 70)
print(f"PowerShell: {elapsed_ps:.2f}s")
print(f"Python WMI: {elapsed_py:.2f}s")
print(f"Diferenca: {elapsed_ps - elapsed_py:.2f}s ({((elapsed_ps - elapsed_py) / elapsed_ps * 100):.1f}% mais rapido)")
print("=" * 70)

if elapsed_py < elapsed_ps:
    speedup = elapsed_ps / elapsed_py
    print(f"\nPython e {speedup:.1f}x mais rapido que PowerShell!")
else:
    print(f"\nPowerShell e mais rapido neste caso (incomum)")
