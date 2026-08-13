#!/usr/bin/env python3
"""Diagnostique la réponse OCR de production sans écrire de JWT, mot de passe ou clé."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import requests

BASE_URL = os.environ.get("PILOT_BASE_URL", "https://corrector-ai.onrender.com").rstrip("/")
EMAIL = os.environ["PILOT_EMAIL"]
PASSWORD = os.environ["PILOT_PASSWORD"]
COPY_PATH = Path(os.environ.get("PILOT_COPY_PATH", "performance/copie_test_pilote.png"))


def main() -> int:
    session = requests.Session()
    login = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=60,
    )
    if login.status_code != 200:
        print(f"LOGIN_STATUS={login.status_code}")
        return 1
    token = login.json().get("token")
    if not isinstance(token, str) or not token:
        print("LOGIN_TOKEN_MISSING")
        return 1
    session.headers["Authorization"] = f"Bearer {token}"

    with COPY_PATH.open("rb") as source:
        response = session.post(
            f"{BASE_URL}/api/ocr/extract",
            files={"file": (COPY_PATH.name, source, "image/png")},
            timeout=120,
        )

    content_type = response.headers.get("content-type", "").split(";", 1)[0]
    print(f"OCR_STATUS={response.status_code} CONTENT_TYPE={content_type}")
    try:
        payload = response.json()
    except ValueError:
        digest = hashlib.sha256(response.content).hexdigest()[:12]
        print(f"OCR_NON_JSON length={len(response.content)} sha256_prefix={digest}")
        return 1

    if not isinstance(payload, dict):
        print(f"OCR_JSON_TYPE={type(payload).__name__}")
        return 1
    print("OCR_JSON_KEYS=" + ",".join(sorted(str(key) for key in payload)))
    detail = payload.get("detail")
    print(f"OCR_DETAIL_TYPE={type(detail).__name__}")
    if isinstance(detail, dict):
        print("OCR_DETAIL_KEYS=" + ",".join(sorted(str(key) for key in detail)))
        message = detail.get("message")
        code = detail.get("code")
        if code == "persistent_storage_unavailable" and isinstance(message, str):
            # Message émis par notre application, volontairement sans réponse fournisseur.
            print(f"OCR_STORAGE_DIAGNOSTIC={message[:200]}")
        elif code in {"ai_provider_not_configured", "ai_provider_unavailable", "ai_invalid_response"}:
            # Ces messages sont définis dans backend.services.vision, sans retour brut fournisseur.
            provider = detail.get("provider")
            provider_text = provider if isinstance(provider, str) else "unknown"
            message_text = message[:200] if isinstance(message, str) else ""
            print(f"OCR_AI_DIAGNOSTIC=code:{code} provider:{provider_text} message:{message_text}")
    elif isinstance(detail, str) and "stockage" in detail.lower():
        print(f"OCR_STORAGE_DIAGNOSTIC={detail[:200]}")
    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.RequestException as exc:
        print(f"NETWORK_ERROR={type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1)
