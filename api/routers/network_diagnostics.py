#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Router para Diagnóstico de Rede / Conectividade SQL Server.

Testa conectividade entre o WatcherDB e instâncias SQL Server em múltiplas camadas:
  0. Basic Network (DNS externo para verificar se rede/VPN funciona)
  1. DNS Resolution (hostname corporativo)
  2. SQL Server Browser (descobrir porta real para instâncias nomeadas)
  3. TCP Port Connectivity (socket na porta correcta)
  4. ODBC Connection
  5. Simple Query (SELECT 1 + SELECT @@VERSION)
  6. Round-trip latency measurement (3x ping)
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Dict, Optional, Tuple
import logging
import time
import socket
import struct
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from api.error_helpers import safe_http_error
from api.models import NetworkDiagnosticsResponse, NetworkQuickTestResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagnostics", tags=["Network Diagnostics"])


def _load_server_config(server_id: str) -> Optional[Dict]:
    """Carrega config de um servidor a partir do servers.json LOCAL (precisa de
    credenciais para o teste de login -> ficheiro, nao BD). E6b: path via config_dir()
    (antes relativo ao CWD: quebrava como Windows Service)."""
    try:
        try:
            from watcherdb.core.paths import config_dir
            config_path = config_dir() / "servers.json"
        except Exception:
            config_path = Path("config/servers.json")
        if not config_path.exists():
            return None
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for srv in data.get('monitored_servers', []):
            if srv.get('id', '').upper() == server_id.upper():
                return srv
        return None
    except Exception:
        return None


def _query_sql_browser(ip_addr: str, instance_name: str, timeout: float = 15.0) -> Optional[int]:  # 3.0->15.0 (2026-07-28): VPN com latencia alta faz UDP 1434 parecer "nao respondeu" quando so esta lento; paridade com o fix do coletor V1 (parecer v1-intel). Call-site rapido (linha ~584) mantem timeout=2.0 explicito.
    """
    Consulta o SQL Server Browser Service (UDP 1434) para descobrir
    a porta TCP real de uma instância nomeada.

    Retorna a porta (int) ou None se não conseguir descobrir.
    """
    try:
        # Protocolo: enviar 0x04 para listar todas as instâncias
        # ou 0x03 + instance_name para consultar uma específica
        request = b'\x04'  # Request all instances

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(request, (ip_addr, 1434))

        data, _ = sock.recvfrom(4096)
        sock.close()

        if not data or len(data) < 3:
            return None

        # Resposta começa com 0x05 + tamanho (2 bytes LE) + dados
        response_text = data[3:].decode('ascii', errors='ignore')

        # Formato: "ServerName;HOSTNAME;InstanceName;INST01;IsClustered;No;Version;16.0.xxxx;tcp;PORT;;"
        # Pode ter múltiplas instâncias separadas por ";;"
        instances = response_text.split(';;')
        for inst_block in instances:
            parts = inst_block.split(';')
            # Procurar InstanceName=instance_name e tcp=PORT
            inst_idx = None
            tcp_idx = None
            for i, part in enumerate(parts):
                if part.lower() == 'instancename' and i + 1 < len(parts):
                    if parts[i + 1].upper() == instance_name.upper():
                        inst_idx = i
                if part.lower() == 'tcp' and i + 1 < len(parts):
                    tcp_idx = i + 1

            if inst_idx is not None and tcp_idx is not None:
                try:
                    return int(parts[tcp_idx])
                except (ValueError, IndexError):
                    pass

        return None
    except (socket.timeout, socket.error, Exception) as e:
        logger.debug(f"SQL Browser query failed for {ip_addr}\\{instance_name}: {e}")
        return None


def _classify_failure(tests: list) -> str:
    """
    Analisa os resultados dos testes e retorna uma causa provável.
    """
    status_map = {}
    for t in tests:
        status_map[t['name']] = t['status']

    # Se rede básica falhou
    if status_map.get('Basic Network') == 'FAIL':
        return 'Sem conectividade de rede - verifique VPN, WiFi ou cabo de rede'

    # Se DNS corporativo falhou mas rede básica OK
    if status_map.get('DNS Resolution') == 'FAIL':
        if status_map.get('Basic Network') == 'PASS':
            return 'Rede OK mas DNS corporativo falhou - verifique VPN ou DNS interno'
        return 'Sem conectividade de rede ou DNS - verifique VPN/WiFi/cabo'

    # Servidor offline: ICMP falhou (ou TCP+ODBC ambos falharam sem ICMP)
    icmp_status = status_map.get('ICMP Ping')
    tcp_status = status_map.get('TCP Port')
    odbc_status = status_map.get('ODBC Connection')
    browser_status = status_map.get('SQL Browser')

    if icmp_status == 'FAIL':
        return 'Servidor parece DESLIGADO ou inacessivel - nao responde a ping, TCP nem ODBC'

    # DNS OK, mas ping WARN (timeout) + TCP FAIL + ODBC FAIL = provavelmente offline
    if icmp_status == 'WARN' and tcp_status in ('FAIL', 'WARN') and odbc_status == 'FAIL':
        return 'Servidor provavelmente DESLIGADO ou bloqueado por firewall - ping sem resposta e todas as conexoes falharam'

    # Sem ICMP mas TCP + ODBC ambos FAIL = servidor inacessivel
    if tcp_status in ('FAIL', 'WARN') and odbc_status == 'FAIL' and browser_status in ('FAIL', 'WARN', None):
        return 'Servidor inacessivel - nenhuma porta SQL responde. Servidor pode estar desligado, firewall a bloquear, ou porta errada'

    # Se Browser falhou (instância nomeada)
    if browser_status == 'FAIL':
        return 'SQL Server Browser Service nao respondeu - servico pode estar parado ou porta UDP 1434 bloqueada'

    # Se TCP falhou
    if tcp_status == 'FAIL':
        return 'Host acessivel mas porta TCP bloqueada - verifique firewall ou se o SQL Server esta a correr'

    # Se ODBC falhou
    if odbc_status == 'FAIL':
        return 'Rede OK mas conexao ODBC falhou - verifique credenciais/autenticacao ou driver ODBC'

    # Se query falhou
    if status_map.get('Query SELECT 1') == 'FAIL':
        return 'Conexao OK mas queries falham - SQL Server pode estar sob pressao ou a recuperar'

    # Se latência é WARN
    if status_map.get('Latency Consistency (3x SELECT 1)') == 'WARN':
        return 'Conexao OK mas latencia elevada - verifique qualidade da rede (WiFi vs cabo)'

    return 'Todos os testes passaram'


def _run_network_test(server_id: str, port: int = 1433) -> Dict:
    """
    Executa bateria de testes de rede/conectividade.
    Retorna dict com resultados de cada etapa e tempos.
    """
    config = _load_server_config(server_id)
    if not config:
        return {
            'success': False,
            'server_id': server_id,
            'error': f'Servidor {server_id} não encontrado em servers.json'
        }

    host = config.get('host', '')
    instance = config.get('instance', '')
    srv_port = config.get('port', port)
    use_windows_auth = config.get('use_windows_auth', True)
    username = config.get('username', '')
    password = config.get('password', '')
    is_named_instance = bool(instance)

    server_full = f"{host}\\{instance}" if instance else host
    results = {
        'success': True,
        'server_id': server_id,
        'server_name': server_full,
        'host': host,
        'instance': instance or 'DEFAULT',
        'port': srv_port,
        'named_instance': is_named_instance,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'tests': [],
        'total_time_ms': 0,
        'summary': 'OK',
        'probable_cause': ''
    }

    overall_start = time.perf_counter()
    failed = False
    ip_addr = None

    # ── TEST 0: Basic Network Connectivity ──
    test0 = {'name': 'Basic Network', 'status': 'PASS', 'time_ms': 0, 'detail': ''}
    t0 = time.perf_counter()
    try:
        # Tentar resolver um DNS bem conhecido para verificar se a rede funciona
        socket.gethostbyname('dns.google')
        test0['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        test0['detail'] = f'Rede OK (DNS externo acessível em {test0["time_ms"]}ms)'
    except socket.gaierror:
        # Tentar alternativa - resolver o próprio hostname local
        try:
            socket.gethostbyname(socket.gethostname())
            test0['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
            test0['status'] = 'WARN'
            test0['detail'] = 'DNS externo inacessível, mas rede local OK'
        except Exception:
            test0['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
            test0['status'] = 'FAIL'
            test0['detail'] = 'Sem conectividade de rede - verifique VPN/WiFi/cabo'
            failed = True
    results['tests'].append(test0)

    if failed:
        results['success'] = False
        results['probable_cause'] = _classify_failure(results['tests'])
        results['summary'] = f'FAIL - {results["probable_cause"]}'
        results['total_time_ms'] = round((time.perf_counter() - overall_start) * 1000, 2)
        return results

    # ── TEST 1: DNS Resolution (hostname corporativo) ──
    test1 = {'name': 'DNS Resolution', 'status': 'PASS', 'time_ms': 0, 'detail': ''}
    t0 = time.perf_counter()
    try:
        ip_addr = socket.gethostbyname(host)
        test1['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        test1['detail'] = f'{host} → {ip_addr}'
    except socket.gaierror as e:
        test1['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        test1['status'] = 'FAIL'
        test1['detail'] = f'Não foi possível resolver {host}: {e}'
        failed = True
    results['tests'].append(test1)

    if failed:
        results['success'] = False
        results['probable_cause'] = _classify_failure(results['tests'])
        results['summary'] = f'FAIL - {results["probable_cause"]}'
        results['total_time_ms'] = round((time.perf_counter() - overall_start) * 1000, 2)
        return results

    # ── TEST 1.5: ICMP Ping (verificar se host responde) ──
    test_icmp = {'name': 'ICMP Ping', 'status': 'PASS', 'time_ms': 0, 'detail': ''}
    t0 = time.perf_counter()
    try:
        import subprocess
        # Windows: ping -n 1 -w 2000 (1 pacote, timeout 2s)
        ping_result = subprocess.run(
            ['ping', '-n', '1', '-w', '2000', ip_addr],
            capture_output=True, text=True, timeout=5
        )
        test_icmp['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        if ping_result.returncode == 0:
            # Extrair tempo do ping da saida
            import re
            time_match = re.search(r'tempo[=<](\d+)ms|time[=<](\d+)ms', ping_result.stdout, re.IGNORECASE)
            ping_ms = time_match.group(1) or time_match.group(2) if time_match else '?'
            test_icmp['detail'] = f'{ip_addr} responde a ping ({ping_ms}ms)'
        else:
            test_icmp['status'] = 'WARN'
            test_icmp['detail'] = (
                f'{ip_addr} nao responde a ping (ICMP bloqueado ou servidor desligado). '
                f'Nota: alguns servidores bloqueiam ICMP por politica de seguranca.'
            )
    except subprocess.TimeoutExpired:
        test_icmp['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        test_icmp['status'] = 'WARN'
        test_icmp['detail'] = f'{ip_addr} nao responde a ping (timeout). Servidor pode estar desligado.'
    except Exception as e:
        test_icmp['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        test_icmp['status'] = 'WARN'
        test_icmp['detail'] = f'Teste ICMP falhou: {str(e)[:100]}'
    results['tests'].append(test_icmp)

    # ── TEST 2: SQL Server Browser (para instâncias nomeadas) ──
    browser_port = None
    if is_named_instance:
        test_browser = {'name': 'SQL Browser', 'status': 'PASS', 'time_ms': 0, 'detail': ''}
        t0 = time.perf_counter()
        browser_port = _query_sql_browser(ip_addr, instance)
        test_browser['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)

        if browser_port:
            test_browser['detail'] = f'Instância {instance} → porta TCP {browser_port} (Browser Service UDP 1434)'
            # Actualizar a porta nos resultados
            srv_port = browser_port
            results['port'] = srv_port
            results['port_source'] = 'SQL Server Browser'
        else:
            test_browser['status'] = 'WARN'
            test_browser['detail'] = (
                f'Browser Service não respondeu para {instance} (UDP 1434). '
                f'A usar porta config: {srv_port}. '
                f'Nota: instâncias nomeadas usam portas dinâmicas.'
            )
            results['port_source'] = 'config (fallback)'
        results['tests'].append(test_browser)
    else:
        results['port_source'] = 'default (1433)'

    # ── TEST 3: TCP Port Connectivity ──
    test2 = {'name': 'TCP Port', 'status': 'PASS', 'time_ms': 0, 'detail': ''}
    t0 = time.perf_counter()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((ip_addr, srv_port))
        test2['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        sock.close()
        if result == 0:
            port_info = f' (via Browser)' if browser_port else ''
            test2['detail'] = f'{ip_addr}:{srv_port} acessível{port_info}'
        else:
            test2['status'] = 'FAIL'
            if is_named_instance and not browser_port:
                test2['detail'] = (
                    f'{ip_addr}:{srv_port} inacessível (code={result}). '
                    f'Instância nomeada {instance} pode usar porta dinâmica diferente de {srv_port}.'
                )
            else:
                test2['detail'] = f'{ip_addr}:{srv_port} inacessível (code={result})'
            failed = True
    except Exception as e:
        test2['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        test2['status'] = 'FAIL'
        test2['detail'] = f'Erro TCP: {e}'
        failed = True
    results['tests'].append(test2)

    if failed:
        # Para instâncias nomeadas sem Browser, não bloquear - tentar ODBC que resolve automaticamente
        if is_named_instance and not browser_port:
            test2['status'] = 'WARN'
            test2['detail'] += ' → A tentar via ODBC (resolve porta automaticamente)'
            failed = False
        else:
            results['success'] = False
            results['probable_cause'] = _classify_failure(results['tests'])
            results['summary'] = f'FAIL - {results["probable_cause"]}'
            results['total_time_ms'] = round((time.perf_counter() - overall_start) * 1000, 2)
            return results

    # ── TEST 4: ODBC Connection ──
    test3 = {'name': 'ODBC Connection', 'status': 'PASS', 'time_ms': 0, 'detail': ''}
    t0 = time.perf_counter()
    conn = None
    try:
        import pyodbc
        if use_windows_auth:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server_full};"
                f"DATABASE=master;"
                f"Trusted_Connection=yes;"
                f"TrustServerCertificate=yes;"
                f"Connection Timeout=10;"
            )
        else:
            # Desencriptar password se necessário
            pwd = password
            if isinstance(pwd, str) and pwd.startswith('encrypted:'):
                try:
                    import os as _os
                    from cryptography.fernet import Fernet as _Fernet
                    _enc_key = _os.environ.get('WATCHERDB_ENCRYPTION_KEY', '')
                    if _enc_key:
                        _f = _Fernet(_enc_key.encode())
                        pwd = _f.decrypt(pwd[len('encrypted:'):].encode()).decode()
                    else:
                        pwd = pwd[len('encrypted:'):]
                except Exception:
                    pwd = pwd[len('encrypted:'):]
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server_full};"
                f"DATABASE=master;"
                f"UID={username};"
                f"PWD={pwd};"
                f"TrustServerCertificate=yes;"
                f"Connection Timeout=10;"
            )
        conn = pyodbc.connect(conn_str, timeout=10)
        test3['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        test3['detail'] = f'Conexão ODBC estabelecida em {test3["time_ms"]}ms'
    except Exception as e:
        test3['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        test3['status'] = 'FAIL'
        test3['detail'] = f'Erro ODBC: {str(e)[:200]}'
        failed = True
    results['tests'].append(test3)

    if failed:
        results['success'] = False
        results['probable_cause'] = _classify_failure(results['tests'])
        results['summary'] = f'FAIL - {results["probable_cause"]}'
        results['total_time_ms'] = round((time.perf_counter() - overall_start) * 1000, 2)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return results

    # ── TEST 5: Simple Query (SELECT 1) ──
    test4 = {'name': 'Query SELECT 1', 'status': 'PASS', 'time_ms': 0, 'detail': ''}
    t0 = time.perf_counter()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        test4['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        test4['detail'] = f'Resultado: {row[0]} ({test4["time_ms"]}ms)'
        cursor.close()
    except Exception as e:
        test4['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        test4['status'] = 'FAIL'
        test4['detail'] = f'Erro query: {str(e)[:200]}'
        failed = True
    results['tests'].append(test4)

    # ── TEST 6: Server Info + Latency (@@VERSION, @@SERVERNAME, response time) ──
    test5 = {'name': 'Server Info & Latency', 'status': 'PASS', 'time_ms': 0, 'detail': ''}
    t0 = time.perf_counter()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                @@SERVERNAME AS server_name,
                SUBSTRING(@@VERSION, 1, 80) AS version_short,
                (SELECT COUNT(*) FROM sys.databases WHERE state_desc = 'ONLINE') AS online_dbs
        """)
        row = cursor.fetchone()
        test5['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        if row:
            test5['detail'] = f'{row[0]} | {row[1].strip()} | {row[2]} DBs online'
            results['server_info'] = {
                'server_name': row[0],
                'version': row[1].strip(),
                'online_databases': row[2]
            }
        cursor.close()
    except Exception as e:
        test5['time_ms'] = round((time.perf_counter() - t0) * 1000, 2)
        test5['status'] = 'WARN'
        test5['detail'] = f'Info parcial: {str(e)[:200]}'
    results['tests'].append(test5)

    # ── TEST 7: Multi-ping (3 execuções de SELECT 1 para medir jitter) ──
    test6 = {'name': 'Latency Consistency (3x SELECT 1)', 'status': 'PASS', 'time_ms': 0, 'detail': ''}
    pings = []
    try:
        cursor = conn.cursor()
        for _ in range(3):
            t0 = time.perf_counter()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            pings.append(round((time.perf_counter() - t0) * 1000, 2))
        cursor.close()

        avg_ping = round(sum(pings) / len(pings), 2)
        max_ping = max(pings)
        min_ping = min(pings)
        jitter = round(max_ping - min_ping, 2)

        test6['time_ms'] = avg_ping
        test6['detail'] = f'Avg: {avg_ping}ms | Min: {min_ping}ms | Max: {max_ping}ms | Jitter: {jitter}ms'
        results['latency'] = {
            'avg_ms': avg_ping,
            'min_ms': min_ping,
            'max_ms': max_ping,
            'jitter_ms': jitter,
            'pings': pings
        }

        # Classificar latência
        if avg_ping > 500:
            test6['status'] = 'WARN'
            test6['detail'] += ' ⚠ Latência alta'
        elif jitter > 200:
            test6['status'] = 'WARN'
            test6['detail'] += ' ⚠ Jitter elevado'
    except Exception as e:
        test6['time_ms'] = 0
        test6['status'] = 'WARN'
        test6['detail'] = f'Ping parcial: {str(e)[:100]}'
    results['tests'].append(test6)

    # Cleanup
    try:
        conn.close()
    except Exception:
        pass

    results['total_time_ms'] = round((time.perf_counter() - overall_start) * 1000, 2)

    # Summary com causa provável
    fails = sum(1 for t in results['tests'] if t['status'] == 'FAIL')
    warns = sum(1 for t in results['tests'] if t['status'] == 'WARN')
    results['probable_cause'] = _classify_failure(results['tests'])
    if fails > 0:
        results['success'] = False
        results['summary'] = f'FAIL - {results["probable_cause"]}'
    elif warns > 0:
        results['summary'] = f'WARN - {warns} alerta(s)'
    else:
        results['summary'] = f'OK - Todos os testes passaram ({results["total_time_ms"]}ms total)'

    return results


@router.get("/network-test/{server_id}", response_model=NetworkDiagnosticsResponse)
async def network_test(
    server_id: str,
    port: int = Query(1433, description="Porta TCP a testar"),
    timeout: int = Query(30, description="Timeout global em segundos (max 60)")
):
    """
    Diagnóstico completo de rede/conectividade a um SQL Server.

    Testa: DNS → TCP Port → ODBC → Query → Latência.
    Retorna resultados detalhados de cada camada com tempos.
    """
    if timeout > 60:
        timeout = 60

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_network_test, server_id, port)
            result = future.result(timeout=timeout)
        return JSONResponse(content=result)
    except FuturesTimeoutError:
        return JSONResponse(
            status_code=504,
            content={
                'success': False,
                'server_id': server_id,
                'error': f'Diagnóstico excedeu timeout de {timeout}s',
                'summary': f'TIMEOUT - O teste não completou em {timeout}s'
            }
        )
    except Exception as e:
        logger.error(f"Erro no diagnóstico de rede para {server_id}: {e}")
        raise safe_http_error(500, e, "running network diagnostics")


@router.get("/network-test-quick/{server_id}", response_model=NetworkQuickTestResponse)
async def network_test_quick(server_id: str):
    """
    Teste rápido de conectividade (apenas DNS + TCP).
    Para instâncias nomeadas, consulta o SQL Server Browser para a porta correcta.
    """
    config = _load_server_config(server_id)
    if not config:
        return JSONResponse(content={
            'success': False,
            'server_id': server_id,
            'reachable': False,
            'error': f'Servidor {server_id} não encontrado'
        })

    host = config.get('host', '')
    instance = config.get('instance', '')
    srv_port = config.get('port', 1433)
    server_full = f"{host}\\{instance}" if instance else host
    port_source = 'config'

    # Quick TCP test
    t0 = time.perf_counter()
    try:
        ip_addr = socket.gethostbyname(host)

        # Para instâncias nomeadas, tentar descobrir a porta real via Browser
        if instance:
            browser_port = _query_sql_browser(ip_addr, instance, timeout=2.0)
            if browser_port:
                srv_port = browser_port
                port_source = 'SQL Browser'

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((ip_addr, srv_port))
        sock.close()
        tcp_ok = result == 0
        tcp_ms = round((time.perf_counter() - t0) * 1000, 2)
    except Exception:
        tcp_ok = False
        tcp_ms = round((time.perf_counter() - t0) * 1000, 2)

    return JSONResponse(content={
        'success': True,
        'server_id': server_id,
        'server_name': server_full,
        'reachable': tcp_ok,
        'tcp_time_ms': tcp_ms,
        'port': srv_port,
        'port_source': port_source
    })
