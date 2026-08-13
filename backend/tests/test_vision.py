"""Tests unitaires du fournisseur OCR Gemini sans appel réseau réel."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.services import vision


def test_generate_content_uses_configured_stable_gemini_model(tmp_path):
    """Le modèle OCR doit être configurable et appelé via le SDK Google GenAI officiel."""
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


def test_safe_gemini_error_message_classifies_common_provider_failures():
    """Les diagnostics opérationnels ne doivent révéler ni détail brut ni secret."""
    permission_error = type("PermissionDenied", (Exception,), {})()
    quota_error = type("ResourceExhausted", (Exception,), {})()
    model_error = type("NotFound", (Exception,), {})()
    sdk_model_error = type("ClientError", (Exception,), {"code": 404})()

    assert "accès à gemini" in vision._safe_gemini_error_message(permission_error).lower()
    assert "quota" in vision._safe_gemini_error_message(quota_error).lower()
    assert "modèle gemini" in vision._safe_gemini_error_message(model_error).lower()
    assert "modèle gemini" in vision._safe_gemini_error_message(sdk_model_error).lower()
    assert "fournisseur ocr gemini" in vision._safe_gemini_error_message(Exception("raw")).lower()
