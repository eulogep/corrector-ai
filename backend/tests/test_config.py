"""Tests de normalisation des secrets de configuration."""

from unittest.mock import patch

from backend import config


def test_read_secret_strips_surrounding_whitespace_from_environment():
    """Les clés saisies dans un gestionnaire d'environnement restent valides."""
    with patch.dict(
        "os.environ",
        {"GEMINI_API_KEY": "  gemini-server-key\n", "GEMINI_API_KEY_FILE": ""},
        clear=False,
    ):
        assert config._read_secret("GEMINI_API_KEY") == "gemini-server-key"


def test_read_secret_keeps_empty_value_when_no_secret_file_is_configured():
    """Une variable non configurée ne déclenche pas de lecture de fichier imprévue."""
    with patch.dict(
        "os.environ",
        {"UNCONFIGURED_SECRET": "", "UNCONFIGURED_SECRET_FILE": ""},
        clear=False,
    ):
        assert config._read_secret("UNCONFIGURED_SECRET") == ""
