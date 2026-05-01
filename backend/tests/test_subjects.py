"""
Tests pour les routes subjects et le service subject_parser.
Utilise un PDF généré à la volée via reportlab pour l'upload.
Tous les appels IA (Claude, Docling) sont mockés.
"""

import io
import os
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from backend.app import app
from backend.auth import create_token, hash_password
from backend.models.database import (
    init_db, create_professor, create_student, get_professor_by_email,
    save_subject, get_subject, list_subjects,
)


# ━━━ Barème mock retourné par Claude ━━━
MOCK_BAREME = {
    "matiere_detectee": "Mathématiques",
    "niveau_detecte": "lycée",
    "total_points": 20,
    "exercices": [
        {
            "numero": 1,
            "enonce": "Résoudre 2x + 3 = 7",
            "reponse_attendue": "x = 2",
            "points_max": 7,
            "sous_questions": [],
            "type": "calcul",
        },
        {
            "numero": 2,
            "enonce": "Calculer la dérivée de f(x) = x^2",
            "reponse_attendue": "f'(x) = 2x",
            "points_max": 7,
            "sous_questions": [],
            "type": "calcul",
        },
        {
            "numero": 3,
            "enonce": "Donner la définition d'une fonction",
            "reponse_attendue": "Relation entre deux ensembles",
            "points_max": 6,
            "sous_questions": [],
            "type": "redaction",
        },
    ],
    "confiance": 0.92,
    "remarques": "Barème détecté clairement depuis le sujet",
}


def _build_test_pdf() -> bytes:
    """Generate a minimal PDF in memory for upload tests."""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "Contrôle de Mathématiques")
    c.drawString(100, 720, "Exercice 1 : Résoudre 2x + 3 = 7")
    c.drawString(100, 690, "Exercice 2 : Derivée de x^2")
    c.drawString(100, 660, "Exercice 3 : Définition d'une fonction")
    c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture(scope="module")
def subject_setup():
    """Create prof + student + auth headers for subject tests."""
    init_db()
    prof = get_professor_by_email("test_subjects@corrector.ai")
    if not prof:
        prof_id = create_professor(
            "SubjectProf", "Test", "test_subjects@corrector.ai", hash_password("pass1234")
        )
    else:
        prof_id = prof["id"]
    student_id = create_student(prof_id, "Dupont", "Jean", "Terminale S", "jd@test.fr")
    token = create_token(prof_id, "test_subjects@corrector.ai")
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "prof_id": prof_id,
        "student_id": student_id,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 1 — parse_subject service-level (mock Claude)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.asyncio
async def test_parse_subject_mock(tmp_path):
    """Parse un PDF → mock Claude → vérifie structure JSON."""
    from backend.services import subject_parser

    pdf_path = tmp_path / "sujet_test.pdf"
    pdf_path.write_bytes(_build_test_pdf())

    with patch.object(subject_parser, "_generate_bareme_with_claude", return_value=MOCK_BAREME):
        result = await subject_parser.parse_subject(str(pdf_path))

    assert isinstance(result, dict)
    assert "exercices" in result
    assert isinstance(result["exercices"], list)
    assert len(result["exercices"]) > 0
    assert result["total_points"] == 20
    assert result["matiere_detectee"] == "Mathématiques"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 2 — endpoint POST /api/subjects/parse
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.asyncio
async def test_parse_endpoint(subject_setup):
    """POST /api/subjects/parse avec un PDF → status 200 + clés attendues."""
    pdf_bytes = _build_test_pdf()

    # On patch parse_subject au niveau du module route (import local)
    async def _fake_parse(_path):
        return {**MOCK_BAREME, "pdf_path": _path}

    with patch("backend.routes.subjects.parse_subject", new=AsyncMock(side_effect=_fake_parse)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/subjects/parse",
                files={"file": ("sujet.pdf", pdf_bytes, "application/pdf")},
                headers=subject_setup["headers"],
            )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "exercices" in data
    assert "total_points" in data
    assert "confiance" in data
    assert len(data["exercices"]) == 3
    assert data["matiere_detectee"] == "Mathématiques"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 3 — validate + retrieve round-trip
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.asyncio
async def test_validate_and_retrieve(subject_setup):
    """POST /validate → GET /{id} : vérifie cohérence du barème sauvegardé."""
    payload = {
        "matiere": "Mathématiques",
        "niveau": "Terminale",
        "titre": "DS n°1",
        "total_points": 20,
        "exercices": MOCK_BAREME["exercices"],
        "pdf_path": "/tmp/sujet.pdf",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post(
            "/api/subjects/validate",
            json=payload,
            headers=subject_setup["headers"],
        )
        assert r1.status_code == 200, r1.text
        subject_id = r1.json()["subject_id"]
        assert isinstance(subject_id, int)

        r2 = await client.get(
            f"/api/subjects/{subject_id}",
            headers=subject_setup["headers"],
        )
        assert r2.status_code == 200
        sub = r2.json()
        assert sub["matiere"] == "Mathématiques"
        assert sub["niveau"] == "Terminale"
        assert len(sub["exercices"]) == 3
        assert sub["exercices"][0]["numero"] == 1

        # Liste aussi disponible
        r3 = await client.get("/api/subjects/", headers=subject_setup["headers"])
        assert r3.status_code == 200
        ids = [s["id"] for s in r3.json()["subjects"]]
        assert subject_id in ids


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 4 — grade with subject_id charge le barème depuis DB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MOCK_GRADE_RESULT = {
    "exercices": [
        {"numero": 1, "points_obtenus": 6.0, "points_max": 7.0, "correct": 0,
         "feedback": "OK", "erreurs_types": ""},
        {"numero": 2, "points_obtenus": 5.0, "points_max": 7.0, "correct": 0,
         "feedback": "Bien", "erreurs_types": ""},
        {"numero": 3, "points_obtenus": 4.0, "points_max": 6.0, "correct": 0,
         "feedback": "Correct", "erreurs_types": ""},
    ],
    "note_totale": 15.0,
    "note_sur": 20,
    "appreciation": "Bon travail.",
    "alerte_anomalie": False,
    "message_anomalie": "",
}


@pytest.mark.asyncio
async def test_grade_with_subject_id(subject_setup):
    """POST /api/grading/grade avec subject_id → utilise le barème DB."""
    # 1. Créer le sujet directement en DB
    subj_id = save_subject(subject_setup["prof_id"], {
        "matiere": "Mathématiques",
        "niveau": "Terminale",
        "titre": "DS auto",
        "total_points": 20,
        "exercices": MOCK_BAREME["exercices"],
        "pdf_path": "",
    })

    # 2. Appeler /grade avec subject_id — pas d'exercices_corrige dans le body
    captured = {}

    async def _capture_grade(**kwargs):
        captured.update(kwargs)
        return MOCK_GRADE_RESULT

    with patch("backend.routes.grading.grade_copy", new=AsyncMock(side_effect=_capture_grade)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/grading/grade",
                json={
                    "student_id": subject_setup["student_id"],
                    "matiere": "Mathématiques",
                    "niveau": "Terminale",
                    "note_sur": 20,
                    "subject_id": subj_id,
                    "reponses_eleve": [
                        {"numero": 1, "reponse_eleve": "x = 2"},
                        {"numero": 2, "reponse_eleve": "2x"},
                        {"numero": 3, "reponse_eleve": "Une relation"},
                    ],
                },
                headers=subject_setup["headers"],
            )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "exam_id" in data

    # Le barème transmis à grade_copy doit venir du subject
    passed_corrige = captured.get("exercices_corrige", [])
    assert len(passed_corrige) == 3
    assert passed_corrige[0]["numero"] == 1
    assert passed_corrige[0]["reponse_attendue"] == "x = 2"
    assert passed_corrige[0]["points_max"] == 7
