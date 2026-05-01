"""
Routes CRUD pour la gestion des élèves.
Toutes les opérations sont filtrées par le professeur connecté (JWT).
"""

import logging
from fastapi import APIRouter, HTTPException, Depends

logger = logging.getLogger("corrector_ai.students")
from pydantic import BaseModel
from backend.auth import get_current_professor
from backend.models.database import (
    create_student, get_students_by_professor, get_student_by_id,
    update_student, delete_student, get_exams_by_student,
    get_student_progression,
)
from backend.services.cache import cache

router = APIRouter(prefix="/api/students", tags=["Élèves"])


# ━━━ Modèles Pydantic ━━━

class StudentCreate(BaseModel):
    nom: str
    prenom: str
    classe: str
    email: str = ""

class StudentUpdate(BaseModel):
    nom: str
    prenom: str
    classe: str
    email: str = ""


# ━━━ Routes ━━━

@router.get("/")
async def list_students(prof: dict = Depends(get_current_professor)):
    """List all students for the connected professor."""
    students = get_students_by_professor(prof["id"])
    return {"students": students}


@router.post("/")
async def add_student(data: StudentCreate, prof: dict = Depends(get_current_professor)):
    """Create a new student."""
    student_id = create_student(
        professor_id=prof["id"],
        nom=data.nom,
        prenom=data.prenom,
        classe=data.classe,
        email=data.email,
    )
    logger.info(f"Élève créé : {data.prenom} {data.nom} (id={student_id}, classe={data.classe})")
    cache.delete(f"stats_dashboard_{prof['id']}")
    return {"id": student_id, "message": "Élève créé avec succès"}


@router.get("/{student_id}")
async def get_student(student_id: int, prof: dict = Depends(get_current_professor)):
    """Get a student's profile with stats."""
    student = get_student_by_id(student_id)
    if not student or student["professor_id"] != prof["id"]:
        raise HTTPException(status_code=404, detail="Élève non trouvé")
    # Ajouter les stats de progression
    stats = get_student_progression(student_id)
    return {**student, **stats}


@router.put("/{student_id}")
async def modify_student(
    student_id: int, data: StudentUpdate, prof: dict = Depends(get_current_professor)
):
    """Update a student's information."""
    student = get_student_by_id(student_id)
    if not student or student["professor_id"] != prof["id"]:
        raise HTTPException(status_code=404, detail="Élève non trouvé")
    update_student(student_id, data.nom, data.prenom, data.classe, data.email)
    return {"message": "Élève mis à jour"}


@router.get("/{student_id}/progression")
async def student_progression(student_id: int, prof: dict = Depends(get_current_professor)):
    """Get progression curves per subject for a student."""
    student = get_student_by_id(student_id)
    if not student or student["professor_id"] != prof["id"]:
        raise HTTPException(status_code=404, detail="Élève non trouvé")
    return get_student_progression(student_id)


@router.get("/{student_id}/exams")
async def student_exams(student_id: int, prof: dict = Depends(get_current_professor)):
    """List all exams for a student."""
    student = get_student_by_id(student_id)
    if not student or student["professor_id"] != prof["id"]:
        raise HTTPException(status_code=404, detail="Élève non trouvé")
    exams = get_exams_by_student(student_id)
    return {"exams": exams}
