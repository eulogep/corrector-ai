"""
Utilitaires partagés — validation des uploads, helpers divers.
"""

import logging
from fastapi import HTTPException, UploadFile
from backend.config import MAX_FILE_SIZE, ALLOWED_MIME_TYPES

logger = logging.getLogger("corrector_ai.utils")

# Magic bytes des formats supportés
MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"RIFF": "image/webp",  # WebP commence par RIFF....WEBP
    b"%PDF": "application/pdf",
}


def _detect_mime(content: bytes) -> str | None:
    """Detect MIME type from magic bytes."""
    header = content[:12]
    for magic, mime in MAGIC_BYTES.items():
        if header.startswith(magic):
            # Vérification supplémentaire pour WebP (RIFF....WEBP)
            if magic == b"RIFF" and b"WEBP" not in header[:12]:
                continue
            return mime
    return None


async def validate_upload(file: UploadFile) -> bytes:
    """
    Validate an uploaded file: size, MIME type, and magic bytes.
    Returns the file content bytes if valid.
    Raises HTTPException on failure.
    """
    # Lire le contenu
    content = await file.read()

    # 1. Vérifier la taille (413 si trop gros)
    if len(content) > MAX_FILE_SIZE:
        size_mb = round(len(content) / (1024 * 1024), 1)
        logger.warning(f"Upload rejeté : fichier trop volumineux ({size_mb} MB)")
        raise HTTPException(
            status_code=413,
            detail=f"Fichier trop volumineux ({size_mb} MB). Taille maximale : 10 MB.",
        )

    # 2. Vérifier le Content-Type déclaré
    declared_mime = file.content_type or ""
    if declared_mime and declared_mime not in ALLOWED_MIME_TYPES:
        logger.warning(f"Upload rejeté : type MIME déclaré non supporté ({declared_mime})")
        raise HTTPException(
            status_code=415,
            detail=f"Type de fichier non supporté : {declared_mime}. "
                   f"Types acceptés : {', '.join(sorted(ALLOWED_MIME_TYPES))}.",
        )

    # 3. Vérifier les magic bytes (le vrai type du fichier)
    detected_mime = _detect_mime(content)
    if detected_mime is None:
        logger.warning("Upload rejeté : magic bytes non reconnus")
        raise HTTPException(
            status_code=415,
            detail="Le contenu du fichier ne correspond à aucun format supporté "
                   "(JPEG, PNG, WebP, PDF).",
        )

    if detected_mime not in ALLOWED_MIME_TYPES:
        logger.warning(f"Upload rejeté : magic bytes détectés ({detected_mime}) non autorisés")
        raise HTTPException(
            status_code=415,
            detail=f"Format réel détecté : {detected_mime}. Non supporté.",
        )

    logger.info(f"Upload validé : {file.filename} ({len(content)} octets, {detected_mime})")
    return content
