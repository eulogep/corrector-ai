"""Réessais asynchrones bornés pour les fournisseurs IA.

Seuls les échecs explicitement transitoires déclenchent un réessai. Les erreurs de
configuration, de contrat JSON ou de barème sont immédiatement retournées afin d'éviter
de répéter inutilement une requête coûteuse.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from backend.config import LLM_RETRY_BASE_SECONDS, LLM_RETRY_MAX_ATTEMPTS, LLM_RETRY_MAX_SECONDS
from backend.services.exceptions import AIProviderUnavailableError
from backend.services.observability import record_ai_retry


ResultT = TypeVar("ResultT")


async def call_with_exponential_backoff(
    *,
    provider: str,
    operation: str,
    call: Callable[[], Awaitable[ResultT]],
) -> ResultT:
    """Exécuter un appel IA avec backoff exponentiel et faible jitter borné.

    L'essai initial compte dans ``LLM_RETRY_MAX_ATTEMPTS``. Avec la configuration par
    défaut, le fournisseur est donc appelé au plus trois fois avant de céder la main au
    fournisseur suivant.
    """
    for attempt in range(1, LLM_RETRY_MAX_ATTEMPTS + 1):
        try:
            return await call()
        except AIProviderUnavailableError:
            if attempt >= LLM_RETRY_MAX_ATTEMPTS:
                raise

            exponential_delay = min(
                LLM_RETRY_BASE_SECONDS * (2 ** (attempt - 1)),
                LLM_RETRY_MAX_SECONDS,
            )
            # Un jitter réduit les pointes de requêtes simultanées sans retarder
            # excessivement une correction individuelle.
            delay = exponential_delay * random.uniform(0.8, 1.2)
            record_ai_retry(
                provider=provider,
                operation=operation,
                attempt=attempt,
                delay_seconds=delay,
            )
            await asyncio.sleep(delay)

    raise RuntimeError("État de réessai inattendu")
