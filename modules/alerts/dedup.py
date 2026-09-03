"""
WatcherDB Alert Routing — Deduplication Store (S3-14 C2).

Evita spam de alerts duplicados dentro de uma janela temporal configurada.
In-memory (thread-safe), reset em restart do servico — aceitavel porque a
BD persiste todo o dispatch log (cross-service correlation e feita via
dbo.alert_dispatch_log).
"""
from __future__ import annotations

import time
from threading import Lock


class DeduplicationStore:
    """TTL dict thread-safe. Singleton por processo."""

    def __init__(self):
        self._store: dict[str, float] = {}  # alert_id -> last_sent_epoch_seconds
        self._lock = Lock()

    def is_duplicate(self, alert_id: str, window_seconds: int) -> bool:
        """True se alert_id foi enviado dentro dos ultimos window_seconds.

        Side-effect: se nao for duplicado, regista timestamp actual.
        """
        with self._lock:
            last = self._store.get(alert_id)
            now = time.time()
            if last is not None and (now - last) < window_seconds:
                return True
            self._store[alert_id] = now
            return False

    def clear_expired(self, max_age_seconds: int = 3600) -> int:
        """Housekeeping — remove entradas mais antigas que max_age_seconds.

        Returns:
            numero de entradas removidas.
        """
        cutoff = time.time() - max_age_seconds
        with self._lock:
            before = len(self._store)
            self._store = {k: v for k, v in self._store.items() if v > cutoff}
            return before - len(self._store)

    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def reset(self) -> None:
        """Usado em tests. NUNCA chamar em producao."""
        with self._lock:
            self._store.clear()


# Singleton por processo. Nao ha threadlocal — todas threads partilham.
_dedup = DeduplicationStore()


def get_dedup() -> DeduplicationStore:
    return _dedup
