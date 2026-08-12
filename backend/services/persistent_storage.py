"""Stockage durable des fichiers sensibles dans Supabase Storage.

Les copies sont chargées dans un bucket privé. L'application conserve uniquement
une clé ``storage://`` dans PostgreSQL, jamais une URL publique ni un lien signé.
Un fichier temporaire local est encore utilisé pendant l'appel OCR, puis peut être
supprimé par l'OS au redéploiement sans perdre l'original durable.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import quote

import httpx

from backend.config import (
    REQUIRE_PERSISTENT_STORAGE,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_STORAGE_BUCKET,
    SUPABASE_URL,
    UPLOADS_DIR,
)


class PersistentStorageError(RuntimeError):
    """Raised when durable storage was required but could not safely be used."""


def _is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def storage_key(professor_id: int, category: str, filename: str) -> str:
    """Create a non-public, professor-scoped object path without personal data."""
    if category not in {"copies", "subjects"}:
        raise ValueError("Catégorie de stockage non autorisée.")
    return f"professors/{professor_id}/{category}/{filename}"


def storage_reference(object_key: str) -> str:
    """Return an opaque value that can be persisted without exposing a URL."""
    return f"storage://{SUPABASE_STORAGE_BUCKET}/{object_key}"


async def save_uploaded_bytes(
    *,
    professor_id: int,
    category: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> tuple[str, str]:
    """Persist an upload and return ``(temporary_local_path, durable_reference)``.

    Local-only mode remains available to tests and local development. Production
    enables ``REQUIRE_PERSISTENT_STORAGE=true`` so a missing provider becomes an
    explicit error rather than silent loss of a school copy.
    """
    if not content:
        raise PersistentStorageError("Le fichier reçu est vide.")

    temporary_path = Path(UPLOADS_DIR) / filename
    try:
        temporary_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(temporary_path.write_bytes, content)
    except OSError as exc:
        raise PersistentStorageError("Écriture locale temporaire impossible.") from exc

    if not _is_configured():
        if REQUIRE_PERSISTENT_STORAGE:
            raise PersistentStorageError("Stockage persistant non configuré.")
        return str(temporary_path), str(temporary_path)

    object_key = storage_key(professor_id, category, filename)
    endpoint = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{quote(object_key, safe='/')}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": content_type or "application/octet-stream",
        "x-upsert": "false",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            response = await client.post(endpoint, content=content, headers=headers)
    except httpx.HTTPError as exc:
        raise PersistentStorageError("Le stockage persistant est indisponible.") from exc

    if response.status_code not in {200, 201}:
        raise PersistentStorageError("Le stockage persistant a refusé le fichier.")

    return str(temporary_path), storage_reference(object_key)


def remove_temporary_file(path: str) -> None:
    """Best-effort cleanup; a durable object is never deleted from this function."""
    try:
        if path and not path.startswith("storage://"):
            os.remove(path)
    except OSError:
        pass
