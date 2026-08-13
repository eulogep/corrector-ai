#!/usr/bin/env python3
"""Vérifier un appel Gemini multimodal sans afficher de clé, de copie ou de sortie OCR."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY")
    image_path = os.environ.get("GEMINI_TEST_IMAGE", "")
    model_name = os.environ.get("GEMINI_TEST_MODEL", "gemini-3.5-flash")
    if not api_key:
        print("GEMINI_API_KEY_MISSING")
        return 2
    if not image_path or not Path(image_path).is_file():
        print("GEMINI_TEST_IMAGE_MISSING")
        return 3

    try:
        from google import genai
        from google.genai import types

        image_data = Path(image_path).read_bytes()
        with genai.Client(api_key=api_key) as client:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_text(text="Réponds exactement par OK."),
                    types.Part.from_bytes(data=image_data, mime_type="image/png"),
                ],
            )
        text = response.text
    except Exception as exc:  # Aucun message distant, potentiellement sensible, n’est affiché.
        status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        print(f"GEMINI_MULTIMODAL_FAILED={type(exc).__name__}")
        if status is not None:
            print(f"GEMINI_MULTIMODAL_STATUS={status}")
        return 4

    if not isinstance(text, str) or not text.strip():
        print("GEMINI_MULTIMODAL_EMPTY_RESPONSE")
        return 5

    print("GEMINI_MULTIMODAL_SUCCESS")
    print(f"GEMINI_MULTIMODAL_MODEL={model_name}")
    print(f"GEMINI_MULTIMODAL_TEXT_LENGTH={len(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
