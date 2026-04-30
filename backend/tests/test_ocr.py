"""
Tests pour les routes OCR.
Vérifie l'extraction avec mock Gemini.
"""

import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from backend.app import app
from backend.auth import create_token
from backend.models.database import init_db, create_professor
from backend.auth import hash_password
import io

MOCK_OCR_SIMPLE = "[Mock] Exercice 1 : Réponse de l'élève."

MOCK_OCR_STRUCTURED = {
    "nom_eleve_detecte": "Martin Pierre",
    "exercices": [
        {"numero": 1, "texte_brut": "La Terre est ronde.", "lisibilite": "bonne"},
    ],
}


@pytest.fixture(scope="module")
def ocr_token():
    """Create a professor for OCR tests."""
    init_db()
    from backend.models.database import get_professor_by_email
    prof = get_professor_by_email("test_ocr@corrector.ai")
    if not prof:
        prof_id = create_professor(
            "OCRProf", "Test", "test_ocr@corrector.ai",
            hash_password("pass1234")
        )
    else:
        prof_id = prof["id"]
    token = create_token(prof_id, "test_ocr@corrector.ai")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_extract_simple_mock(ocr_token):
    """POST /api/ocr/simple — mock Gemini, vérifie retour texte."""
    with patch("backend.routes.ocr.extract_text_simple", new_callable=AsyncMock, return_value=MOCK_OCR_SIMPLE):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Créer un faux fichier image
            fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            resp = await client.post(
                "/api/ocr/simple",
                files={"file": ("test.png", fake_image, "image/png")},
                headers={"Authorization": ocr_token["Authorization"]},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "text" in data
            assert "Mock" in data["text"]


@pytest.mark.asyncio
async def test_extract_structured_mock(ocr_token):
    """POST /api/ocr/extract — mock Gemini, vérifie retour JSON structuré."""
    with patch("backend.routes.ocr.extract_text_structured", new_callable=AsyncMock, return_value=MOCK_OCR_STRUCTURED):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            resp = await client.post(
                "/api/ocr/extract",
                files={"file": ("test.png", fake_image, "image/png")},
                headers={"Authorization": ocr_token["Authorization"]},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "exercices" in data
            assert len(data["exercices"]) >= 1
            assert data["exercices"][0]["numero"] == 1
