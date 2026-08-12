"""
Routes de gestion des sujets d'examen.
Pipeline : upload PDF → Docling + Claude → barème JSON → validation prof → SQLite.
"""

import os
import uuid
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.auth import get_current_professor
from backend.config import UPLOADS_DIR, MAX_FILE_SIZE
from backend.services.subject_parser import parse_subject
from backend.models.database import save_subject, get_subject, list_subjects
from backend.services.exceptions import AIServiceError
from backend.services.persistent_storage import (
    PersistentStorageError,
    remove_temporary_file,
    save_uploaded_bytes,
)

router = APIRouter(prefix="/api/subjects", tags=["Sujets"])

# Formats acceptés pour un sujet (inclut DOCX)
SUBJECT_EXTENSIONS = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".webp"}


# ━━━ Modèles Pydantic ━━━

class ExerciceBareme(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    numero: int = Field(ge=1, le=500)
    enonce: str = Field(min_length=1, max_length=20_000)
    reponse_attendue: str = Field(default="", max_length=20_000)
    points_max: float = Field(gt=0, le=1000)
    type: str = Field(default="autre", min_length=1, max_length=50)
    sous_questions: list[dict] = Field(default_factory=list, max_length=100)


class ValidateSubjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    matiere: str = Field(min_length=1, max_length=200)
    niveau: str = Field(min_length=1, max_length=200)
    titre: str = Field(default="", max_length=300)
    total_points: float = Field(gt=0, le=1000)
    exercices: list[ExerciceBareme] = Field(min_length=1, max_length=500)
    pdf_path: str = Field(default="", max_length=2_000)

    @model_validator(mode="after")
    def total_matches_exercises(self) -> "ValidateSubjectRequest":
        total = round(sum(exercice.points_max for exercice in self.exercices), 2)
        if abs(total - self.total_points) > 0.01:
            raise ValueError("La somme des points des exercices doit correspondre au total_points.")
        return self


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

    filename = f"subject_{uuid.uuid4().hex}{ext}"
    try:
        filepath, durable_reference = await save_uploaded_bytes(
            professor_id=prof["id"],
            category="subjects",
            filename=filename,
            content=content,
            content_type=file.content_type or "application/octet-stream",
        )
    except PersistentStorageError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "persistent_storage_unavailable", "message": str(exc)},
        ) from exc

    try:
        bareme = await parse_subject(filepath, cache_namespace=f"professor:{prof['id']}")
        bareme["pdf_path"] = durable_reference
        return bareme
    except AIServiceError:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Erreur interne lors de l'analyse du sujet.")
    finally:
        remove_temporary_file(filepath)


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
