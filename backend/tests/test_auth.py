"""Tests de sécurité des sessions JWT."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from jose import jwt

from backend import auth


def test_created_token_carries_the_active_session_version():
    """Les nouvelles sessions sont liées à la version de rotation active."""
    with (
        patch.object(auth, "JWT_SECRET_KEY", "unit-test-secret"),
        patch.object(auth, "JWT_TOKEN_VERSION", "rotation-test"),
    ):
        token = auth.create_token(42, "teacher@example.test")
        payload = auth.decode_token(token)

    assert payload["sub"] == "42"
    assert payload["ver"] == "rotation-test"


def test_legacy_token_without_version_is_rejected_after_rotation():
    """Un jeton antérieur à la rotation ne peut plus accéder aux routes protégées."""
    legacy_payload = {
        "sub": "42",
        "email": "teacher@example.test",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(legacy_payload, "unit-test-secret", algorithm="HS256")

    with (
        patch.object(auth, "JWT_SECRET_KEY", "unit-test-secret"),
        patch.object(auth, "JWT_TOKEN_VERSION", "rotation-test"),
        pytest.raises(HTTPException) as exc_info,
    ):
        auth.decode_token(token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token invalide ou expiré"
