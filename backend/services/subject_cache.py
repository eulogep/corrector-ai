"""Cache Redis des analyses de sujets.

Les clés sont dérivées du hachage du contenu, de la version du contrat et d'un espace de
nommage professeur. Aucun texte de sujet ni identifiant élève n'est présent dans les clés
ou les métriques. Redis reste une optimisation : toute erreur de cache laisse le pipeline
Docling/OCR/LLM poursuivre normalement.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

from backend.config import REDIS_URL, SUBJECT_CACHE_TTL_SECONDS
from backend.services.observability import record_subject_cache_result


logger = logging.getLogger("corrector_ai.subject_cache")
CACHE_PREFIX = "corrector-ai:subject-rubric:v1"


class SubjectExtractionCache:
    """Accès Redis minimal pour les résultats validés d'extraction de sujet."""

    def __init__(self, redis_url: str = REDIS_URL, ttl_seconds: int = SUBJECT_CACHE_TTL_SECONDS):
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.redis_url)

    async def _get_client(self):
        if self._client is None:
            from redis.asyncio import Redis

            self._client = Redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
                health_check_interval=30,
            )
        return self._client

    async def key_for_file(self, file_path: str, namespace: str) -> str:
        """Produire une clé non réversible à partir du fichier et de son espace professeur."""
        def compute_hash() -> str:
            digest = hashlib.sha256()
            with open(file_path, "rb") as file:
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()

        content_hash = await asyncio.to_thread(compute_hash)
        namespace_hash = hashlib.sha256(namespace.encode("utf-8")).hexdigest()[:16]
        return f"{CACHE_PREFIX}:{namespace_hash}:{content_hash}"

    async def get(self, cache_key: str) -> dict[str, Any] | None:
        """Lire un résultat de cache ; les pannes Redis sont converties en cache miss."""
        if not self.enabled:
            record_subject_cache_result("disabled")
            return None

        try:
            client = await self._get_client()
            payload = await client.get(cache_key)
            if payload is None:
                record_subject_cache_result("miss")
                return None
            decoded = json.loads(payload)
            if not isinstance(decoded, dict):
                raise ValueError("Le payload Redis n'est pas un objet JSON.")
            record_subject_cache_result("hit")
            return decoded
        except Exception:
            logger.warning("Cache Redis indisponible ou entrée illisible", exc_info=False)
            record_subject_cache_result("unavailable")
            return None

    async def set(self, cache_key: str, payload: dict[str, Any]) -> None:
        """Enregistrer un résultat validé avec expiration; l'échec est non bloquant."""
        if not self.enabled:
            return

        try:
            client = await self._get_client()
            serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            await client.set(cache_key, serialized, ex=self.ttl_seconds)
            record_subject_cache_result("stored")
        except Exception:
            logger.warning("Écriture Redis impossible; le résultat ne sera pas mis en cache", exc_info=False)
            record_subject_cache_result("unavailable")

    async def close(self) -> None:
        """Fermer le pool Redis lors de l'arrêt applicatif."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def delete(self, cache_key: str) -> None:
        """Supprimer une entrée invalide sans faire échouer l'analyse du sujet."""
        if not self.enabled:
            return
        try:
            client = await self._get_client()
            await client.delete(cache_key)
        except Exception:
            logger.warning("Suppression Redis impossible", exc_info=False)
