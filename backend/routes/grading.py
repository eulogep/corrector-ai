"""
Routes de correction — envoi au LLM et sauvegarde en base.
Deux modes : correction complète (avec sauvegarde) et correction rapide (sans).
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from backend.auth import get_current_professor
from backend.models.database import (
    get_student_by_id, get_recent_exams_by_student_matiere,
    create_exam, create_exercise, get_exam_by_id, get_exercises_by_exam,
    delete_exam, get_subject, update_exam_review, get_review_events,
    list_exams_for_review, save_calibration_case, get_pilot_metrics,
)
from backend.services.llm import grade_copy
from backend.services.observability import record_calibration_case, record_review_action

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


class ReviewRequest(BaseModel):
    status: Literal["approved", "needs_revision"]
    comment: str = Field(default="", max_length=1000)
    final_note: float | None = Field(default=None, ge=0)
    final_appreciation: str | None = Field(default=None, max_length=5000)


class BulkReviewRequest(BaseModel):
    exam_ids: list[int] = Field(min_length=1, max_length=100)
    status: Literal["approved", "needs_revision"]
    comment: str = Field(default="", max_length=1000)


class CalibrationRequest(BaseModel):
    exam_id: int
    reference_note: float = Field(ge=0)
    reference_note_sur: float = Field(default=20, gt=0)
    reference_source: str = Field(default="double_correction_humaine", max_length=200)
    notes: str = Field(default="", max_length=2000)


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
    result["review_status"] = "pending_review"
    result["ai_note_totale"] = result.get("note_totale")
    return result


@router.post("/quick")
async def grade_quick(data: QuickGradeRequest, prof: dict = Depends(get_current_professor)):
    """
    Quick grading: grade with AI but DON'T save to database.
    Useful for testing or preview.
    """
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

@router.get("/reviews/queue")
async def review_queue(
    status: Literal["pending_review", "needs_revision", "approved"] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    prof: dict = Depends(get_current_professor),
):
    """List corrections awaiting a teacher decision, scoped to the authenticated professor."""
    exams = list_exams_for_review(prof["id"], status=status, limit=limit)
    return {"exams": exams, "count": len(exams)}


@router.post("/reviews/bulk")
async def review_bulk(data: BulkReviewRequest, prof: dict = Depends(get_current_professor)):
    """Apply the same teacher decision to a bounded set of owned suggestions."""
    unique_ids = list(dict.fromkeys(data.exam_ids))
    updated, missing = [], []
    for exam_id in unique_ids:
        result = update_exam_review(
            exam_id=exam_id,
            professor_id=prof["id"],
            status=data.status,
            comment=data.comment,
        )
        if result is None:
            missing.append(exam_id)
        else:
            updated.append(result["id"])
    for _ in updated:
        record_review_action(data.status)
    return {"updated_exam_ids": updated, "not_found_exam_ids": missing, "status": data.status}


@router.post("/exams/{exam_id}/review")
async def review_exam(exam_id: int, data: ReviewRequest, prof: dict = Depends(get_current_professor)):
    """Record the final teacher decision while preserving the original AI suggestion."""
    exam = get_exam_by_id(exam_id)
    if not exam or exam["professor_id"] != prof["id"]:
        raise HTTPException(status_code=404, detail="Copie non trouvée")
    if data.final_note is not None and data.final_note > exam["note_sur"]:
        raise HTTPException(status_code=422, detail="La note finale ne peut pas dépasser le barème de la copie")
    updated = update_exam_review(
        exam_id=exam_id,
        professor_id=prof["id"],
        status=data.status,
        comment=data.comment,
        final_note=data.final_note,
        final_appreciation=data.final_appreciation,
    )
    record_review_action(data.status)
    return updated


@router.get("/exams/{exam_id}/review-history")
async def review_history(exam_id: int, prof: dict = Depends(get_current_professor)):
    """Return the teacher-facing audit history for one correction."""
    exam = get_exam_by_id(exam_id)
    if not exam or exam["professor_id"] != prof["id"]:
        raise HTTPException(status_code=404, detail="Copie non trouvée")
    return {"exam_id": exam_id, "events": get_review_events(exam_id, prof["id"])}


@router.post("/pilot/calibration")
async def register_calibration(data: CalibrationRequest, prof: dict = Depends(get_current_professor)):
    """Register a human reference score for pilot quality measurement, never for automatic grading."""
    exam = get_exam_by_id(data.exam_id)
    if not exam or exam["professor_id"] != prof["id"]:
        raise HTTPException(status_code=404, detail="Copie non trouvée")
    if data.reference_note > data.reference_note_sur:
        raise HTTPException(status_code=422, detail="La note de référence ne peut pas dépasser son barème")
    case = save_calibration_case(
        exam_id=data.exam_id,
        professor_id=prof["id"],
        reference_note=data.reference_note,
        reference_note_sur=data.reference_note_sur,
        reference_source=data.reference_source,
        notes=data.notes,
    )
    record_calibration_case("submitted")
    return case


@router.get("/pilot/metrics")
async def pilot_metrics(prof: dict = Depends(get_current_professor)):
    """Expose pilot review and accuracy indicators for the authenticated professor only."""
    return get_pilot_metrics(prof["id"])


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
    return {"message": "Copie supprimée"}
