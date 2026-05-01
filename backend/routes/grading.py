"""
Routes de correction — envoi au LLM et sauvegarde en base.
Deux modes : correction complète (avec sauvegarde) et correction rapide (sans).
"""

import logging
from fastapi import APIRouter, HTTPException, Depends

logger = logging.getLogger("corrector_ai.grading")
from pydantic import BaseModel
from backend.auth import get_current_professor
from backend.models.database import (
    get_student_by_id, get_recent_exams_by_student_matiere,
    create_exam, create_exercise, get_exam_by_id, get_exercises_by_exam,
    delete_exam, get_subject,
)
from backend.services.llm import grade_copy

router = APIRouter(prefix="/api/grading", tags=["Correction"])


# ━━━ Modèles Pydantic ━━━

class ExerciseCorrige(BaseModel):
    numero: int
    enonce: str = ""
    reponse_attendue: str
    points_max: float

class ExerciseReponse(BaseModel):
    numero: int
    reponse_eleve: str

class GradeRequest(BaseModel):
    student_id: int
    matiere: str
    niveau: str = ""
    date_examen: str = ""
    note_sur: float = 20
    image_path: str = ""
    subject_id: int | None = None
    exercices_corrige: list[ExerciseCorrige] = []
    reponses_eleve: list[ExerciseReponse]

class QuickGradeRequest(BaseModel):
    matiere: str
    niveau: str = ""
    note_sur: float = 20
    exercices_corrige: list[ExerciseCorrige]
    reponses_eleve: list[ExerciseReponse]


# ━━━ Routes ━━━

@router.post("/grade")
async def grade_full(data: GradeRequest, prof: dict = Depends(get_current_professor)):
    """
    Full grading: grade with AI, save exam + exercises to database.
    Includes anomaly detection based on student history.
    """
    # Vérifier que l'élève existe et appartient au prof
    student = get_student_by_id(data.student_id)
    if not student or student["professor_id"] != prof["id"]:
        raise HTTPException(status_code=404, detail="Élève non trouvé")

    # Si un subject_id est fourni → charger le barème depuis SQLite
    # Sinon → utiliser les exercices_corrige fournis manuellement
    if data.subject_id is not None:
        subject = get_subject(data.subject_id)
        if not subject or subject["professor_id"] != prof["id"]:
            raise HTTPException(status_code=404, detail="Sujet non trouvé")
        exercices_corrige = [
            {
                "numero": ex.get("numero"),
                "enonce": ex.get("enonce", ""),
                "reponse_attendue": ex.get("reponse_attendue", ""),
                "points_max": ex.get("points_max", 0),
            }
            for ex in subject.get("exercices", [])
        ]
    else:
        exercices_corrige = [ex.model_dump() for ex in data.exercices_corrige]

    # Récupérer l'historique pour détection d'anomalies
    historique = get_recent_exams_by_student_matiere(data.student_id, data.matiere, limit=5)

    # Appeler le LLM
    logger.info(f"Correction complète lancée : élève={data.student_id}, matière={data.matiere}")
    result = await grade_copy(
        matiere=data.matiere,
        niveau=data.niveau,
        note_sur=data.note_sur,
        exercices_corrige=exercices_corrige,
        reponses_eleve=[r.model_dump() for r in data.reponses_eleve],
        historique=historique,
    )

    # Sauvegarder l'examen en base
    exam_id = create_exam(
        student_id=data.student_id,
        professor_id=prof["id"],
        matiere=data.matiere,
        niveau=data.niveau,
        date_examen=data.date_examen or "",
        note_totale=result.get("note_totale", 0),
        note_sur=result.get("note_sur", data.note_sur),
        appreciation=result.get("appreciation", ""),
        image_path=data.image_path,
        alerte_anomalie=1 if result.get("alerte_anomalie") else 0,
        message_anomalie=result.get("message_anomalie", ""),
        subject_id=data.subject_id,
    )

    # Sauvegarder chaque exercice — cherche le corrigé dans la liste unifiée
    for ex in result.get("exercices", []):
        corrige_match = next(
            (c for c in exercices_corrige if c.get("numero") == ex["numero"]), None
        )
        reponse_match = next(
            (r for r in data.reponses_eleve if r.numero == ex["numero"]), None
        )
        create_exercise(
            exam_id=exam_id,
            numero=ex["numero"],
            enonce=corrige_match.get("enonce", "") if corrige_match else "",
            reponse_eleve=reponse_match.reponse_eleve if reponse_match else "",
            reponse_attendue=corrige_match.get("reponse_attendue", "") if corrige_match else "",
            points_obtenus=ex.get("points_obtenus", 0),
            points_max=ex.get("points_max", 0),
            correct=ex.get("correct", 0),
            feedback=ex.get("feedback", ""),
            erreurs_types=ex.get("erreurs_types", ""),
        )

    result["exam_id"] = exam_id
    logger.info(f"Correction sauvegardée : exam_id={exam_id}, note={result.get('note_totale')}/{result.get('note_sur')}, llm={result.get('llm_used')}")
    return result


@router.post("/quick")
async def grade_quick(data: QuickGradeRequest, prof: dict = Depends(get_current_professor)):
    """
    Quick grading: grade with AI but DON'T save to database.
    Useful for testing or preview.
    """
    logger.info(f"Correction rapide : matière={data.matiere}")
    result = await grade_copy(
        matiere=data.matiere,
        niveau=data.niveau,
        note_sur=data.note_sur,
        exercices_corrige=[ex.model_dump() for ex in data.exercices_corrige],
        reponses_eleve=[r.model_dump() for r in data.reponses_eleve],
        historique=None,
    )
    return result


# ━━━ Copies (exams) ━━━

@router.get("/exams/{exam_id}")
async def get_exam_detail(exam_id: int, prof: dict = Depends(get_current_professor)):
    """Get full detail of a graded exam with all exercises."""
    exam = get_exam_by_id(exam_id)
    if not exam or exam["professor_id"] != prof["id"]:
        raise HTTPException(status_code=404, detail="Copie non trouvée")
    exercises = get_exercises_by_exam(exam_id)
    return {**exam, "exercices": exercises}


@router.delete("/exams/{exam_id}")
async def remove_exam(exam_id: int, prof: dict = Depends(get_current_professor)):
    """Delete an exam and all its exercises."""
    exam = get_exam_by_id(exam_id)
    if not exam or exam["professor_id"] != prof["id"]:
        raise HTTPException(status_code=404, detail="Copie non trouvée")
    delete_exam(exam_id)
    logger.info(f"Copie supprimée : exam_id={exam_id} par prof={prof['id']}")
    return {"message": "Copie supprimée"}
