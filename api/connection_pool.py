#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Connection Pool Global - Pool de conexões centralizado para todas as APIs

Este módulo fornece pools de conexões reutilizáveis para:
1. Servidores SQL monitorados (dinâmico, múltiplos servidores)
2. WatcherDB Intelligence (banco de metadados, servidor fixo)

Benefícios:
- Reutilização de conexões entre requisições
- Redução do overhead de autenticação Windows
- Melhor performance em requisições paralelas
"""

import pyodbc
import threading
import time
import logging
import os
import re
import socket
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from pybreaker import CircuitBreakerError

from watcherdb.core.settings import settings
from watcherdb.core.retry import retry_db_operation
from watcherdb.core.circuit_breaker import sql_server_breaker, intelligence_breaker

logger = logging.getLogger(__name__)

# ============================================
# RESOLUCAO IPv4 DIRECTA (Wave Resiliencia de Rede — fase B, 2026-07-28)
# ============================================
# Incidente 2026-07-28: getaddrinfo() IPv6-first do OS PENDURA na resolucao
# por nome (VPN sem rota IPv6) — ping/pyodbc por nome travam, apesar de
# DNS-A + ping por IPv4 responderem em ~20ms. Fase B (gate v1-intel
# GO-com-condicoes): para instancias DEFAULT (porta 1433), resolver o nome
# para IPv4 com timeout PROPRIO e ligar por SERVER=ip,1433 + ServerSPN
# (preserva Kerberos — validar auth_scheme apos deploy, condicao 5 do gate).
# Instancias nomeadas ficam no comportamento atual (precisam do
# port-discovery da wave completa). FAIL-OPEN: qualquer falha na resolucao
# mantem o comportamento de hoje (host cru, OS resolve).
#
# ROLLBACK (1 linha): IPV4_DIRECT_DEFAULT_INSTANCES = False
IPV4_DIRECT_DEFAULT_INSTANCES = True
IPV4_RESOLVE_TIMEOUT = 2.0          # s — resolucao nunca bloqueia mais que isto
IPV4_CACHE_TTL = 300.0              # s — cache positiva (IP muda raramente)
IPV4_NEG_CACHE_TTL = 60.0           # s — cache negativa (nao re-pagar 2s por connect)

# Wave A (2026-07-28) — consumo da porta/IP aprendidos pelo collector V1.
# Fecha o buraco que a fase B deixou aberto: instancias NOMEADAS dependiam do
# SQL Browser (UDP 1434), que a VPN bloqueia — daí o ODBC Named Pipes 233.
# Com a porta em BD ligamos direto a ip,porta e o Browser deixa de importar.
# ROLLBACK (1 linha): NET_CACHE_ENABLED = False -> volta ao comportamento fase B.
NET_CACHE_ENABLED = True
NET_CACHE_TTL = 300.0               # s — 5 min (a porta so muda em restart/reconfig)

# Threads DAEMON com cap por semaforo (condicao 9 do gate, endurecida apos
# smoke test 2026-07-28): getaddrinfo() nao aceita timeout nativo. Um
# ThreadPoolExecutor seria errado aqui — threads nao-daemon presas no syscall
# (o smoke test provou o hang) bloqueiam o STOP do servico no exit-join e
# esgotam o pool (4 hangs = resolvedor morto). Daemon thread orfa nao impede
# shutdown; o semaforo (non-blocking) limita in-flight — sem slot = fail-open
# imediato, nunca fila.
_ipv4_inflight = threading.Semaphore(4)
_ipv4_cache: Dict[str, tuple] = {}   # host_upper -> (expires_ts, ip_or_None, fqdn_or_None)
_ipv4_cache_lock = threading.Lock()
_IP_LITERAL_RE = re.compile(r'^\d{1,3}(\.\d{1,3}){3}$')


def resolve_ipv4_cached(host: str, timeout: float = IPV4_RESOLVE_TIMEOUT) -> Tuple[Optional[str], Optional[str]]:
    """Resolve host -> (ipv4, fqdn) com timeout proprio e cache TTL.

    FQDN via AI_CANONNAME — vem na MESMA resposta A do DNS (zero lookups
    extra). NUNCA usar socket.getfqdn(): faz reverse-DNS (PTR) que pendura
    no mesmo resolver partido (provado no smoke test 2026-07-28). Fail-open:
    (None, None) em timeout/erro — caller mantem o comportamento atual.
    """
    key = host.upper()
    now = time.time()
    with _ipv4_cache_lock:
        hit = _ipv4_cache.get(key)
        if hit and hit[0] > now:
            return hit[1], hit[2]

    if not _ipv4_inflight.acquire(blocking=False):
        # 4 resolucoes ja presas/em curso -> nao empilhar; fail-open ja
        logger.debug(f"resolve_ipv4({host}): sem slot (flap sustentado?) — fail-open")
        return None, None

    result: list = []

    def _do_resolve():
        try:
            infos = socket.getaddrinfo(
                host, None, family=socket.AF_INET, flags=socket.AI_CANONNAME)
            ip = infos[0][4][0]
            canon = infos[0][3] or ''   # canonical name da resposta A (FQDN)
            result.append((ip, canon if '.' in canon else None))
        except Exception as e:
            result.append(e)
        finally:
            _ipv4_inflight.release()

    t = threading.Thread(target=_do_resolve, daemon=True, name=f"ipv4resolve-{key[:16]}")
    t.start()
    t.join(timeout)

    if result and isinstance(result[0], tuple):
        ip, fqdn = result[0]
        with _ipv4_cache_lock:
            _ipv4_cache[key] = (now + IPV4_CACHE_TTL, ip, fqdn)
        return ip, fqdn

    # timeout (thread daemon fica orfa, morre com o processo) ou erro DNS
    err = result[0] if result else 'timeout'
    logger.debug(f"resolve_ipv4({host}) falhou (fail-open): {err}")
    with _ipv4_cache_lock:
        _ipv4_cache[key] = (now + IPV4_NEG_CACHE_TTL, None, None)
    return None, None

# ============================================
# CONFIGURAÇÃO DO POOL
# ============================================
POOL_MAX_CONNECTIONS = 20
POOL_MAX_WORKERS = 8
# Fix 2026-07-15: 300s (5 min) esfriava o pool entre visitas a uma instância
# — reabrir o Overview >5 min depois pagava handshake completo outra vez.
# 1800s mantém quente por 30 min; conexões mortas não escapam (validação
# SELECT 1 no checkout e no return descarta-as).
POOL_CONNECTION_LIFETIME = 1800  # 30 minutos
POOL_CLEANUP_INTERVAL = 60  # 1 minuto

# ============================================
# POOL PARA SERVIDORES SQL MONITORADOS
# ============================================

class SQLServerConnectionPool:
    """
    Pool de conexões para múltiplos servidores SQL monitorados.
    Thread-safe e com limpeza automática de conexões antigas.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.pools: Dict[str, List[tuple]] = defaultdict(list)
        # FIX P0-2: Usar dict normal + lock global para evitar race condition
        # defaultdict(threading.Lock) tem race condition quando duas threads
        # acessam uma chave nova simultaneamente - podem criar locks diferentes
        self._locks_dict: Dict[str, threading.Lock] = {}
        self._locks_meta_lock = threading.Lock()  # Protege acesso ao _locks_dict
        self.active_connections: Dict[str, int] = defaultdict(int)
        self.max_connections = POOL_MAX_CONNECTIONS
        self.connection_lifetime = POOL_CONNECTION_LIFETIME

        # PER-SERVER FAILURE CACHE (quarantine)
        # ------------------------------------------------------------------
        # Quando um servidor falha a conectar, fica "em quarentena" por
        # OFFLINE_QUARANTINE_SECONDS. Tentativas subsequentes a esse server_id
        # devolvem None imediatamente sem chamar pyodbc.connect, eliminando
        # ate 7s de retries inuteis (1+2+4) por servidor offline x N requests
        # paralelos.
        #
        # O circuit breaker global (sql_server_breaker) NAO resolve isto
        # porque so abre apos 5 falhas consecutivas e e' partilhado entre TODOS
        # os servidores — uma chamada a um servidor saudavel reset-a o counter.
        self._offline_until: Dict[str, float] = {}  # pool_key -> unix_ts ate quando esta offline
        self._offline_lock = threading.Lock()
        self.OFFLINE_QUARANTINE_SECONDS = 60.0  # 1 minuto

        # PER-SERVER CREDENTIALS CACHE
        # ------------------------------------------------------------------
        # Mapeia server_id -> dict com credenciais resolvidas do servers.json
        # (use_windows_auth, username, password_decrypted, port). Carregado
        # lazy on first use, recarregado quando o ficheiro muda.
        # Antes deste cache, _build_connection_string usava Trusted_Connection=yes
        # hardcoded, ignorando os servidores que precisam de SQL Auth (como
        # SQLADSPRD003 que usa sql_monitoring) — esses ficavam impossiveis de
        # contactar e o overview falhava com 504.
        self._creds_cache: Dict[str, dict] = {}
        self._creds_cache_lock = threading.Lock()
        self._creds_cache_loaded_at: float = 0.0
        self._creds_cache_path = "config/servers.json"

        # FASE 1 least-privilege (2026-08-21): gate de rollout do SQL Auth.
        # A flag use_windows_auth JA' esta a False em TODAS as 63 entradas do
        # servers.json, mas os GRANTs least-priv (LEAST_PRIVILEGE_SETUP.sql) ainda
        # NAO estao aplicados a' conta sql_monitoring na frota. Se o branch de auth
        # confiasse so' nessa flag, o proximo restart mudava os 63 servidores para
        # SQL Auth de uma vez e o monitoring apagava-se onde os grants faltam. Por
        # isso um gate SEPARADO, explicito e default-VAZIO: um server_id so' liga
        # por SQL Auth se estiver nesta allowlist. Deploy do codigo com allowlist
        # vazia = zero mudanca de comportamento (todos continuam Trusted).
        # Ordem OBRIGATORIA por servidor: grants -> validar -> adicionar aqui.
        self._sql_auth_rollout: set = set()
        self._sql_auth_rollout_lock = threading.Lock()
        self._sql_auth_rollout_loaded_at: float = 0.0
        self._sql_auth_rollout_path = "config/sql_auth_rollout.json"

        # Wave A (2026-07-28): porta TCP + IPv4 APRENDIDOS pelo collector V1 e
        # guardados na BD partilhada. Carregados EM BLOCO com TTL -- nunca uma
        # query por ligacao (isso poria a BD no caminho critico de cada connect,
        # exatamente onde ja doi quando a rede esta ma).
        self._net_cache: Dict[str, dict] = {'ports': {}, 'ips': {}}
        self._net_cache_lock = threading.Lock()
        self._net_cache_loaded_at: float = 0.0

        self.stats = {
            'total_connections': 0,
            'active_connections': 0,
            'pool_hits': 0,
            'pool_misses': 0,
            'connection_errors': 0,
            'queries_executed': 0,
            'fast_fail_offline': 0,  # quantas vezes saimos rapido por quarentena
        }

        # Thread de limpeza
        self._cleanup_running = True
        self._cleanup_thread = threading.Thread(target=self._cleanup_old_connections, daemon=True)
        self._cleanup_thread.start()

        self._initialized = True
        logger.info(f"SQLServerConnectionPool initialized (max_connections={self.max_connections})")

    def _get_pool_lock(self, pool_key: str) -> threading.Lock:
        """
        Obtém lock para um pool_key de forma thread-safe.
        Cria novo lock se não existir, garantindo que apenas um lock
        seja criado por pool_key mesmo com acesso concorrente.
        """
        # Fast path: lock já existe
        if pool_key in self._locks_dict:
            return self._locks_dict[pool_key]

        # Slow path: criar lock com proteção
        with self._locks_meta_lock:
            # Double-check após adquirir meta-lock
            if pool_key not in self._locks_dict:
                self._locks_dict[pool_key] = threading.Lock()
            return self._locks_dict[pool_key]

    def _is_in_quarantine(self, pool_key: str) -> bool:
        """Returns True if pool_key is currently quarantined as offline.

        Quarantine expires automatically after OFFLINE_QUARANTINE_SECONDS.
        Thread-safe via _offline_lock.
        """
        with self._offline_lock:
            until = self._offline_until.get(pool_key)
            if until is None:
                return False
            if time.time() >= until:
                # Expirou — limpar e permitir nova tentativa
                del self._offline_until[pool_key]
                return False
            return True

    def _mark_offline(self, pool_key: str) -> None:
        """Marca pool_key como offline pelo periodo de quarentena."""
        with self._offline_lock:
            self._offline_until[pool_key] = time.time() + self.OFFLINE_QUARANTINE_SECONDS

    def get_connection(self, server_id: str, database: str = "master") -> Optional[pyodbc.Connection]:
        """
        Obtém conexão do pool ou cria nova se necessário.

        Args:
            server_id: ID do servidor (HOST_INSTANCE ou HOST\\INSTANCE)
            database: Database a conectar (default: master)

        Returns:
            Conexão pyodbc ou None se falhar
        """
        pool_key = f"{server_id}_{database}"

        # Fast-fail: se este servidor falhou ha menos de OFFLINE_QUARANTINE_SECONDS
        # nao gasta os 7s de retries — devolve None imediatamente
        if self._is_in_quarantine(pool_key):
            self.stats['fast_fail_offline'] += 1
            logger.debug(f"Fast-fail (quarantine): {pool_key}")
            return None

        # FASE 1 (com lock): tentar reutilizar conexão do pool.
        # O lock protege apenas a lista do pool — operações rápidas (pop/append
        # + SELECT 1 de validação em conexão quente, ~ms).
        with self._get_pool_lock(pool_key):
            # Tentar obter conexão do pool
            while self.pools[pool_key]:
                conn, created_at = self.pools[pool_key].pop()

                # Verificar se conexão ainda é válida
                if time.time() - created_at < self.connection_lifetime:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT 1")
                        cursor.close()
                        self.stats['pool_hits'] += 1
                        self.active_connections[pool_key] += 1
                        return conn
                    except pyodbc.Error:
                        try:
                            conn.close()
                        except Exception:
                            pass
                else:
                    try:
                        conn.close()
                    except Exception:
                        pass

            # Pool vazio — vamos criar nova conexão FORA do lock
            self.stats['pool_misses'] += 1

        # FASE 2 (SEM lock): criar nova conexão.
        # Fix 2026-07-15: o handshake TCP+login (segundos numa instância fria,
        # + resolução SQL Browser em instância nomeada) estava DENTRO do lock
        # por pool_key — os 7 fetches paralelos do Overview serializavam e o
        # custo de conexão multiplicava por 7 em wall-clock. Criar fora do
        # lock deixa os handshakes correr em simultâneo. O cap do pool
        # continua garantido no return_connection (excedentes são fechados).
        try:
            conn_str = self._build_connection_string(server_id, database)
            conn = self._create_connection(conn_str)

            # Configurar isolation level
            cursor = conn.cursor()
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
            cursor.close()

            with self._get_pool_lock(pool_key):
                self.stats['total_connections'] += 1
                self.stats['active_connections'] += 1
                self.active_connections[pool_key] += 1

            logger.debug(f"New connection created: {pool_key}")
            return conn

        except CircuitBreakerError:
            self.stats['connection_errors'] += 1
            # Circuit breaker global aberto — quarentenar este server tambem
            self._mark_offline(pool_key)
            logger.warning(f"Circuit breaker OPEN for {pool_key} — fast-failing + quarantining")
            return None

        except Exception as e:
            self.stats['connection_errors'] += 1
            # Marcar este servidor como offline para os proximos 60s
            self._mark_offline(pool_key)
            logger.warning(f"Connection error to {pool_key} (quarantining for {self.OFFLINE_QUARANTINE_SECONDS:.0f}s): {e}")
            return None

    @staticmethod
    @retry_db_operation
    def _create_connection(conn_str):
        """Create a pyodbc connection with retry logic.

        REMOVED @sql_server_breaker — esse breaker era GLOBAL para todos os
        servidores monitorizados. 5 falhas em SQLHDSQLT051 abriam o breaker
        para SQLADSPRD003 tambem (e todos os outros), causando 504s em
        servidores saudaveis. A quarentena per-server (_offline_until) que
        adicionei substitui esta funcionalidade de forma mais granular.
        """
        conn = pyodbc.connect(conn_str, timeout=settings.connection_timeout, autocommit=True)
        # DMVs como dm_exec_sql_text devolvem VARCHAR com bytes cp1252 (acentos PT
        # em colunas VARCHAR com collation Latin1_General_*). Default UTF-8 rebenta
        # com 'invalid start byte' em caracteres como 'ã'(0xE3) seguidos de byte
        # continuation invalido. cp1252 e o encoding canonico de SQL Server em PT.
        try:
            conn.setdecoding(pyodbc.SQL_CHAR, encoding='cp1252')
            conn.setencoding(encoding='cp1252')
        except Exception:
            pass
        return conn

    def return_connection(self, server_id: str, conn: pyodbc.Connection, database: str = "master"):
        """Devolve conexão ao pool para reutilização."""
        if conn is None:
            return

        pool_key = f"{server_id}_{database}"

        with self._get_pool_lock(pool_key):
            self.active_connections[pool_key] = max(0, self.active_connections[pool_key] - 1)

            # Verificar se conexão ainda é válida
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                connection_valid = True
            except pyodbc.Error:
                connection_valid = False

            if connection_valid and len(self.pools[pool_key]) < self.max_connections:
                self.pools[pool_key].append((conn, time.time()))
                self.stats['active_connections'] = max(0, self.stats['active_connections'] - 1)
                logger.debug(f"Connection returned to pool: {pool_key}")
            else:
                try:
                    conn.close()
                    self.stats['active_connections'] = max(0, self.stats['active_connections'] - 1)
                except Exception:
                    pass

    def _load_credentials_cache(self) -> None:
        """Load servers.json into _creds_cache. Lazy: only on first miss or
        when the file mtime changes. Thread-safe via _creds_cache_lock.

        Each entry maps server_id (uppercase) to a dict:
            {
                'host': str,
                'instance': str | '',
                'port': int | None,
                'use_windows_auth': bool,
                'username': str | None,
                'password': str | None,  # plaintext, decrypted if needed
            }
        """
        import json as _json
        import os as _os

        with self._creds_cache_lock:
            try:
                mtime = _os.path.getmtime(self._creds_cache_path)
            except OSError:
                logger.warning(f"Cannot stat {self._creds_cache_path}")
                return

            if self._creds_cache and mtime == self._creds_cache_loaded_at:
                return  # cache still fresh

            try:
                with open(self._creds_cache_path, 'r', encoding='utf-8') as f:
                    cfg = _json.load(f)
            except Exception as e:
                logger.error(f"Failed to load {self._creds_cache_path}: {e}")
                return

            servers = cfg.get('monitored_servers', cfg.get('servers', []))
            new_cache: Dict[str, dict] = {}

            # Lazy import to avoid module-level circular
            try:
                from services.secrets import get_secret as _get_secret
            except Exception:
                _get_secret = None

            # Decrypt helper for Fernet "encrypted:..." values
            def _decrypt(val):
                if not val:
                    return val
                if not isinstance(val, str):
                    return val
                if not val.startswith('encrypted:'):
                    return val
                try:
                    from cryptography.fernet import Fernet
                    # Etapa 1.4 (empacotamento): cadeia de resolucao unica em
                    # services.secrets.try_get_master_key() — ficheiro DPAPI
                    # machine-scope -> env DPAPI user-scope -> plain key.
                    from services.secrets import try_get_master_key
                    key = try_get_master_key()
                    if not key:
                        return val  # no key, give up
                    f = Fernet(key)
                    return f.decrypt(val[len('encrypted:'):].encode()).decode()
                except Exception as decrypt_err:
                    logger.debug(f"Failed to decrypt server password: {decrypt_err}")
                    return val

            for s in servers:
                sid = (s.get('id') or s.get('server_id') or '').strip()
                if not sid:
                    continue
                host = s.get('host') or s.get('server_name') or s.get('server', '')
                instance = s.get('instance') or s.get('instance_name') or ''
                port = s.get('port')
                use_win = bool(s.get('use_windows_auth', True))
                username = s.get('username')
                password = _decrypt(s.get('password'))

                entry = {
                    'host': host,
                    'instance': instance,
                    'port': port,
                    'use_windows_auth': use_win,
                    'username': username,
                    'password': password,
                }
                new_cache[sid.upper()] = entry
                # Also index by host alone (for callers passing just hostname)
                if host:
                    host_key = host.upper()
                    if host_key not in new_cache:
                        new_cache[host_key] = entry

            self._creds_cache = new_cache
            self._creds_cache_loaded_at = mtime
            logger.info(f"SQLServerConnectionPool credentials cache loaded: {len(new_cache)} entries")

    def _resolve_credentials(self, server_id: str) -> Optional[dict]:
        """Look up credentials for a server_id. Loads cache lazily.

        Tries multiple key formats:
            - exact match on uppercase id
            - HOST_INSTANCE format
            - HOST\\INSTANCE format
            - just HOST
        Returns None if no match (caller should fall back to Trusted_Connection).
        """
        if not self._creds_cache:
            self._load_credentials_cache()

        sid_upper = server_id.upper()
        if sid_upper in self._creds_cache:
            return self._creds_cache[sid_upper]

        # Try with backslash converted to underscore (and vice versa)
        if '\\' in server_id:
            alt = server_id.replace('\\', '_').upper()
            if alt in self._creds_cache:
                return self._creds_cache[alt]
        elif '_' in server_id:
            alt = server_id.replace('_', '\\').upper()
            if alt in self._creds_cache:
                return self._creds_cache[alt]

        # Try just the hostname (before any separator)
        host_only = server_id.split('_', 1)[0].split('\\', 1)[0].upper()
        if host_only in self._creds_cache:
            return self._creds_cache[host_only]

        return None

    def _load_sql_auth_rollout(self) -> set:
        """Allowlist de server_ids autorizados a ligar por SQL Auth (FASE 1).

        Ficheiro config/sql_auth_rollout.json, formato:
            { "sql_auth_servers": ["HOST_INST", "HOST2_INST", ...] }
        O valor especial "*" liga SQL Auth para TODOS (usar so' quando a frota
        inteira ja' tiver os grants aplicados). FAIL-CLOSED: se o ficheiro nao
        existe, esta vazio ou e' invalido, devolve set() -> ninguem usa SQL Auth
        (todos Trusted). Recarrega quando o ficheiro muda (mesma disciplina do
        creds cache) para permitir rollout servidor-a-servidor sem restart.
        """
        import os as _os
        import json as _json
        with self._sql_auth_rollout_lock:
            try:
                mtime = _os.path.getmtime(self._sql_auth_rollout_path)
            except OSError:
                # ficheiro ausente -> allowlist vazia (default seguro / fail-closed)
                self._sql_auth_rollout = set()
                self._sql_auth_rollout_loaded_at = 0.0
                return self._sql_auth_rollout

            if self._sql_auth_rollout and mtime == self._sql_auth_rollout_loaded_at:
                return self._sql_auth_rollout

            try:
                with open(self._sql_auth_rollout_path, 'r', encoding='utf-8') as f:
                    cfg = _json.load(f)
                servers = cfg.get('sql_auth_servers', []) or []
                self._sql_auth_rollout = {
                    str(s).strip().upper() for s in servers if str(s).strip()
                }
            except Exception as e:
                logger.error(
                    f"Failed to load {self._sql_auth_rollout_path}: {e}; "
                    f"SQL Auth rollout DESLIGADO (fail-closed)"
                )
                self._sql_auth_rollout = set()
            self._sql_auth_rollout_loaded_at = mtime
            logger.info(
                f"SQL Auth rollout allowlist: {len(self._sql_auth_rollout)} servidor(es)"
            )
            return self._sql_auth_rollout

    def _sql_auth_enabled_for(self, server_id: str) -> bool:
        """True se este server_id esta na allowlist de rollout do SQL Auth.

        NAO usar `use_windows_auth` do servers.json como sinal de prontidao: essa
        flag ja' esta False em toda a frota sem os grants aplicados. So' a allowlist
        explicita conta. "*" liga todos. Tolera variantes _ <-> \\ (mesma logica
        do _resolve_credentials).
        """
        allow = self._load_sql_auth_rollout()
        if "*" in allow:
            return True
        sid = server_id.upper()
        if sid in allow:
            return True
        if '\\' in server_id and server_id.replace('\\', '_').upper() in allow:
            return True
        if '_' in server_id and server_id.replace('_', '\\').upper() in allow:
            return True
        return False

    def _load_net_cache(self) -> Dict[str, dict]:
        """Porta TCP + IPv4 aprendidos pelo collector V1 (Wave A, TTL 5 min).

        Uma unica query por janela de TTL, nunca por ligacao. FAIL-OPEN em
        toda a linha: se as tabelas nao existirem (DDL da SECAO 19 por
        aplicar), o GRANT faltar ou a Intelligence estiver em baixo, devolve
        o que tiver e o chamador cai no comportamento anterior.
        """
        now = time.time()
        with self._net_cache_lock:
            if self._net_cache_loaded_at and (now - self._net_cache_loaded_at) < NET_CACHE_TTL:
                return self._net_cache
            # Marcar ANTES de ir a BD: se a query pendurar ou falhar, as outras
            # threads nao formam stampede a repetir a mesma query lenta.
            self._net_cache_loaded_at = now

        ports: Dict[str, int] = {}
        ips: Dict[str, tuple] = {}
        try:
            for row in execute_on_intelligence(
                "SELECT Instance, Tcp_Port FROM dbo.WDB_INSTANCE_TCP_PORT WITH (NOLOCK)"
            ):
                inst, port = row.get('Instance'), row.get('Tcp_Port')
                if inst and port:
                    ports[str(inst).upper()] = int(port)
        except Exception as e:
            logger.debug(f"WDB_INSTANCE_TCP_PORT indisponivel (fail-open): {e}")

        try:
            for row in execute_on_intelligence(
                "SELECT Host, Ipv4, Fqdn FROM dbo.WDB_HOST_IP_CACHE WITH (NOLOCK)"
            ):
                host, ipv4 = row.get('Host'), row.get('Ipv4')
                if host and ipv4:
                    ips[str(host).upper()] = (str(ipv4), row.get('Fqdn'))
        except Exception as e:
            logger.debug(f"WDB_HOST_IP_CACHE indisponivel (fail-open): {e}")

        cache = {'ports': ports, 'ips': ips}
        with self._net_cache_lock:
            self._net_cache = cache
        if ports or ips:
            logger.info(f"[NET_CACHE] {len(ports)} portas + {len(ips)} IPs carregados da BD")
        return cache

    def _learned_target(self, server_id: str, host: str) -> Optional[Tuple[str, Optional[str]]]:
        """(SERVER=ip,porta + ServerSPN) a partir do que o collector aprendeu.

        Devolve None quando nao ha porta conhecida -- o chamador segue para o
        fallback de hoje. So devolve alvo por IP quando TEM porta: ligar por
        IP sem porta a uma instancia nomeada seria pior que o estado atual.
        """
        if not NET_CACHE_ENABLED:
            return None
        cache = self._load_net_cache()
        ports = cache.get('ports') or {}

        # server_id pode vir em qualquer das formas (host\inst ou host_inst)
        port = ports.get(server_id.upper())
        if port is None and '\\' in server_id:
            port = ports.get(server_id.replace('\\', '_').upper())
        if port is None and '_' in server_id:
            port = ports.get(server_id.replace('_', '\\').upper())
        if not port:
            return None

        ip, fqdn = (cache.get('ips') or {}).get(host.upper(), (None, None))
        if not ip:
            # cache de IP fria: resolver agora (bounded, fail-open)
            ip, fqdn = resolve_ipv4_cached(host)
        if not ip:
            # sem IP mas COM porta: host,porta ja dispensa o SQL Browser
            return f"{host},{port}", None

        spn = f"MSSQLSvc/{fqdn}:{port}" if fqdn and '.' in str(fqdn) else None
        return f"{ip},{port}", spn

    def _build_server_target_ex(self, server_id: str) -> Tuple[str, Optional[str]]:
        """Resolve (SERVER=..., ServerSPN|None) a partir do server_id.

        Fase B resiliencia (2026-07-28, gate v1-intel): instancias DEFAULT
        ligam por IPv4,1433 (bypassa o getaddrinfo IPv6-first do OS que
        pendura sob VPN) + ServerSPN=MSSQLSvc/fqdn:1433 (preserva Kerberos).
        Porta manual !=1433 ganha sempre; instancias NOMEADAS ficam no
        comportamento atual (host\\instance via SQL Browser) ate a wave
        completa (port-discovery). Fail-open em toda a linha.
        """
        def _default_target(host: str) -> Tuple[str, Optional[str]]:
            # host ja e' IP literal -> comportamento atual (sem SPN, como hoje)
            if not IPV4_DIRECT_DEFAULT_INSTANCES or _IP_LITERAL_RE.match(host):
                return host, None
            ip, fqdn = resolve_ipv4_cached(host)
            if ip and fqdn and '.' in fqdn:
                return f"{ip},1433", f"MSSQLSvc/{fqdn}:1433"
            if ip:
                # sem FQDN completo nao ha SPN valido -> ligar por IP na mesma
                # (NTLM); melhor que pendurar no resolver do OS
                return f"{ip},1433", None
            return host, None   # fail-open: exatamente o comportamento de hoje

        creds = self._resolve_credentials(server_id)
        if creds:
            host = creds.get('host') or server_id
            instance = creds.get('instance') or ''
            port = creds.get('port')
            # (1) porta manual explicita no servers.json -> intencao do admin, ganha sempre
            if port and port != 1433:
                return f"{host},{port}", None
            # (2) porta descoberta pelo collector (Wave A) -> ip,porta + SPN.
            #     E' aqui que as instancias NOMEADAS deixam de precisar do
            #     SQL Browser; sem isto a fase B so cobria as DEFAULT.
            learned = self._learned_target(server_id, host)
            if learned:
                return learned
            # (3)/(4) fallback de hoje: host\instancia (Browser) ou default
            if instance and instance.upper() not in ('', 'DEFAULT'):
                return f"{host}\\{instance}", None
            return _default_target(host)

        # Fallback parsing
        if '_' in server_id and '\\' not in server_id:
            parts = server_id.split('_', 1)
            return f"{parts[0]}\\{parts[1]}", None
        return _default_target(server_id)

    def _build_server_target(self, server_id: str) -> str:
        """Compat: devolve so o SERVER=... (ver _build_server_target_ex)."""
        return self._build_server_target_ex(server_id)[0]

    def _build_connection_string(self, server_id: str, database: str) -> str:
        """Constrói a connection string para um servidor monitorizado.

        FASE 1 least-privilege (2026-08-21): passa a poder usar SQL Auth com a
        conta least-priv (sql_monitoring, ja' preenchida no servers.json), MAS so'
        para servidores na allowlist de rollout (_sql_auth_enabled_for) — NUNCA
        pela flag use_windows_auth do servers.json sozinha, que ja' esta False em
        toda a frota sem os grants aplicados. Fora da allowlist mantem
        Trusted_Connection (comportamento historico), para o deploy do codigo ser
        neutro ate' o rollout servidor-a-servidor (grants -> validar -> allowlist).

        Regra de Ouro #2 do projecto: Trusted_Connection e' proibido em producao;
        a meta e' migrar toda a frota para SQL Auth (sql_monitoring least-priv) e a
        allowlist chegar a "*". Ate' la', Trusted e' o fallback documentado.

        O servers.json continua a ser lido (via _resolve_credentials) para host/
        instance/port em ambos os caminhos.
        """
        # Caminho SQL Auth: SO' se (a) o servidor esta na allowlist de rollout,
        # (b) o servers.json o marca para SQL Auth, (c) ha' credenciais completas.
        if self._sql_auth_enabled_for(server_id):
            creds = self._resolve_credentials(server_id)
            if (creds and not creds.get('use_windows_auth')
                    and creds.get('username') and creds.get('password')):
                sql_str = self._build_connection_string_sql_auth(server_id, database)
                if sql_str:
                    return sql_str
            logger.warning(
                f"{server_id} esta na allowlist SQL Auth mas as credenciais estao "
                f"incompletas (use_windows_auth/username/password); fallback Trusted"
            )

        server_name, server_spn = self._build_server_target_ex(server_id)

        return (
            f"DRIVER={{{settings.odbc_driver}}};"
            f"SERVER={server_name};"
            f"DATABASE={database};"
            f"Trusted_Connection=yes;"
            # ServerSPN mantem Kerberos ao ligar por IP (fase B resiliencia;
            # sem isto o SSPI cai silenciosamente para NTLM)
            + (f"ServerSPN={server_spn};" if server_spn else "")
            + f"TrustServerCertificate=yes;"
            f"Connection Timeout={settings.connection_timeout};"
        )

    def _build_connection_string_sql_auth(self, server_id: str, database: str) -> Optional[str]:
        """Variante SQL Auth — usada apenas se Trusted_Connection falhar.

        Devolve None se o server_id nao tiver credenciais SQL no servers.json
        ou se nao for use_windows_auth=False.

        Reservado para futuro fallback automatico quando o user actual perder
        acesso a um servidor.
        """
        creds = self._resolve_credentials(server_id)
        if not creds or creds.get('use_windows_auth'):
            return None
        username = creds.get('username') or ''
        password = creds.get('password') or ''
        if not username or not password:
            return None
        # SQL Auth nao usa Kerberos -> sem ServerSPN; o target IPv4,1433 (fase B)
        # beneficia na mesma (evita o hang do resolver do OS)
        server_name = self._build_server_target_ex(server_id)[0]
        return (
            f"DRIVER={{{settings.odbc_driver}}};"
            f"SERVER={server_name};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout={settings.connection_timeout};"
        )

    def _cleanup_old_connections(self):
        """Thread de limpeza de conexões antigas."""
        while self._cleanup_running:
            try:
                time.sleep(POOL_CLEANUP_INTERVAL)

                for pool_key in list(self.pools.keys()):
                    with self._get_pool_lock(pool_key):
                        valid_connections = []

                        for conn, created_at in self.pools[pool_key]:
                            if time.time() - created_at < self.connection_lifetime:
                                valid_connections.append((conn, created_at))
                            else:
                                try:
                                    conn.close()
                                    logger.debug(f"Cleanup: closed expired connection to {pool_key}")
                                except Exception:
                                    pass

                        self.pools[pool_key] = valid_connections

            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do pool."""
        total_pooled = sum(len(pool) for pool in self.pools.values())
        total_active = sum(self.active_connections.values())

        total_requests = self.stats['pool_hits'] + self.stats['pool_misses']
        hit_rate = (self.stats['pool_hits'] / total_requests * 100) if total_requests > 0 else 0

        return {
            'total_connections_created': self.stats['total_connections'],
            'active_connections': total_active,
            'pooled_connections': total_pooled,
            'connection_errors': self.stats['connection_errors'],
            'queries_executed': self.stats['queries_executed'],
            'pool_hits': self.stats['pool_hits'],
            'pool_misses': self.stats['pool_misses'],
            'pool_hit_rate': f"{hit_rate:.1f}%",
            'pools': list(self.pools.keys())
        }


# ============================================
# POOL PARA INTELLIGENCE DB (SERVIDOR FIXO)
# ============================================

class IntelligenceConnectionPool:
    """
    Pool de conexões para o banco WatcherDB_Intelligence.
    Servidor fixo, configurado via variáveis de ambiente.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Configuracao do Intelligence DB — sourced from centralized settings (pydantic-settings)
        self.server = settings.intelligence_server
        self.database = settings.intelligence_database
        self.use_windows_auth = settings.intelligence_use_windows_auth
        self.sql_user = settings.intelligence_sql_user
        # Password vem via wrapper services.secrets.get_secret que aceita
        # prefixo "encrypted:" (Fernet) e suporta WATCHERDB_ENCRYPTION_KEY_DPAPI
        # (Tier 2: DPAPI-wrapped Fernet key, recomendado em Windows).
        # NOTA: usa-se os.environ via get_secret em vez de settings.intelligence_sql_password
        # porque pydantic-settings ja' resolveu o valor — chamamos o env var pelo nome.
        from services.secrets import get_secret
        self.sql_password = get_secret("INTELLIGENCE_SQL_PASSWORD", "")
        self.driver = settings.odbc_driver

        self.pool: List[tuple] = []
        self.pool_lock = threading.Lock()
        # 2026-06-09: 10 -> 20 para igualar o _query_executor (20 workers). Com 10, metade
        # das ~18 queries do dashboard ficava em fila a' espera de ligacao -> gather lento.
        # [WAIVER aplicado 2026-06-09 | regra: edicao ficheiro producao | scope: pool 10->20]
        self.max_connections = 20
        self.connection_lifetime = POOL_CONNECTION_LIFETIME

        self.stats = {
            'total_connections': 0,
            'pool_hits': 0,
            'pool_misses': 0,
            'connection_errors': 0
        }

        self._initialized = True
        logger.info(f"IntelligenceConnectionPool initialized (server={self.server}, db={self.database})")

    def get_connection(self) -> pyodbc.Connection:
        """Obtém conexão do pool ou cria nova."""
        with self.pool_lock:
            # Tentar obter do pool
            while self.pool:
                conn, created_at = self.pool.pop()

                if time.time() - created_at < self.connection_lifetime:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT 1")
                        cursor.close()
                        self.stats['pool_hits'] += 1
                        return conn
                    except pyodbc.Error:
                        try:
                            conn.close()
                        except Exception:
                            pass
                else:
                    try:
                        conn.close()
                    except Exception:
                        pass

            # Criar nova conexão
            self.stats['pool_misses'] += 1

            try:
                conn_str = self._build_connection_string()
                conn = self._create_connection(conn_str)

                cursor = conn.cursor()
                cursor.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
                cursor.close()

                self.stats['total_connections'] += 1
                logger.debug(f"New Intelligence connection created")
                return conn

            except Exception as e:
                self.stats['connection_errors'] += 1
                logger.error(f"Intelligence connection error: {e}")
                raise

    @staticmethod
    @retry_db_operation
    def _create_connection(conn_str):
        """Create a pyodbc connection with retry logic."""
        return pyodbc.connect(conn_str, timeout=settings.connection_timeout, autocommit=True)

    def return_connection(self, conn: pyodbc.Connection):
        """Devolve conexão ao pool."""
        if conn is None:
            return

        with self.pool_lock:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                connection_valid = True
            except pyodbc.Error:
                connection_valid = False

            if connection_valid and len(self.pool) < self.max_connections:
                self.pool.append((conn, time.time()))
            else:
                try:
                    conn.close()
                except Exception:
                    pass

    def _build_connection_string(self) -> str:
        """Constrói string de conexão para Intelligence DB."""
        if self.use_windows_auth:
            return (
                f"DRIVER={{{self.driver}}};"
                f"SERVER={self.server};"
                f"DATABASE={self.database};"
                f"Trusted_Connection=yes;"
                f"Connection Timeout={settings.connection_timeout};"
            )
        else:
            if not self.sql_password:
                raise ValueError("SQL Authentication requer senha (INTELLIGENCE_SQL_PASSWORD)")
            return (
                f"DRIVER={{{self.driver}}};"
                f"SERVER={self.server};"
                f"DATABASE={self.database};"
                f"UID={self.sql_user};"
                f"PWD={self.sql_password};"
                f"Connection Timeout={settings.connection_timeout};"
            )

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do pool."""
        total_requests = self.stats['pool_hits'] + self.stats['pool_misses']
        hit_rate = (self.stats['pool_hits'] / total_requests * 100) if total_requests > 0 else 0

        return {
            'server': self.server,
            'database': self.database,
            'total_connections_created': self.stats['total_connections'],
            'pooled_connections': len(self.pool),
            'connection_errors': self.stats['connection_errors'],
            'pool_hits': self.stats['pool_hits'],
            'pool_misses': self.stats['pool_misses'],
            'pool_hit_rate': f"{hit_rate:.1f}%"
        }


# ============================================
# INSTÂNCIAS GLOBAIS (SINGLETON)
# ============================================

def get_sql_server_pool() -> SQLServerConnectionPool:
    """Retorna instância singleton do pool de servidores SQL."""
    return SQLServerConnectionPool()


def get_intelligence_pool() -> IntelligenceConnectionPool:
    """Retorna instância singleton do pool do Intelligence DB."""
    return IntelligenceConnectionPool()


# ============================================
# FUNÇÕES HELPER PARA USO SIMPLIFICADO
# ============================================

def execute_on_server(server_id: str, query: str, database: str = "master", timeout_s: int = 0) -> List[Dict[str, Any]]:
    """
    Executa query em um servidor SQL monitorado usando pool de conexões.

    Args:
        server_id: ID do servidor (HOST_INSTANCE ou HOST\\INSTANCE)
        query: Query SQL a executar
        database: Database (default: master)
        timeout_s: command timeout em segundos (0 = sem limite, comportamento
            historico). 2026-09-02 (drill-down TLOG, gate sql-deep): ate aqui
            nenhum caller tinha command timeout — o cancel do anyio abandona a
            espera mas a thread e a ligacao do pool ficam presas. Reposto a 0
            antes de devolver a ligacao ao pool (e' reutilizada).

    Returns:
        Lista de dicionários com resultados
    """
    pool = get_sql_server_pool()
    conn = None

    try:
        conn = pool.get_connection(server_id, database)
        if conn is None:
            raise Exception(f"Não foi possível conectar ao servidor {server_id}")

        if timeout_s and timeout_s > 0:
            try:
                conn.timeout = int(timeout_s)
            except Exception:
                pass
        cursor = conn.cursor()
        cursor.execute(query)

        if cursor.description is None:
            return []

        columns = [desc[0] for desc in cursor.description]
        results = []

        for row in cursor.fetchall():
            row_dict = {}
            for i, value in enumerate(row):
                # Converter tipos especiais
                if hasattr(value, '__float__'):  # Decimal
                    row_dict[columns[i]] = float(value)
                else:
                    row_dict[columns[i]] = value
            results.append(row_dict)

        cursor.close()
        pool.stats['queries_executed'] += 1
        return results

    finally:
        if conn:
            if timeout_s and timeout_s > 0:
                try:
                    conn.timeout = 0
                except Exception:
                    pass
            pool.return_connection(server_id, conn, database)


def execute_on_intelligence(query: str, params=None) -> List[Dict[str, Any]]:
    """
    Executa query no banco WatcherDB_Intelligence usando pool de conexões.

    Args:
        query: Query SQL a executar
        params: tuple/list de parametros para queries parametrizadas (opcional).
                Usa placeholders ? no query (ex: "WHERE x = ?")

    Returns:
        Lista de dicionários com resultados
    """
    pool = get_intelligence_pool()
    conn = None

    try:
        conn = pool.get_connection()

        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        if cursor.description is None:
            return []

        columns = [desc[0] for desc in cursor.description]
        results = []

        for row in cursor.fetchall():
            row_dict = {}
            for i, value in enumerate(row):
                if hasattr(value, '__float__'):
                    row_dict[columns[i]] = float(value)
                else:
                    row_dict[columns[i]] = value
            results.append(row_dict)

        cursor.close()
        return results

    finally:
        if conn:
            pool.return_connection(conn)
