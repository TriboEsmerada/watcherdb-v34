#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste da coleta de eventos do cluster (modo FAST)
"""

import sys
sys.path.insert(0, '.')

from modules.monitoring.cluster_analysis_fast import get_cluster_events_fast, get_cluster_summary_fast
import time

server = 'SQLADSPRD002'

print("=" * 70)
print("TESTE: Coleta de Eventos do Cluster (FAST MODE)")
print("=" * 70)

# Teste 1: Apenas eventos
print(f"\n[1] Testando get_cluster_events_fast('{server}')...")
start = time.time()
events_result = get_cluster_events_fast(server, max_events=50)
elapsed = time.time() - start

print(f"\nResultado:")
print(f"  Tempo: {elapsed:.2f}s")
print(f"  Success: {events_result.get('success')}")
print(f"  Eventos encontrados: {len(events_result.get('events', []))}")
print(f"  Error: {events_result.get('error')}")

if events_result.get('success') and events_result.get('events'):
    print(f"\n  Primeiros 5 eventos:")
    for i, event in enumerate(events_result.get('events', [])[:5], 1):
        print(f"    {i}. [{event['level']}] ID {event['event_id']} - {event['timestamp']}")
        print(f"       {event['message'][:100]}...")

# Teste 2: Summary completo (health + events)
print(f"\n[2] Testando get_cluster_summary_fast('{server}')...")
start = time.time()
summary = get_cluster_summary_fast(server)
elapsed = time.time() - start

print(f"\nResultado:")
print(f"  Tempo total: {elapsed:.2f}s")
print(f"  Health Success: {summary.get('health', {}).get('success')}")
print(f"  Events Success: {summary.get('events', {}).get('success')}")
print(f"  Cluster Name: {summary.get('health', {}).get('cluster_name')}")
print(f"  AG Resources: {len(summary.get('health', {}).get('ag_resources', []))}")
print(f"  Eventos: {len(summary.get('events', {}).get('events', []))}")

print("\n" + "=" * 70)
if summary.get('events', {}).get('success'):
    print(f"✅ SUCCESS! Eventos do cluster obtidos em {elapsed:.2f}s")
else:
    print(f"⚠️ AVISO: {summary.get('events', {}).get('error')}")
print("=" * 70)
