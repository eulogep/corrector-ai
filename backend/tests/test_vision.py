"""Tests unitaires du fournisseur OCR Gemini sans appel réseau réel."""

from types import SimpleNamespace
from unittest.mock import patch

from backend.services import vision


def test_generate_content_uses_configured_stable_gemini_model(tmp_path):
    """Le modèle OCR doit être configurable afin de suivre le cycle de vie Gemini."""
    image_path = tmp_path / "copy.png"
    image_path.write_bytes(b"synthetic-image")
    fake_model = SimpleNamespace(generate_content=lambda _parts: SimpleNamespace(text="{}"))

    with (
        patch.object(vision, "GEMINI_API_KEY", "test-key"),
        patch.object(vision, "GEMINI_OCR_MODEL", "gemini-2.5-flash"),
        patch("google.generativeai.configure") as configure,
        patch("google.generativeai.GenerativeModel", return_value=fake_model) as model_factory,
    ):
        result = vision._generate_content("OCR prompt", str(image_path))

    assert result == "{}"
    configure.assert_called_once_with(api_key="test-key")
    model_factory.assert_called_once_with("gemini-2.5-flash")


def test_safe_gemini_error_message_classifies_common_provider_failures():
    """Les diagnostics opérationnels ne doivent révéler ni détail brut ni secret."""
    permission_error = type("PermissionDenied", (Exception,), {})()
    quota_error = type("ResourceExhausted", (Exception,), {})()
    model_error = type("NotFound", (Exception,), {})()

    assert "accès à gemini" in vision._safe_gemini_error_message(permission_error).lower()
    assert "quota" in vision._safe_gemini_error_message(quota_error).lower()
    assert "modèle gemini" in vision._safe_gemini_error_message(model_error).lower()
    assert "fournisseur ocr gemini" in vision._safe_gemini_error_message(Exception("raw" )).lower()
