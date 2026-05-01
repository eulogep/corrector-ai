"""
Routes de gestion des sujets d'examen.
Pipeline : upload PDF → Docling + Claude → barème JSON → validation prof → SQLite.
"""

import os
import uuid
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from backend.auth import get_current_professor
from backend.config import UPLOADS_DIR, MAX_FILE_SIZE
from backend.services.subject_parser import parse_subject
from backend.models.database import save_subject, get_subject, list_subjects

router = APIRouter(prefix="/api/subjects", tags=["Sujets"])

# Formats acceptés pour un sujet (inclut DOCX)
SUBJECT_EXTENSIONS = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".webp"}


# ━━━ Modèles Pydantic ━━━

class ExerciceBareme(BaseModel):
    numero: int
    enonce: str = ""
    reponse_attendue: str = ""
    points_max: float = 0
    type: str = "autre"
    sous_questions: list = []


class ValidateSubjectRequest(BaseModel):
    matiere: str = ""
    niveau: str = ""
    titre: str = ""
    total_points: float = 20
    exercices: list[ExerciceBareme]
    pdf_path: str = ""


# ━━━ Routes ━━━

@router.post("/parse")
async def parse_subject_endpoint(
    file: UploadFile = File(...),
    prof: dict = Depends(get_current_professor),
):
    """
    Parse an uploaded subject (PDF/DOCX/image) and return a generated barème JSON.
    Pipeline: Docling → Claude. Does NOT save to DB.
    """
    # Validation extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in SUBJECT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporté. Acceptés : {', '.join(sorted(SUBJECT_EXTENSIONS))}",
        )

    # Validation taille
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 10 MB)")

    # Sauvegarde temporaire (réutilisé pour pdf_path si validé ensuite)
    filename = f"subject_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOADS_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    try:
        bareme = await parse_subject(filepath)
        bareme["pdf_path"] = filepath
        return bareme
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur analyse sujet : {str(e)}")


@router.post("/validate")
async def validate_subject(
    data: ValidateSubjectRequest,
    prof: dict = Depends(get_current_professor),
):
    """Persist a validated/edited barème to DB. Returns subject_id."""
    payload = {
        "matiere": data.matiere,
        "niveau": data.niveau,
        "titre": data.titre,
        "total_points": data.total_points,
        "exercices": [ex.model_dump() for ex in data.exercices],
        "pdf_path": data.pdf_path,
    }
    subject_id = save_subject(prof["id"], payload)
    return {"subject_id": subject_id, "message": "Barème enregistré"}


@router.get("/")
async def list_subjects_endpoint(prof: dict = Depends(get_current_professor)):
    """List all subjects belonging to the connected professor."""
    return {"subjects": list_subjects(prof["id"])}


@router.get("/{subject_id}")
async def get_subject_endpoint(
    subject_id: int,
    prof: dict = Depends(get_current_professor),
):
    """Fetch a single subject with its barème."""
    subject = get_subject(subject_id)
    if not subject or subject["professor_id"] != prof["id"]:
        raise HTTPException(status_code=404, detail="Sujet non trouvé")
    return subject
