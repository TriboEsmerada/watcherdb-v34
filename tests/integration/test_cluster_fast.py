#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste da versão FAST do cluster
"""

import sys
sys.path.insert(0, '.')

from modules.monitoring.cluster_analysis_fast import check_cluster_health_fast
import time

server = 'SQLADSPRD002'

print("=" * 70)
print("TESTE: Cluster FAST Mode")
print("=" * 70)

print(f"\nTestando check_cluster_health_fast('{server}')...")
start = time.time()
result = check_cluster_health_fast(server)
elapsed = time.time() - start

print(f"\nResultado:")
print(f"  Tempo: {elapsed:.2f}s")
print(f"  Success: {result.get('success')}")
print(f"  Cluster: {result.get('cluster_name')}")
print(f"  AG Resources: {len(result.get('ag_resources', []))}")
print(f"  Failed Resources: {len(result.get('failed_resources', []))}")
print(f"  Error: {result.get('error')}")
print(f"  Elapsed (internal): {result.get('elapsed_time'):.2f}s")

print("\n" + "=" * 70)
if result.get('success'):
    print(f"SUCCESS! Cluster info obtida em {elapsed:.2f}s")
else:
    print(f"FAILED: {result.get('error')}")
print("=" * 70)
