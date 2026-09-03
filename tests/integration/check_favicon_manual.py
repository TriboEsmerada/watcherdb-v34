#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Teste rápido para verificar se o favicon está acessível"""

import requests
import sys

try:
    # Testar se o servidor está rodando
    base_url = "http://127.0.0.1:8000"
    
    print("🔍 Testando rota do favicon...")
    print(f"URL: {base_url}/favicon.svg")
    
    response = requests.get(f"{base_url}/favicon.svg", timeout=5)
    
    print(f"Status Code: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    print(f"Content Length: {len(response.content)} bytes")
    
    if response.status_code == 200:
        print("✅ Favicon está acessível!")
        if response.headers.get('Content-Type') == 'image/svg+xml':
            print("✅ Content-Type correto!")
        else:
            print(f"⚠️  Content-Type: {response.headers.get('Content-Type')}")
    else:
        print(f"❌ Erro: Status {response.status_code}")
        print(f"Resposta: {response.text[:200]}")
        
except requests.exceptions.ConnectionError:
    print("❌ Erro: Servidor não está rodando!")
    print("   Execute: python watcherdb_main.py")
    sys.exit(1)
except Exception as e:
    print(f"❌ Erro: {e}")
    sys.exit(1)

