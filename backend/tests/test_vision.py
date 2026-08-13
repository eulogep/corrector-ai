"""Tests unitaires de la chaîne OCR multimodale sans appel réseau réel."""

import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.services import vision
from backend.services.exceptions import AIProviderUnavailableError


def test_generate_content_uses_configured_stable_gemini_model(tmp_path):
    """Le modèle OCR Gemini reste configurable et appelé via le SDK officiel."""
    image_path = tmp_path / "copy.png"
    image_path.write_bytes(b"synthetic-image")

    fake_response = SimpleNamespace(text="{}")
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response
    fake_client_factory = MagicMock()
    fake_client_factory.return_value.__enter__.return_value = fake_client

    with (
        patch.object(vision, "GEMINI_API_KEY", "test-key"),
        patch.object(vision, "GEMINI_OCR_MODEL", "gemini-3.5-flash"),
        patch("google.genai.Client", fake_client_factory),
    ):
        result = vision._generate_content("OCR prompt", str(image_path))

    assert result == "{}"
    fake_client_factory.assert_called_once_with(api_key="test-key")
    fake_client.models.generate_content.assert_called_once()

    call_kwargs = fake_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-3.5-flash"
    text_part, image_part = call_kwargs["contents"]
    assert text_part.text == "OCR prompt"
    assert image_part.inline_data.mime_type == "image/png"
    assert image_part.inline_data.data == b"synthetic-image"


def test_generate_content_with_claude_encodes_supported_image(tmp_path):
    """Le repli Claude transmet une image encodée et ne construit aucun résultat simulé."""
    image_path = tmp_path / "copy.png"
    image_path.write_bytes(b"synthetic-image")

    fake_response = SimpleNamespace(content=[SimpleNamespace(type="text", text="{}")])
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response
    fake_factory = MagicMock(return_value=fake_client)

    with (
        patch.object(vision, "ANTHROPIC_API_KEY", "test-anthropic-key"),
        patch.object(vision, "CLAUDE_OCR_MODEL", "claude-sonnet-4-20250514"),
        patch("anthropic.Anthropic", fake_factory),
    ):
        result = vision._generate_content_with_claude("OCR prompt", str(image_path))

    assert result == "{}"
    fake_factory.assert_called_once_with(api_key="test-anthropic-key")
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-20250514"
    visual_part = call_kwargs["messages"][0]["content"][1]
    assert visual_part["type"] == "image"
    assert visual_part["source"]["media_type"] == "image/png"
    assert visual_part["source"]["data"] == base64.b64encode(b"synthetic-image").decode("ascii")


def test_structured_ocr_falls_back_to_claude_after_gemini_failure(tmp_path):
    """Une indisponibilité Gemini déclenche le repli Claude et sa validation Pydantic."""
    image_path = tmp_path / "copy.png"
    image_path.write_bytes(b"synthetic-image")
    valid_ocr_json = (
        '{"nom_eleve_detecte":null,"exercices":['
        '{"numero":1,"texte_brut":"Réponse élève","lisibilite":"bonne"}]}'
    )

    async def single_attempt(**kwargs):
        return await kwargs["call"]()

    with (
        patch.object(vision, "GEMINI_API_KEY", "test-gemini-key"),
        patch.object(vision, "ANTHROPIC_API_KEY", "test-anthropic-key"),
        patch.object(
            vision,
            "_generate_content",
            side_effect=AIProviderUnavailableError("gemini", "Indisponible"),
        ) as gemini,
        patch.object(vision, "_generate_content_with_claude", return_value=valid_ocr_json) as claude,
        patch.object(vision, "call_with_exponential_backoff", side_effect=single_attempt),
    ):
        result = asyncio.run(vision.extract_text_structured(str(image_path)))

    assert result == {
        "nom_eleve_detecte": None,
        "exercices": [
            {"numero": 1, "texte_brut": "Réponse élève", "lisibilite": "bonne"}
        ],
    }
    gemini.assert_called_once()
    claude.assert_called_once()


def test_safe_gemini_error_message_classifies_common_provider_failures():
    """Les diagnostics opérationnels ne doivent révéler ni détail brut ni secret."""
    permission_error = type("PermissionDenied", (Exception,), {})()
    quota_error = type("ResourceExhausted", (Exception,), {})()
    model_error = type("NotFound", (Exception,), {})()
    sdk_model_error = type("ClientError", (Exception,), {"code": 404})()
    sdk_invalid_key_error = type("ClientError", (Exception,), {"code": 400})(
        "API key not valid. Please pass a valid API key."
    )

    assert "accès à gemini" in vision._safe_gemini_error_message(permission_error).lower()
    assert "quota" in vision._safe_gemini_error_message(quota_error).lower()
    assert "modèle gemini" in vision._safe_gemini_error_message(model_error).lower()
    assert "modèle gemini" in vision._safe_gemini_error_message(sdk_model_error).lower()
    assert "authentification gemini" in vision._safe_gemini_error_message(sdk_invalid_key_error).lower()
    assert "fournisseur ocr gemini" in vision._safe_gemini_error_message(Exception("raw")).lower()


def test_safe_claude_error_message_classifies_authentication_failure():
    """Les erreurs du repli Claude restent assainies et actionnables."""
    auth_error = type("AuthenticationError", (Exception,), {})()

    assert "authentification claude" in vision._safe_claude_error_message(auth_error).lower()
    assert "fournisseur ocr claude" in vision._safe_claude_error_message(Exception("raw")).lower()


def test_generate_content_with_easyocr_derives_structured_contract(tmp_path):
    """EasyOCR encapsule le texte détecté dans le contrat OCR sans le fabriquer."""
    image_path = tmp_path / "copy.png"
    image_path.write_bytes(b"synthetic-image")
    fake_reader = MagicMock()
    fake_reader.readtext.return_value = [
        (None, "Réponse détectée", 0.92),
        (None, "suite", 0.80),
    ]

    with patch("easyocr.Reader", return_value=fake_reader):
        raw = vision._generate_content_with_easyocr(vision.OCR_PROMPT, str(image_path))

    assert raw == (
        '{"nom_eleve_detecte": null, "exercices": '
        '[{"numero": 1, "texte_brut": "Réponse détectée\\nsuite", "lisibilite": "bonne"}]}'
    )


def test_structured_ocr_falls_back_to_easyocr_when_enabled(tmp_path):
    """Le moteur local n’est sollicité qu’après l’échec Gemini et quand il est explicitement activé."""
    image_path = tmp_path / "copy.png"
    image_path.write_bytes(b"synthetic-image")
    valid_ocr_json = (
        '{"nom_eleve_detecte":null,"exercices":['
        '{"numero":1,"texte_brut":"Texte local","lisibilite":"moyenne"}]}'
    )

    async def single_attempt(**kwargs):
        return await kwargs["call"]()

    with (
        patch.object(vision, "GEMINI_API_KEY", "test-gemini-key"),
        patch.object(vision, "ANTHROPIC_API_KEY", ""),
        patch.object(vision, "LOCAL_OCR_FALLBACK_ENABLED", True),
        patch.object(
            vision,
            "_generate_content",
            side_effect=AIProviderUnavailableError("gemini", "Indisponible"),
        ) as gemini,
        patch.object(vision, "_generate_content_with_easyocr", return_value=valid_ocr_json) as easyocr,
        patch.object(vision, "call_with_exponential_backoff", side_effect=single_attempt),
    ):
        result = asyncio.run(vision.extract_text_structured(str(image_path)))

    assert result["exercices"][0]["texte_brut"] == "Texte local"
    gemini.assert_called_once()
    easyocr.assert_called_once()
