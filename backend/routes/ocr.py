"""
Routes OCR — upload d'image et extraction de texte manuscrit.
Utilise Gemini Vision avec fallback mock.
"""

import os
import uuid
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from backend.auth import get_current_professor
from backend.config import UPLOADS_DIR, ALLOWED_EXTENSIONS, MAX_FILE_SIZE
from backend.services.vision import extract_text_structured, extract_text_simple

router = APIRouter(prefix="/api/ocr", tags=["OCR"])


async def _save_upload(file: UploadFile) -> str:
    """Save uploaded file and return its path."""
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

    # Sauvegarder avec un nom unique
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOADS_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

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
        result = await extract_text_structured(filepath)
        result["image_path"] = filepath
        return result
    except Exception as e:
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
        text = await extract_text_simple(filepath)
        return {"text": text, "image_path": filepath}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur OCR : {str(e)}")
