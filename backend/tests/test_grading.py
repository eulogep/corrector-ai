"""
Tests pour les routes de correction.
Vérifie la correction rapide (mock LLM) et la sauvegarde en base.
"""

import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from backend.app import app
from backend.auth import create_token
from backend.models.database import init_db, create_professor, create_student, get_exam_by_id
from backend.auth import hash_password

# Résultat mock de la correction
MOCK_GRADE_RESULT = {
    "exercices": [
        {
            "numero": 1,
            "points_obtenus": 4.0,
            "points_max": 5.0,
            "correct": 0,
            "feedback": "Bonne réponse mais manque de précision.",
            "erreurs_types": "",
        },
        {
            "numero": 2,
            "points_obtenus": 3.0,
            "points_max": 5.0,
            "correct": 0,
            "feedback": "Réponse partielle.",
            "erreurs_types": "Oubli concept clé",
        },
    ],
    "note_totale": 7.0,
    "note_sur": 10,
    "appreciation": "Copie correcte mais peut mieux faire.",
    "alerte_anomalie": False,
    "message_anomalie": "",
}


@pytest.fixture(scope="module")
def grading_setup():
    """Create prof + student for grading tests."""
    init_db()
    from backend.models.database import get_professor_by_email
    prof = get_professor_by_email("test_grading@corrector.ai")
    if not prof:
        prof_id = create_professor(
            "GradingProf", "Test", "test_grading@corrector.ai",
            hash_password("pass1234")
        )
    else:
        prof_id = prof["id"]

    student_id = create_student(prof_id, "Eleve", "Test", "4ème C", "eleve@test.fr")
    token = create_token(prof_id, "test_grading@corrector.ai")
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "prof_id": prof_id,
        "student_id": student_id,
    }


@pytest.mark.asyncio
async def test_grade_quick(grading_setup):
    """POST /api/grading/quick — mock LLM, vérifie structure JSON retournée."""
    with patch("backend.routes.grading.grade_copy", new_callable=AsyncMock, return_value=MOCK_GRADE_RESULT):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/grading/quick",
                json={
                    "matiere": "SVT",
                    "niveau": "4ème",
                    "note_sur": 10,
                    "exercices_corrige": [
                        {"numero": 1, "enonce": "Qu'est-ce que la Terre ?", "reponse_attendue": "Une planète", "points_max": 5},
                        {"numero": 2, "enonce": "Photosynthèse ?", "reponse_attendue": "Production O2", "points_max": 5},
                    ],
                    "reponses_eleve": [
                        {"numero": 1, "reponse_eleve": "La Terre est une planète du système solaire."},
                        {"numero": 2, "reponse_eleve": "Les plantes produisent de l'oxygène."},
                    ],
                },
                headers=grading_setup["headers"],
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "exercices" in data
            assert "note_totale" in data
            assert "appreciation" in data
            assert len(data["exercices"]) == 2


@pytest.mark.asyncio
async def test_grade_saves_to_db(grading_setup):
    """POST /api/grading/grade — vérifie que la copie est bien sauvegardée en base."""
    with patch("backend.routes.grading.grade_copy", new_callable=AsyncMock, return_value=MOCK_GRADE_RESULT):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/grading/grade",
                json={
                    "student_id": grading_setup["student_id"],
                    "matiere": "Mathématiques",
                    "niveau": "4ème",
                    "date_examen": "2025-03-15",
                    "note_sur": 10,
                    "exercices_corrige": [
                        {"numero": 1, "enonce": "Calcul", "reponse_attendue": "42", "points_max": 5},
                        {"numero": 2, "enonce": "Géométrie", "reponse_attendue": "Triangle", "points_max": 5},
                    ],
                    "reponses_eleve": [
                        {"numero": 1, "reponse_eleve": "42"},
                        {"numero": 2, "reponse_eleve": "Carré"},
                    ],
                },
                headers=grading_setup["headers"],
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "exam_id" in data

            # Vérifier en base
            exam = get_exam_by_id(data["exam_id"])
            assert exam is not None
            assert exam["matiere"] == "Mathématiques"
            assert exam["note_totale"] == 7.0


async def _create_pilot_exam(client, setup) -> int:
    """Create one AI suggestion in a controlled test context."""
    from copy import deepcopy

    with patch(
        "backend.routes.grading.grade_copy",
        new_callable=AsyncMock,
        return_value=deepcopy(MOCK_GRADE_RESULT),
    ):
        response = await client.post(
            "/api/grading/grade",
            json={
                "student_id": setup["student_id"],
                "matiere": "Pilotage",
                "niveau": "4ème",
                "date_examen": "2026-08-12",
                "note_sur": 10,
                "exercices_corrige": [
                    {"numero": 1, "enonce": "Question", "reponse_attendue": "Réponse", "points_max": 5},
                    {"numero": 2, "enonce": "Question 2", "reponse_attendue": "Réponse 2", "points_max": 5},
                ],
                "reponses_eleve": [
                    {"numero": 1, "reponse_eleve": "Réponse élève 1"},
                    {"numero": 2, "reponse_eleve": "Réponse élève 2"},
                ],
            },
            headers=setup["headers"],
        )
    assert response.status_code == 200, response.text
    return response.json()["exam_id"]


@pytest.mark.asyncio
async def test_teacher_review_preserves_ai_suggestion_and_creates_audit(grading_setup):
    """A teacher can finalise a suggestion without losing the original AI score."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        exam_id = await _create_pilot_exam(client, grading_setup)

        queue = await client.get("/api/grading/reviews/queue?status=pending_review", headers=grading_setup["headers"])
        assert queue.status_code == 200
        assert exam_id in [item["id"] for item in queue.json()["exams"]]

        review = await client.post(
            f"/api/grading/exams/{exam_id}/review",
            json={
                "status": "approved",
                "comment": "Exercice 2 revalorisé après lecture manuelle.",
                "final_note": 8.0,
                "final_appreciation": "Copie validée après revue humaine.",
            },
            headers=grading_setup["headers"],
        )
        assert review.status_code == 200, review.text
        reviewed = review.json()
        assert reviewed["review_status"] == "approved"
        assert reviewed["note_totale"] == 8.0
        assert reviewed["ai_note_totale"] == 7.0
        assert reviewed["reviewed_by"] == grading_setup["prof_id"]

        history = await client.get(
            f"/api/grading/exams/{exam_id}/review-history", headers=grading_setup["headers"]
        )
        assert history.status_code == 200
        event = history.json()["events"][-1]
        assert event["new_status"] == "approved"
        assert event["note_before"] == 7.0
        assert event["note_after"] == 8.0


@pytest.mark.asyncio
async def test_pilot_calibration_and_bulk_review_are_scoped_to_professor(grading_setup):
    """Pilot metrics use human references and bulk actions only touch owned exams."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first_id = await _create_pilot_exam(client, grading_setup)
        second_id = await _create_pilot_exam(client, grading_setup)

        calibration = await client.post(
            "/api/grading/pilot/calibration",
            json={
                "exam_id": first_id,
                "reference_note": 7.5,
                "reference_note_sur": 10,
                "reference_source": "double_correction_humaine",
            },
            headers=grading_setup["headers"],
        )
        assert calibration.status_code == 200, calibration.text

        metrics = await client.get("/api/grading/pilot/metrics", headers=grading_setup["headers"])
        assert metrics.status_code == 200
        payload = metrics.json()
        assert payload["calibration"]["count"] >= 1
        assert payload["calibration"]["mae_sur_20"] is not None

        bulk = await client.post(
            "/api/grading/reviews/bulk",
            json={"exam_ids": [first_id, second_id, second_id], "status": "needs_revision", "comment": "Relecture demandée."},
            headers=grading_setup["headers"],
        )
        assert bulk.status_code == 200, bulk.text
        assert sorted(bulk.json()["updated_exam_ids"]) == sorted([first_id, second_id])


@pytest.mark.asyncio
async def test_final_score_constraints_and_email_review_gate(grading_setup):
    """A report cannot be sent while a suggestion has not been approved by a teacher."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        exam_id = await _create_pilot_exam(client, grading_setup)

        invalid = await client.post(
            f"/api/grading/exams/{exam_id}/review",
            json={"status": "approved", "final_note": 12},
            headers=grading_setup["headers"],
        )
        assert invalid.status_code == 422

        # La barrière de revue est indépendante de la disponibilité SMTP :
        # une proposition non approuvée ne doit jamais aboutir à une erreur
        # de transport qui masquerait le statut métier attendu.
        email = await client.post(
            "/api/reports/email",
            json={"exam_id": exam_id, "to_email": "test@example.test"},
            headers=grading_setup["headers"],
        )
        assert email.status_code == 409
