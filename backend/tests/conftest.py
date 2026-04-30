"""
Fixtures partagées pour les tests Corrector AI.
Configure un client HTTP de test et une base de données temporaire.
"""

import os
import sys
import pytest
from unittest.mock import patch, AsyncMock

# Configurer la base de données de test avant tout import
TEST_DB = os.path.join(os.path.dirname(__file__), "test_corrector.db")
os.environ["DATABASE_PATH"] = TEST_DB

# Supprimer la DB de test si elle existe déjà
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

from httpx import AsyncClient, ASGITransport
from backend.app import app
from backend.models.database import init_db
from backend.auth import create_token


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """Create test database tables once for all tests."""
    init_db()
    yield
    # Nettoyage après les tests
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def auth_headers():
    """Return auth headers with a valid JWT token for prof ID 1."""
    token = create_token(professor_id=1, email="test@corrector.ai")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client():
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def registered_prof(client):
    """Register a test professor and return the response data."""
    resp = await client.post("/api/auth/register", json={
        "nom": "Dupont",
        "prenom": "Jean",
        "email": "jean.dupont@test.fr",
        "password": "test1234",
    })
    return resp.json()


# ━━━ Mocks pour les services IA ━━━

@pytest.fixture
def mock_gemini():
    """Mock du service OCR Gemini."""
    mock_result = {
        "nom_eleve_detecte": "Martin Pierre",
        "exercices": [
            {"numero": 1, "texte_brut": "La Terre tourne autour du Soleil.", "lisibilite": "bonne"},
            {"numero": 2, "texte_brut": "La photosynthèse produit de l'oxygène.", "lisibilite": "moyenne"},
        ],
    }
    with patch("backend.services.vision.extract_text_structured", new_callable=AsyncMock, return_value=mock_result) as m:
        yield m


@pytest.fixture
def mock_claude():
    """Mock du service de correction Claude."""
    mock_result = {
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
                "feedback": "Réponse partielle, il manque le rôle de la chlorophylle.",
                "erreurs_types": "Oubli d'un concept clé",
            },
        ],
        "note_totale": 7.0,
        "note_sur": 10,
        "appreciation": "Copie correcte mais peut mieux faire. Revoir la photosynthèse.",
        "alerte_anomalie": False,
        "message_anomalie": "",
    }
    with patch("backend.services.llm.grade_copy", new_callable=AsyncMock, return_value=mock_result) as m:
        yield m
