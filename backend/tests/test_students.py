"""
Tests pour les routes de gestion des élèves.
Vérifie le CRUD complet et la progression.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from backend.app import app
from backend.auth import create_token
from backend.models.database import init_db, create_professor
from backend.auth import hash_password


@pytest.fixture(scope="module")
def prof_token():
    """Create a real professor in DB and return a valid token."""
    init_db()
    try:
        from backend.models.database import get_professor_by_email
        prof = get_professor_by_email("test_students@corrector.ai")
        if not prof:
            prof_id = create_professor(
                "TestProf", "Students", "test_students@corrector.ai",
                hash_password("pass1234")
            )
        else:
            prof_id = prof["id"]
    except Exception:
        prof_id = create_professor(
            "TestProf", "Students", "test_students@corrector.ai",
            hash_password("pass1234")
        )
    token = create_token(prof_id, "test_students@corrector.ai")
    return {"Authorization": f"Bearer {token}", "prof_id": prof_id}


@pytest.mark.asyncio
async def test_create_student(prof_token):
    """POST /api/students/ → 200 + id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/students/",
            json={"nom": "Martin", "prenom": "Pierre", "classe": "3ème B", "email": "pierre@ecole.fr"},
            headers={"Authorization": prof_token["Authorization"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["id"] > 0


@pytest.mark.asyncio
async def test_list_students(prof_token):
    """GET /api/students/ → 200 + liste non vide."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # D'abord créer un élève
        await client.post(
            "/api/students/",
            json={"nom": "Duval", "prenom": "Marie", "classe": "3ème B"},
            headers={"Authorization": prof_token["Authorization"]},
        )
        # Puis lister
        resp = await client.get(
            "/api/students/",
            headers={"Authorization": prof_token["Authorization"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "students" in data
        assert len(data["students"]) >= 1


@pytest.mark.asyncio
async def test_get_student_progression(prof_token):
    """Progression vide pour un nouvel élève."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Créer un nouvel élève
        resp = await client.post(
            "/api/students/",
            json={"nom": "Nouveau", "prenom": "Eleve", "classe": "6ème A"},
            headers={"Authorization": prof_token["Authorization"]},
        )
        student_id = resp.json()["id"]

        # Vérifier la progression
        resp = await client.get(
            f"/api/students/{student_id}/progression",
            headers={"Authorization": prof_token["Authorization"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["nb_exams"] == 0
        assert data["progression"] == {}


@pytest.mark.asyncio
async def test_orphaned_professor_token_is_rejected():
    """Un JWT dont le professeur a disparu doit être rejeté avec 401, jamais avec 500."""
    transport = ASGITransport(app=app)
    orphan_token = create_token(9_999_999, "orphaned@corrector.ai")
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/students/",
            json={"nom": "Test", "prenom": "Orphelin", "classe": "4ème A"},
            headers={"Authorization": f"Bearer {orphan_token}"},
        )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Session expirée. Connectez-vous à nouveau."
