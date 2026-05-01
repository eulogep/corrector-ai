"""
Cache simple en mémoire avec TTL pour Corrector AI.
Utilisé pour éviter les recalculs répétés du dashboard stats.
"""

import time
import logging
from typing import Any

logger = logging.getLogger("corrector_ai.cache")


class InMemoryCache:
    """Simple TTL cache — pas de dépendance externe (Redis, etc.)."""

    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        """Get a value from cache. Returns None if expired or missing."""
        if key not in self._store:
            return None
        value, expires_at = self._store[key]
        if time.time() > expires_at:
            del self._store[key]
            logger.debug(f"Cache expiré : {key}")
            return None
        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a value in cache with TTL (seconds)."""
        ttl = ttl or self._default_ttl
        self._store[key] = (value, time.time() + ttl)
        logger.debug(f"Cache set : {key} (TTL={ttl}s)")

    def delete(self, key: str) -> None:
        """Delete a specific key from cache."""
        if key in self._store:
            del self._store[key]
            logger.info(f"Cache invalidé : {key}")

    def clear(self) -> None:
        """Clear all cached entries."""
        self._store.clear()
        logger.info("Cache entièrement vidé")


# Instance globale
cache = InMemoryCache(default_ttl=300)  # 5 minutes
