"""
Routes OCR — upload d'image et extraction de texte manuscrit.
Utilise Gemini Vision avec validation stricte et erreurs contrôlées.
"""

import os
import uuid
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from backend.auth import get_current_professor
from backend.config import UPLOADS_DIR, ALLOWED_EXTENSIONS, MAX_FILE_SIZE
from backend.services.vision import extract_text_structured, extract_text_simple
from backend.services.exceptions import AIServiceError
from backend.services.persistent_storage import (
    PersistentStorageError,
    remove_temporary_file,
    save_uploaded_bytes,
)

router = APIRouter(prefix="/api/ocr", tags=["OCR"])


async def _save_upload(file: UploadFile, professor_id: int) -> tuple[str, str]:
    """Persist an upload and return ``(temporary_path, durable_reference)``."""
    # Vérifier l'extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporté. Formats acceptés : {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Lire et vérifier la taille
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 10 MB)")

    filename = f"{uuid.uuid4().hex}{ext}"
    try:
        return await save_uploaded_bytes(
            professor_id=professor_id,
            category="copies",
            filename=filename,
            content=content,
            content_type=file.content_type or "application/octet-stream",
        )
    except PersistentStorageError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "persistent_storage_unavailable", "message": str(exc)},
        ) from exc


@router.post("/extract")
async def ocr_extract(
    file: UploadFile = File(...),
    prof: dict = Depends(get_current_professor),
):
    """
    Upload a handwritten copy image and extract structured text by exercise.
    Returns JSON with exercises breakdown.
    """
    filepath, durable_reference = await _save_upload(file, prof["id"])
    try:
        result = await extract_text_structured(filepath)
        result["image_path"] = durable_reference
        return result
    except AIServiceError:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Erreur interne lors du traitement OCR.")
    finally:
        remove_temporary_file(filepath)


@router.post("/simple")
async def ocr_simple(
    file: UploadFile = File(...),
    prof: dict = Depends(get_current_professor),
):
    """
    Upload an image and extract raw text (no exercise breakdown).
    """
    filepath, durable_reference = await _save_upload(file, prof["id"])
    try:
        text = await extract_text_simple(filepath)
        return {"text": text, "image_path": durable_reference}
    except AIServiceError:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Erreur interne lors du traitement OCR.")
    finally:
        remove_temporary_file(filepath)
