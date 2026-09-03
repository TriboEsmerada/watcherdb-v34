#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste direto da API de Cluster
"""

import sys
sys.path.insert(0, '.')

from modules.monitoring.cluster_analysis import check_cluster_health, get_cluster_summary
import time

# Testar com SQLADSPRD002
server = 'SQLADSPRD002'

print(f"[TEST] Testando cluster analysis para {server}...")
print("=" * 70)

# Teste 1: Health check direto
print(f"\n[1] Teste: check_cluster_health('{server}', timeout=10)")
start = time.time()
result = check_cluster_health(server, timeout=10)
elapsed = time.time() - start

print(f"   Tempo: {elapsed:.2f}s")
print(f"   Success: {result.get('success')}")
print(f"   Cluster: {result.get('cluster_name')}")
print(f"   Error: {result.get('error')}")

# Teste 2: Summary completo
print(f"\n[2] Teste: get_cluster_summary('{server}')")
start = time.time()
summary = get_cluster_summary(server)
elapsed = time.time() - start

print(f"   Tempo: {elapsed:.2f}s")
print(f"   Health Success: {summary.get('health', {}).get('success')}")
print(f"   Events Success: {summary.get('events', {}).get('success')}")

print("\n" + "=" * 70)
print("[OK] Teste concluido!")
