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


def _mock_storage(tmp_path):
    """Patch save_uploaded_bytes pour éviter toute dépendance réseau dans les tests."""
    import tempfile
    import os
    async def _fake_save(*, professor_id, category, filename, content, content_type):
        p = os.path.join(str(tmp_path), filename)
        with open(p, "wb") as f:
            f.write(content)
        return p, p
    return patch("backend.routes.ocr.save_uploaded_bytes", new=AsyncMock(side_effect=_fake_save))


@pytest.mark.asyncio
async def test_extract_simple_mock(ocr_token, tmp_path):
    """POST /api/ocr/simple — mock Gemini et stockage, vérifie retour texte."""
    with _mock_storage(tmp_path), patch("backend.routes.ocr.extract_text_simple", new_callable=AsyncMock, return_value=MOCK_OCR_SIMPLE):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
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
async def test_extract_structured_mock(ocr_token, tmp_path):
    """POST /api/ocr/extract — mock Gemini et stockage, vérifie retour JSON structuré."""
    with _mock_storage(tmp_path), patch("backend.routes.ocr.extract_text_structured", new_callable=AsyncMock, return_value=MOCK_OCR_STRUCTURED):
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


@pytest.mark.asyncio
async def test_extract_returns_explicit_error_when_persistent_storage_fails(ocr_token):
    """Une copie ne doit jamais sembler acceptée si le stockage durable la refuse."""
    from backend.services.persistent_storage import PersistentStorageError

    with patch(
        "backend.routes.ocr.save_uploaded_bytes",
        new=AsyncMock(side_effect=PersistentStorageError("Stockage persistant non configuré.")),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            resp = await client.post(
                "/api/ocr/simple",
                files={"file": ("test.png", fake_image, "image/png")},
                headers={"Authorization": ocr_token["Authorization"]},
            )

    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "persistent_storage_unavailable"
