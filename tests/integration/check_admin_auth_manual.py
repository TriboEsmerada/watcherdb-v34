#!/usr/bin/env python3
"""
Script de teste para validar autenticação nos endpoints /api/admin/*

Testa:
1. Acesso sem autenticação (deve falhar com 401)
2. Acesso com token de VIEWER (deve falhar com 403)
3. Acesso com token de ADMIN (deve funcionar)
"""

import requests
import sys
from typing import Dict, Optional

# Configuração
BASE_URL = "http://localhost:8000"
ADMIN_USER = "admin"
ADMIN_PASS = "secret"
VIEWER_USER = "viewer"
VIEWER_PASS = "secret"


def get_auth_token(username: str, password: str) -> Optional[str]:
    """Obtem token JWT de autenticação"""
    response = requests.post(
        f"{BASE_URL}/api/auth/token",
        data={"username": username, "password": password}
    )

    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        print(f"Erro ao obter token: {response.status_code}")
        return None


def test_endpoint_without_auth(endpoint: str) -> bool:
    """Testa endpoint sem autenticação (deve retornar 401)"""
    response = requests.get(f"{BASE_URL}{endpoint}")

    if response.status_code == 401:
        print(f"OK {endpoint} - Bloqueado sem autenticação (401)")
        return True
    else:
        print(f"ERRO {endpoint} - ERRO: Deveria bloquear sem auth, mas retornou {response.status_code}")
        return False


def test_endpoint_with_token(endpoint: str, token: str, should_succeed: bool, role: str) -> bool:
    """Testa endpoint com token"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}{endpoint}", headers=headers)

    if should_succeed:
        if response.status_code == 200:
            print(f"OK {endpoint} - Acesso permitido para {role} (200)")
            return True
        else:
            print(f"ERRO {endpoint} - ERRO: {role} deveria ter acesso, mas retornou {response.status_code}")
            return False
    else:
        if response.status_code == 403:
            print(f"OK {endpoint} - Acesso negado para {role} (403)")
            return True
        else:
            print(f"ERRO {endpoint} - ERRO: {role} deveria ser bloqueado com 403, mas retornou {response.status_code}")
            return False


def main():
    print("=" * 80)
    print("TESTE DE AUTENTICAÇÃO - ENDPOINTS /api/admin/*")
    print("=" * 80)
    print()

    # Endpoints a testar
    admin_endpoints = [
        "/api/admin/metrics/endpoints/usage",
        "/api/admin/metrics/endpoints/unused",
        "/api/admin/metrics/endpoints/deprecated",
        "/api/admin/metrics/endpoints/performance",
        "/api/admin/metrics/endpoints/report",
    ]

    # Obter tokens
    print("1. Obtendo tokens de autenticação...")
    print("-" * 80)

    admin_token = get_auth_token(ADMIN_USER, ADMIN_PASS)
    if not admin_token:
        print("ERRO: Não foi possível obter token de ADMIN")
        sys.exit(1)
    print(f"OK Token ADMIN obtido")

    viewer_token = get_auth_token(VIEWER_USER, VIEWER_PASS)
    if not viewer_token:
        print("ERRO: Não foi possível obter token de VIEWER")
        sys.exit(1)
    print(f"OK Token VIEWER obtido")
    print()

    # Teste 1: Sem autenticação
    print("2. Testando acesso SEM autenticação (deve bloquear com 401)...")
    print("-" * 80)
    results_no_auth = []
    for endpoint in admin_endpoints:
        results_no_auth.append(test_endpoint_without_auth(endpoint))
    print()

    # Teste 2: Com token VIEWER (deve falhar com 403)
    print("3. Testando acesso com token VIEWER (deve bloquear com 403)...")
    print("-" * 80)
    results_viewer = []
    for endpoint in admin_endpoints:
        results_viewer.append(test_endpoint_with_token(endpoint, viewer_token, should_succeed=False, role="VIEWER"))
    print()

    # Teste 3: Com token ADMIN (deve funcionar com 200)
    print("4. Testando acesso com token ADMIN (deve permitir com 200)...")
    print("-" * 80)
    results_admin = []
    for endpoint in admin_endpoints:
        results_admin.append(test_endpoint_with_token(endpoint, admin_token, should_succeed=True, role="ADMIN"))
    print()

    # Resumo
    print("=" * 80)
    print("RESUMO DOS TESTES")
    print("=" * 80)

    total_tests = len(admin_endpoints) * 3
    passed_tests = sum(results_no_auth) + sum(results_viewer) + sum(results_admin)

    print(f"Total de testes: {total_tests}")
    print(f"Testes passados: {passed_tests}")
    print(f"Testes falhados: {total_tests - passed_tests}")
    print()

    if passed_tests == total_tests:
        print("OKOKOK TODOS OS TESTES PASSARAM! Autenticação funcionando corretamente.")
        return 0
    else:
        print("ERROERROERRO ALGUNS TESTES FALHARAM! Verifique a implementação.")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.exceptions.ConnectionError:
        print()
        print("ERRO: Não foi possível conectar ao servidor.")
        print(f"Verifique se o servidor está rodando em {BASE_URL}")
        print()
        print("Para iniciar o servidor:")
        print("  cd WATCHERDB_DEV")
        print("  python watcherdb_main.py")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nTeste interrompido pelo usuário")
        sys.exit(1)
