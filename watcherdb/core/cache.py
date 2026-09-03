"""
Redis-like Cache Implementation
Provides TTL, persistence, pub/sub, and memory management
"""

import os
import time
import pickle
import threading
import collections
import fnmatch
import logging
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger(__name__)


class RedisLikeCache:
    """
    Implementação completa de cache tipo Redis
    Features: TTL, persistência, pub/sub, transações, clustering simulation
    """

    def __init__(self, persistence_file: str = "watcherdb_cache.db", max_memory_mb: int = 100):
        self.data: Dict[str, Dict[str, Any]] = {}
        self.ttl_data: Dict[str, float] = {}
        self.subscribers: Dict[str, List[Callable]] = collections.defaultdict(list)
        # B1-6 (auditoria empacotamento 2026-07-03): paths relativos resolvem
        # via cache_dir() — o CWD de um servico Windows e System32; nunca
        # gravar relativo ao CWD. Absolutos passam intactos; None preserva o
        # contrato original "sem persistencia" (tests/conftest.py:14).
        if persistence_file is None:
            self.persistence_file = None
        else:
            from pathlib import Path as _Path
            from watcherdb.core.paths import cache_dir as _cache_dir
            _pf = _Path(persistence_file)
            self.persistence_file = str(_pf if _pf.is_absolute() else _cache_dir() / _pf)
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.lock = threading.Lock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'expired': 0
        }

        # Background tasks
        self._cleanup_running = True
        self._persistence_running = True

        # Load persisted data
        self._load_persistence()

        # Start background tasks
        threading.Thread(target=self._cleanup_expired, daemon=True).start()
        threading.Thread(target=self._persist_data, daemon=True).start()

        logger.info(f"RedisLikeCache initialized with {len(self.data)} persisted keys")

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set key-value with optional TTL (in seconds)"""
        try:
            with self.lock:
                # Memory management
                if self._get_memory_usage() > self.max_memory_bytes:
                    self._evict_lru()

                # Serialize complex objects
                if isinstance(value, (dict, list, set, tuple)):
                    serialized_value = {
                        'type': type(value).__name__,
                        'data': value if isinstance(value, (dict, list)) else list(value),
                        'serialized': True
                    }
                else:
                    serialized_value = value

                self.data[key] = {
                    'value': serialized_value,
                    'created': time.time(),
                    'accessed': time.time(),
                    'access_count': 0
                }

                if ttl:
                    self.ttl_data[key] = time.time() + ttl
                elif key in self.ttl_data:
                    del self.ttl_data[key]

                self.stats['sets'] += 1
                return True

        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False

    def get(self, key: str) -> Optional[Any]:
        """Get value by key"""
        try:
            with self.lock:
                # Check if key exists
                if key not in self.data:
                    self.stats['misses'] += 1
                    return None

                # Check TTL
                if key in self.ttl_data and time.time() > self.ttl_data[key]:
                    del self.data[key]
                    del self.ttl_data[key]
                    self.stats['expired'] += 1
                    self.stats['misses'] += 1
                    return None

                # Update access stats
                self.data[key]['accessed'] = time.time()
                self.data[key]['access_count'] += 1
                self.stats['hits'] += 1

                # Deserialize if needed
                value_data = self.data[key]['value']
                if isinstance(value_data, dict) and value_data.get('serialized'):
                    if value_data['type'] == 'set':
                        return set(value_data['data'])
                    elif value_data['type'] == 'tuple':
                        return tuple(value_data['data'])
                    else:
                        return value_data['data']

                return value_data

        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None

    def delete(self, key: str) -> bool:
        """Delete key"""
        try:
            with self.lock:
                if key in self.data:
                    del self.data[key]
                    if key in self.ttl_data:
                        del self.ttl_data[key]
                    self.stats['deletes'] += 1
                    return True
                return False
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False

    def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern"""
        try:
            with self.lock:
                if pattern == "*":
                    return list(self.data.keys())

                # Simple pattern matching
                return [key for key in self.data.keys() if fnmatch.fnmatch(key, pattern)]
        except Exception as e:
            logger.error(f"Cache keys error: {e}")
            return []

    def flushall(self) -> bool:
        """Clear all data"""
        try:
            with self.lock:
                self.data.clear()
                self.ttl_data.clear()
                return True
        except Exception as e:
            logger.error(f"Cache flushall error: {e}")
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists"""
        return self.get(key) is not None

    def ttl(self, key: str) -> int:
        """Get TTL for key (-1 if no TTL, -2 if key doesn't exist)"""
        try:
            with self.lock:
                if key not in self.data:
                    return -2
                if key not in self.ttl_data:
                    return -1

                remaining = self.ttl_data[key] - time.time()
                return int(remaining) if remaining > 0 else -2
        except Exception as e:
            logger.error(f"Cache TTL error: {e}")
            return -2

    def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment key value"""
        try:
            with self.lock:
                # Inline get logic (avoid re-entrant lock acquisition)
                current = 0
                if key in self.data:
                    if key in self.ttl_data and time.time() > self.ttl_data[key]:
                        del self.data[key]
                        del self.ttl_data[key]
                        self.stats['expired'] += 1
                    else:
                        value_data = self.data[key]['value']
                        if isinstance(value_data, dict) and value_data.get('serialized'):
                            current = value_data['data']
                        else:
                            current = value_data

                if isinstance(current, (int, float)):
                    new_value = int(current) + amount
                    # Inline set logic (avoid re-entrant lock acquisition)
                    self.data[key] = {
                        'value': new_value,
                        'created': time.time(),
                        'accessed': time.time(),
                        'access_count': 0
                    }
                    self.stats['sets'] += 1
                    return new_value
                return None
        except Exception as e:
            logger.error(f"Cache incr error: {e}")
            return None

    def expire(self, key: str, ttl: int) -> bool:
        """Set TTL for existing key"""
        try:
            with self.lock:
                if key in self.data:
                    self.ttl_data[key] = time.time() + ttl
                    return True
                return False
        except Exception as e:
            logger.error(f"Cache expire error: {e}")
            return False

    # ==============================
    # Pub/Sub
    # ==============================
    def publish(self, channel: str, message: Any) -> int:
        """Publish message to channel"""
        try:
            with self.lock:
                callbacks = self.subscribers.get(channel, [])
                for cb in callbacks:
                    try:
                        cb(message)
                    except Exception as e:
                        logger.error(f"Callback error in channel {channel}: {e}")
                return len(callbacks)
        except Exception as e:
            logger.error(f"Cache publish error: {e}")
            return 0

    def subscribe(self, channel: str, callback: Callable) -> None:
        """Subscribe to channel"""
        try:
            self.subscribers[channel].append(callback)
        except Exception as e:
            logger.error(f"Cache subscribe error: {e}")

    def unsubscribe(self, channel: str, callback: Callable) -> None:
        """Unsubscribe from channel"""
        try:
            if channel in self.subscribers and callback in self.subscribers[channel]:
                self.subscribers[channel].remove(callback)
        except Exception as e:
            logger.error(f"Cache unsubscribe error: {e}")

    # ==============================
    # Stats
    # ==============================
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            with self.lock:
                stats_copy = dict(self.stats)
                stats_copy['num_keys'] = len(self.data)
                stats_copy['num_ttl'] = len(self.ttl_data)
                stats_copy['total_keys'] = stats_copy['num_keys']
                stats_copy['total_ttl'] = stats_copy['num_ttl']
                total_requests = self.stats.get('hits', 0) + self.stats.get('misses', 0)
                stats_copy['hit_rate'] = round(self.stats.get('hits', 0) / total_requests, 4) if total_requests else 0.0
                stats_copy['miss_rate'] = round(self.stats.get('misses', 0) / total_requests, 4) if total_requests else 0.0
                mem_bytes = self._get_memory_usage()
                stats_copy['memory_bytes'] = mem_bytes
                stats_copy['memory_usage_mb'] = round(mem_bytes / (1024 * 1024), 2)
                return stats_copy
        except Exception:
            return {}

    def _load_persistence(self) -> None:
        """Load persisted cache from disk"""
        try:
            if not self.persistence_file:
                logger.info("No persistence file configured, starting with empty cache")
                return
                
            if not os.path.exists(self.persistence_file):
                logger.info(f"Cache file {self.persistence_file} does not exist, starting with empty cache")
                return
            
            # Verificar se o arquivo está vazio ou corrompido
            try:
                file_size = os.path.getsize(self.persistence_file)
                if file_size == 0:
                    logger.warning(f"Cache file {self.persistence_file} is empty, starting with empty cache")
                    return
            except OSError as e:
                logger.warning(f"Could not check cache file size: {e}, starting with empty cache")
                return
            
            try:
                with open(self.persistence_file, 'rb') as f:
                    persisted = pickle.load(f)
                    if isinstance(persisted, dict):
                        self.data = persisted.get('data', {}) or {}
                        self.ttl_data = persisted.get('ttl', {}) or {}
                        logger.info(f"Cache loaded successfully: {len(self.data)} keys")
                    else:
                        logger.warning(f"Cache file has invalid format, starting with empty cache")
            except (pickle.UnpicklingError, EOFError, ValueError) as e:
                logger.error(f"Cache file {self.persistence_file} appears to be corrupted: {e}")
                logger.info(f"Attempting to backup corrupted file and starting with empty cache")
                try:
                    # Fazer backup do arquivo corrompido
                    backup_name = f"{self.persistence_file}.corrupted.{int(time.time())}"
                    import shutil
                    shutil.move(self.persistence_file, backup_name)
                    logger.info(f"Corrupted cache file backed up to: {backup_name}")
                except Exception as backup_error:
                    logger.error(f"Failed to backup corrupted cache file: {backup_error}")
                    # Se não conseguir fazer backup, tentar remover
                    try:
                        os.remove(self.persistence_file)
                        logger.info(f"Removed corrupted cache file: {self.persistence_file}")
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Cache load persistence error: {e}", exc_info=True)
            # Em caso de erro, continuar com cache vazio
            self.data = {}
            self.ttl_data = {}

    def _persist_data(self) -> None:
        """Background task to persist cache to disk"""
        while self._persistence_running:
            try:
                time.sleep(10)
                # Verificar se ainda deve continuar antes de tentar escrever
                if not self._persistence_running:
                    break
                # Verificar se o arquivo de persistência está configurado
                if not self.persistence_file:
                    continue
                snapshot = None
                with self.lock:
                    snapshot = {
                        'data': self.data.copy(),
                        'ttl': self.ttl_data.copy(),
                        'timestamp': time.time()
                    }
                # Verificar novamente antes de escrever
                if not self._persistence_running:
                    break
                # Usar modo 'wb' para escrever
                try:
                    with open(self.persistence_file, 'wb') as f:
                        pickle.dump(snapshot, f)
                        f.flush()  # Garantir que os dados são escritos no buffer do sistema
                        # Tentar sincronizar com disco, mas ignorar erros durante shutdown
                        try:
                            if f.fileno() >= 0:  # Verificar se file descriptor é válido
                                os.fsync(f.fileno())
                        except (OSError, IOError, ValueError):
                            # Ignorar erros de fsync (comum durante shutdown)
                            pass
                except (OSError, IOError, ValueError) as e:
                    # Erros de I/O podem ocorrer durante shutdown - não logar como erro crítico
                    # Só logar se ainda estiver rodando e não for um erro de file descriptor
                    errno = getattr(e, 'errno', None)
                    if self._persistence_running and errno != 9:  # 9 = Bad file descriptor
                        logger.warning(f"Cache persist I/O error: {e}")
            except Exception as e:
                # Só logar como erro se ainda estiver rodando
                if self._persistence_running:
                    logger.error(f"Cache persist error: {e}")

    def _cleanup_expired(self) -> None:
        """Background task to remove expired keys"""
        while self._cleanup_running:
            try:
                time.sleep(5)
                now = time.time()
                expired_keys = []
                with self.lock:
                    for key, expire_at in list(self.ttl_data.items()):
                        if now > expire_at:
                            expired_keys.append(key)
                    for key in expired_keys:
                        if key in self.data:
                            del self.data[key]
                        if key in self.ttl_data:
                            del self.ttl_data[key]
                        self.stats['expired'] += 1
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")

    def _get_memory_usage(self) -> int:
        """Get approximate memory usage in bytes"""
        try:
            return len(pickle.dumps(self.data, protocol=pickle.HIGHEST_PROTOCOL))
        except Exception:
            return 0

    def _evict_lru(self) -> None:
        """Evict least recently used key"""
        try:
            if not self.data:
                return
            # Remove least recently accessed key
            lru_key = min(self.data.items(), key=lambda kv: kv[1].get('accessed', 0))[0]
            del self.data[lru_key]
            if lru_key in self.ttl_data:
                del self.ttl_data[lru_key]
            logger.debug(f"Evicted LRU key: {lru_key}")
        except Exception as e:
            logger.error(f"Cache LRU eviction error: {e}")

    def shutdown(self) -> None:
        """Gracefully shutdown cache (stop background tasks)"""
        self._cleanup_running = False
        self._persistence_running = False
        # Final persistence
        try:
            with self.lock:
                snapshot = {
                    'data': self.data.copy(),
                    'ttl': self.ttl_data.copy(),
                    'timestamp': time.time()
                }
            with open(self.persistence_file, 'wb') as f:
                pickle.dump(snapshot, f)
            logger.info("Cache persisted on shutdown")
        except Exception as e:
            logger.error(f"Error persisting cache on shutdown: {e}")
