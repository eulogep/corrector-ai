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
