"""Tests des contrats stricts et des erreurs IA contrôlées."""

import io
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

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



def test_ocr_contract_rejects_duplicate_exercise_numbers():
    """Deux exercices OCR portant le même numéro doivent être refusés."""
    with pytest.raises(ValidationError):
        OCRStructuredResult.model_validate(
            {
                "nom_eleve_detecte": None,
                "exercices": [
                    {"numero": 1, "texte_brut": "Réponse A", "lisibilite": "bonne"},
                    {"numero": 1, "texte_brut": "Réponse B", "lisibilite": "moyenne"},
                ],
            }
        )


def test_grading_contract_rejects_integer_for_boolean():
    """Une sortie LLM ne peut pas convertir implicitement 0 ou 1 en booléen."""
    invalid_grade = {**VALID_GRADE}
    invalid_grade["exercices"] = [
        {**VALID_GRADE["exercices"][0], "correct": 1},
        VALID_GRADE["exercices"][1],
    ]

    with pytest.raises(ValidationError):
        GradingResult.model_validate(invalid_grade)


def test_grading_contract_rejects_total_mismatch():
    """Une note totale différente de la somme des exercices est invalide."""
    invalid_grade = {**VALID_GRADE, "note_totale": 6.5}

    with pytest.raises(ValidationError):
        GradingResult.model_validate(invalid_grade)


@pytest.mark.asyncio
async def test_subject_validation_rejects_inconsistent_total(ai_token):
    """L'API refuse un barème dont le total ne correspond pas aux exercices."""
    payload = {
        "matiere": "Mathématiques",
        "niveau": "4ème",
        "total_points": 20.0,
        "exercices": [
            {
                "numero": 1,
                "enonce": "Calcul",
                "reponse_attendue": "2",
                "points_max": 5.0,
                "type": "calcul",
                "sous_questions": [],
            }
        ],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/subjects/validate", json=payload, headers=ai_token)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_healthz_and_metrics_authentication():
    """La santé est publique mais les métriques nécessitent un jeton distinct."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/healthz", headers={"X-Request-ID": "trace-test"})
        disabled_metrics = await client.get("/metrics")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert health.headers["X-Request-ID"] == "trace-test"
    assert "X-Response-Time-Ms" in health.headers
    assert disabled_metrics.status_code == 503


@pytest.mark.asyncio
async def test_metrics_returns_prometheus_payload_with_valid_token():
    """Les métriques Prometheus sont disponibles avec le jeton de service configuré."""
    with patch("backend.app.METRICS_TOKEN", "metrics-test-token"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            denied = await client.get("/metrics", headers={"X-Metrics-Token": "wrong"})
            authorized = await client.get(
                "/metrics", headers={"Authorization": "Bearer metrics-test-token"}
            )

    assert denied.status_code == 403
    assert authorized.status_code == 200
    assert "corrector_ai_ai_calls_total" in authorized.text



def test_decoder_accepts_a_complete_fenced_json_response():
    """Un JSON proprement encadré par Markdown reste accepté pour tolérer certains fournisseurs."""
    raw = """```json
{
  "nom_eleve_detecte": null,
  "exercices": [{"numero": 1, "texte_brut": "Réponse", "lisibilite": "bonne"}]
}
```"""

    result = decode_json_response(raw, OCRStructuredResult, provider="gemini")
    assert result.exercices[0].numero == 1


def test_subject_rubric_contract_rejects_point_total_mismatch():
    """Un barème LLM dont les points ne totalisent pas le maximum annoncé est inutilisable."""
    from backend.schemas.ai_outputs import SubjectRubric

    with pytest.raises(ValidationError):
        SubjectRubric.model_validate(
            {
                "matiere_detectee": "Mathématiques",
                "niveau_detecte": "4ème",
                "total_points": 20.0,
                "exercices": [
                    {
                        "numero": 1,
                        "enonce": "Calcul",
                        "reponse_attendue": "2",
                        "points_max": 5.0,
                        "sous_questions": [],
                        "type": "calcul",
                    }
                ],
                "confiance": 0.8,
                "remarques": "",
            }
        )


@pytest.mark.asyncio
async def test_grade_copy_uses_deepseek_when_claude_fails():
    """Le repli fournisseur est conservé mais uniquement avec une sortie validée."""
    from unittest.mock import AsyncMock
    from backend.services import llm, retry
    from backend.services.exceptions import AIProviderUnavailableError

    valid_result = GradingResult.model_validate(VALID_GRADE)
    with patch("backend.services.llm.ANTHROPIC_API_KEY", "claude-test"), patch(
        "backend.services.llm.DEEPSEEK_API_KEY", "deepseek-test"
    ), patch.object(
        llm,
        "_grade_with_claude",
        new=AsyncMock(side_effect=AIProviderUnavailableError("claude", "indisponible")),
    ), patch.object(llm, "_grade_with_deepseek", new=AsyncMock(return_value=valid_result)), patch.object(
        retry, "LLM_RETRY_MAX_ATTEMPTS", 1
    ):
        result = await grade_copy(
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

    assert result["llm_used"] == "deepseek"
    assert result["note_totale"] == 7.0


@pytest.mark.asyncio
async def test_ocr_service_validates_a_provider_response():
    """L’OCR instrumenté conserve le contrat strict pour une réponse fournisseur valide."""
    from backend.services import vision

    raw = """{
      "nom_eleve_detecte": null,
      "exercices": [{"numero": 1, "texte_brut": "Réponse", "lisibilite": "bonne"}]
    }"""
    with patch.object(vision, "_generate_content", return_value=raw):
        result = await vision.extract_text_structured("/tmp/fichier-non-utilise.png")

    assert result["exercices"][0]["texte_brut"] == "Réponse"


@pytest.mark.asyncio
async def test_retry_uses_exponential_backoff_then_succeeds():
    """Un échec transitoire est réessayé avec un délai exponentiel borné."""
    from unittest.mock import AsyncMock
    from backend.services import retry
    from backend.services.exceptions import AIProviderUnavailableError

    call = AsyncMock(
        side_effect=[
            AIProviderUnavailableError("claude", "indisponible"),
            AIProviderUnavailableError("claude", "indisponible"),
            "résultat",
        ]
    )
    sleep = AsyncMock()
    with patch.object(retry, "LLM_RETRY_MAX_ATTEMPTS", 3), patch.object(
        retry, "LLM_RETRY_BASE_SECONDS", 0.5
    ), patch.object(retry, "LLM_RETRY_MAX_SECONDS", 4.0), patch.object(
        retry.random, "uniform", return_value=1.0
    ), patch.object(retry.asyncio, "sleep", sleep):
        result = await retry.call_with_exponential_backoff(
            provider="claude", operation="grading", call=call
        )

    assert result == "résultat"
    assert call.await_count == 3
    assert [awaited.args[0] for awaited in sleep.await_args_list] == [0.5, 1.0]


@pytest.mark.asyncio
async def test_retry_does_not_repeat_invalid_llm_output():
    """Une sortie de contrat invalide ne doit jamais être répétée auprès du fournisseur."""
    from unittest.mock import AsyncMock
    from backend.services import retry

    call = AsyncMock(side_effect=AIOutputValidationError("claude", "JSON invalide"))
    sleep = AsyncMock()
    with patch.object(retry.asyncio, "sleep", sleep):
        with pytest.raises(AIOutputValidationError):
            await retry.call_with_exponential_backoff(
                provider="claude", operation="grading", call=call
            )

    assert call.await_count == 1
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_subject_rubric_falls_back_to_deepseek_when_claude_fails():
    """La génération de barème utilise DeepSeek après épuisement de Claude."""
    from unittest.mock import AsyncMock
    from backend.services import subject_parser
    from backend.schemas.ai_outputs import SubjectRubric
    from backend.services.exceptions import AIProviderUnavailableError

    rubric = SubjectRubric.model_validate(
        {
            "matiere_detectee": "Mathématiques",
            "niveau_detecte": "4ème",
            "total_points": 10.0,
            "exercices": [
                {
                    "numero": 1,
                    "enonce": "Calcul",
                    "reponse_attendue": "2",
                    "points_max": 10.0,
                    "sous_questions": [],
                    "type": "calcul",
                }
            ],
            "confiance": 0.9,
            "remarques": "",
        }
    )
    with patch("backend.services.subject_parser.ANTHROPIC_API_KEY", "claude-test"), patch(
        "backend.services.subject_parser.DEEPSEEK_API_KEY", "deepseek-test"
    ), patch.object(
        subject_parser,
        "_generate_bareme_with_claude",
        new=AsyncMock(side_effect=AIProviderUnavailableError("claude", "indisponible")),
    ), patch.object(
        subject_parser, "_generate_bareme_with_deepseek", new=AsyncMock(return_value=rubric)
    ):
        result, provider = await subject_parser._generate_bareme_with_fallback("sujet", "docling")

    assert provider == "deepseek"
    assert result.total_points == 10.0
