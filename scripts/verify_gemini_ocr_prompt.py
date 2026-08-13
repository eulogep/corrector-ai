#!/usr/bin/env python3
"""Reproduire localement l’appel OCR structuré sans afficher de clé ni de contenu de copie."""

from __future__ import annotations

import os
import sys


def main() -> int:
    image_path = os.environ.get("GEMINI_TEST_IMAGE", "")
    if not image_path:
        print("GEMINI_TEST_IMAGE_MISSING")
        return 2

    try:
        from backend.services.vision import OCR_PROMPT, _generate_content

        text = _generate_content(OCR_PROMPT, image_path)
    except Exception as exc:  # La sortie reste volontairement assainie.
        print(f"GEMINI_OCR_PROMPT_FAILED={type(exc).__name__}")
        print(f"GEMINI_OCR_PROMPT_STATUS={getattr(exc, 'status_code', 'none')}")
        return 4

    print("GEMINI_OCR_PROMPT_SUCCESS")
    print(f"GEMINI_OCR_PROMPT_TEXT_LENGTH={len(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
