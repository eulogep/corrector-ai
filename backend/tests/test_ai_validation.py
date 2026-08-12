"""Tests des contrats stricts et des erreurs IA contrôlées."""

import io
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app import app
from backend.auth import create_token, hash_password
from backend.models.database import create_professor, get_professor_by_email, init_db
from backend.schemas.ai_outputs import (
    GradingResult,
    OCRStructuredResult,
    decode_json_response,
    validate_grading_result,
)
from backend.services.exceptions import (
    AIConfigurationError,
    AIOutputValidationError,
)
from backend.services.llm import grade_copy


VALID_GRADE = {
    "exercices": [
        {
            "numero": 1,
            "points_obtenus": 4.0,
            "points_max": 5.0,
            "correct": False,
            "feedback": "Réponse globalement correcte.",
            "erreurs_types": "",
        },
        {
            "numero": 2,
            "points_obtenus": 3.0,
            "points_max": 5.0,
            "correct": False,
            "feedback": "Réponse partielle.",
            "erreurs_types": "Justification incomplète.",
        },
    ],
    "note_totale": 7.0,
    "note_sur": 10.0,
    "appreciation": "Copie sérieuse à approfondir.",
    "alerte_anomalie": False,
    "message_anomalie": "",
}


@pytest.fixture(scope="module")
def ai_token():
    """Créer un utilisateur authentifié pour les tests de route IA."""
    init_db()
    professor = get_professor_by_email("test_ai_validation@corrector.ai")
    if not professor:
        professor_id = create_professor(
            "Validation", "IA", "test_ai_validation@corrector.ai", hash_password("pass1234")
        )
    else:
        professor_id = professor["id"]
    return {"Authorization": f"Bearer {create_token(professor_id, 'test_ai_validation@corrector.ai')}"}


def test_ocr_contract_rejects_unexpected_fields():
    """Une clé ajoutée par un modèle doit invalider la sortie OCR."""
    raw = """{
      "nom_eleve_detecte": null,
      "exercices": [{"numero": 1, "texte_brut": "Bonjour", "lisibilite": "bonne"}],
      "commentaire": "clé non autorisée"
    }"""

    with pytest.raises(AIOutputValidationError) as error:
        decode_json_response(raw, OCRStructuredResult, provider="gemini")

    assert error.value.status_code == 502
    assert error.value.code == "ai_invalid_response"


def test_ocr_contract_rejects_invalid_enum():
    """Une valeur de lisibilité hors contrat doit être refusée."""
    raw = """{
      "nom_eleve_detecte": null,
      "exercices": [{"numero": 1, "texte_brut": "Bonjour", "lisibilite": "incertaine"}]
    }"""

    with pytest.raises(AIOutputValidationError):
        decode_json_response(raw, OCRStructuredResult, provider="gemini")


def test_grading_contract_rejects_wrong_score_and_exercise_set():
    """Une note incohérente ou un exercice absent ne peut pas être utilisée."""
    result = GradingResult.model_validate(VALID_GRADE)

    with pytest.raises(AIOutputValidationError):
        validate_grading_result(
            result,
            expected_exercises=[
                {"numero": 1, "points_max": 5.0},
                {"numero": 3, "points_max": 5.0},
            ],
            requested_note_sur=10.0,
        )



@pytest.mark.asyncio
async def test_grade_copy_without_provider_raises_configuration_error_async():
    """Sans clé fournisseur, le service refuse explicitement la correction."""
    with patch("backend.services.llm.ANTHROPIC_API_KEY", ""), patch(
        "backend.services.llm.DEEPSEEK_API_KEY", ""
    ):
        with pytest.raises(AIConfigurationError) as error:
            await grade_copy(
                matiere="Mathématiques",
                niveau="4ème",
                note_sur=10.0,
                exercices_corrige=[
                    {"numero": 1, "enonce": "Calcul", "reponse_attendue": "2", "points_max": 5.0},
                    {"numero": 2, "enonce": "Géométrie", "reponse_attendue": "Carré", "points_max": 5.0},
                ],
                reponses_eleve=[
                    {"numero": 1, "reponse_eleve": "2"},
                    {"numero": 2, "reponse_eleve": "Carré"},
                ],
            )

    assert error.value.status_code == 503
    assert error.value.code == "ai_provider_not_configured"


@pytest.mark.asyncio
async def test_ocr_endpoint_returns_explicit_503_when_unconfigured(ai_token):
    """L'API OCR doit exposer une erreur structurée 503 sans donnée simulée."""
    fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    with patch("backend.services.vision.GEMINI_API_KEY", ""):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/ocr/simple",
                files={"file": ("test.png", fake_image, "image/png")},
                headers=ai_token,
            )

    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"]["code"] == "ai_provider_not_configured"
    assert payload["detail"]["provider"] == "gemini"


@pytest.mark.asyncio
async def test_grading_endpoint_returns_explicit_503_when_unconfigured(ai_token):
    """La correction HTTP ne doit pas produire de note simulée sans fournisseur."""
    payload = {
        "matiere": "Mathématiques",
        "niveau": "4ème",
        "note_sur": 10.0,
        "exercices_corrige": [
            {"numero": 1, "enonce": "Calcul", "reponse_attendue": "2", "points_max": 5.0},
            {"numero": 2, "enonce": "Géométrie", "reponse_attendue": "Carré", "points_max": 5.0},
        ],
        "reponses_eleve": [
            {"numero": 1, "reponse_eleve": "2"},
            {"numero": 2, "reponse_eleve": "Carré"},
        ],
    }

    with patch("backend.services.llm.ANTHROPIC_API_KEY", ""), patch(
        "backend.services.llm.DEEPSEEK_API_KEY", ""
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/grading/quick", json=payload, headers=ai_token
            )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "ai_provider_not_configured"
    assert detail["provider"] == "correction"
