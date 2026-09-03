#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste COM/WMI direto para Cluster
"""

import win32com.client
import time

server = 'SQLADSPRD002'

print(f"Testando acesso COM ao cluster {server}...")

try:
    # Tentar via WMI COM
    print("\n[1] Tentando via WMI COM...")
    start = time.time()

    wmi_locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
    wmi_service = wmi_locator.ConnectServer(server, "root\\MSCluster")

    # Obter cluster
    clusters = wmi_service.ExecQuery("SELECT * FROM MSCluster_Cluster")
    for cluster in clusters:
        print(f"   Cluster: {cluster.Name}")
        print(f"   Domain: {cluster.Properties_('Domain').Value}")

    # Obter nodes
    nodes = wmi_service.ExecQuery("SELECT * FROM MSCluster_Node")
    print(f"   Nodes: {nodes.Count}")
    for node in nodes:
        print(f"     - {node.Name} (State: {node.State})")

    # Obter resources
    resources = wmi_service.ExecQuery("SELECT * FROM MSCluster_Resource")
    print(f"   Resources: {resources.Count}")

    elapsed = time.time() - start
    print(f"\n   SUCCESS em {elapsed:.2f}s!")

except Exception as e:
    print(f"   ERRO: {e}")

# Tentar via MSCluster COM Object
print("\n[2] Tentando via MSCluster COM Object...")
try:
    start = time.time()

    cluster_app = win32com.client.Dispatch("MSClusterLib.Cluster")
    cluster_app.Open(server)

    print(f"   Cluster: {cluster_app.Name}")
    print(f"   Nodes: {cluster_app.Nodes.Count}")

    for i in range(cluster_app.Nodes.Count):
        node = cluster_app.Nodes.Item(i + 1)  # COM collections are 1-indexed
        print(f"     - {node.Name} (State: {node.State})")

    print(f"   Resources: {cluster_app.Resources.Count}")

    elapsed = time.time() - start
    print(f"\n   SUCCESS em {elapsed:.2f}s!")

except Exception as e:
    print(f"   ERRO: {e}")

print("\nDone!")
