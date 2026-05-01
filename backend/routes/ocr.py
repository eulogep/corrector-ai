"""
Routes OCR — upload d'image et extraction de texte manuscrit.
Utilise Gemini Vision avec fallback mock.
"""

import os
import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from backend.auth import get_current_professor
from backend.config import UPLOADS_DIR, ALLOWED_EXTENSIONS
from backend.services.vision import extract_text_structured, extract_text_simple
from backend.services.utils import validate_upload

logger = logging.getLogger("corrector_ai.ocr")
router = APIRouter(prefix="/api/ocr", tags=["OCR"])


async def _save_upload(file: UploadFile) -> str:
    """Validate, save uploaded file and return its path."""
    # Validation complète (taille, MIME, magic bytes)
    content = await validate_upload(file)

    # Sauvegarder avec un nom unique
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".bin"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOADS_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    logger.info(f"Fichier sauvegardé : {filepath} ({len(content)} octets)")
    return filepath


@router.post("/extract")
async def ocr_extract(
    file: UploadFile = File(...),
    prof: dict = Depends(get_current_professor),
):
    """
    Upload a handwritten copy image and extract structured text by exercise.
    Returns JSON with exercises breakdown.
    """
    filepath = await _save_upload(file)
    try:
        logger.info(f"OCR structuré lancé pour {filepath} (prof={prof['id']})")
        result = await extract_text_structured(filepath)
        result["image_path"] = filepath
        logger.info(f"OCR terminé : {len(result.get('exercices', []))} exercices extraits")
        return result
    except Exception as e:
        logger.error(f"Erreur OCR structuré : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur OCR : {str(e)}")


@router.post("/simple")
async def ocr_simple(
    file: UploadFile = File(...),
    prof: dict = Depends(get_current_professor),
):
    """
    Upload an image and extract raw text (no exercise breakdown).
    """
    filepath = await _save_upload(file)
    try:
        logger.info(f"OCR simple lancé pour {filepath} (prof={prof['id']})")
        text = await extract_text_simple(filepath)
        logger.info(f"OCR simple terminé : {len(text)} caractères extraits")
        return {"text": text, "image_path": filepath}
    except Exception as e:
        logger.error(f"Erreur OCR simple : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur OCR : {str(e)}")
