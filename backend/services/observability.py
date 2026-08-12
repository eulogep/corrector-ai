"""Observabilité des appels aux fournisseurs IA.

Les métriques ont une cardinalité bornée et les logs de tracing ne contiennent ni prompts,
ni réponses, ni identité d'élève. Chaque appel IA émet un trace_id corrélable avec le
request_id HTTP afin de diagnostiquer les latences et échecs en production.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from prometheus_client import Counter, Gauge, Histogram, generate_latest

from backend.services.exceptions import AIServiceError


logger = logging.getLogger("corrector_ai.observability")
request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)

AI_CALLS_TOTAL = Counter(
    "corrector_ai_ai_calls_total",
    "Nombre total d'appels IA finalisés.",
    ("provider", "operation", "outcome"),
)
AI_CALL_ERRORS_TOTAL = Counter(
    "corrector_ai_ai_call_errors_total",
    "Nombre d'appels IA en erreur par code applicatif.",
    ("provider", "operation", "code"),
)
AI_CALL_DURATION_SECONDS = Histogram(
    "corrector_ai_ai_call_duration_seconds",
    "Durée totale des appels IA, validation incluse.",
    ("provider", "operation"),
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120),
)
AI_CALLS_IN_PROGRESS = Gauge(
    "corrector_ai_ai_calls_in_progress",
    "Nombre d'appels IA actuellement en cours.",
    ("provider", "operation"),
)


def set_request_id(request_id: str):
    """Associer un identifiant HTTP au contexte asynchrone courant."""
    return request_id_context.set(request_id)


def reset_request_id(token) -> None:
    """Nettoyer le contexte de requête à la fin du traitement HTTP."""
    request_id_context.reset(token)


def _log(event: str, **fields: object) -> None:
    """Émettre un évènement JSON ne contenant aucune donnée personnelle ou de copie."""
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))


@contextmanager
def observe_ai_call(provider: str, operation: str) -> Iterator[str]:
    """Tracer un appel IA et publier latence, succès ou échec en métriques Prometheus."""
    trace_id = uuid.uuid4().hex
    request_id = request_id_context.get()
    started_at = time.perf_counter()
    outcome = "success"
    error_code: str | None = None

    AI_CALLS_IN_PROGRESS.labels(provider=provider, operation=operation).inc()
    _log(
        "ai_call_started",
        trace_id=trace_id,
        request_id=request_id,
        provider=provider,
        operation=operation,
    )

    try:
        yield trace_id
    except AIServiceError as exc:
        outcome = "error"
        error_code = exc.code
        raise
    except Exception:
        outcome = "error"
        error_code = "unexpected_error"
        raise
    finally:
        duration = time.perf_counter() - started_at
        AI_CALLS_IN_PROGRESS.labels(provider=provider, operation=operation).dec()
        AI_CALL_DURATION_SECONDS.labels(provider=provider, operation=operation).observe(duration)
        AI_CALLS_TOTAL.labels(provider=provider, operation=operation, outcome=outcome).inc()
        if error_code:
            AI_CALL_ERRORS_TOTAL.labels(
                provider=provider, operation=operation, code=error_code
            ).inc()

        _log(
            "ai_call_finished",
            trace_id=trace_id,
            request_id=request_id,
            provider=provider,
            operation=operation,
            outcome=outcome,
            error_code=error_code,
            duration_ms=round(duration * 1000, 2),
        )


def prometheus_metrics() -> bytes:
    """Sérialiser le registre Prometheus standard au format texte."""
    return generate_latest()
