#!/usr/bin/env python3
"""Vérifier l’API Gemini Interactions sans afficher de clé ni de contenu de réponse."""

from __future__ import annotations

import os


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY")
    model_name = os.environ.get("GEMINI_TEST_MODEL", "gemini-3.5-flash")
    if not api_key:
        print("GEMINI_API_KEY_MISSING")
        return 2

    try:
        from google import genai

        with genai.Client(api_key=api_key) as client:
            interaction = client.interactions.create(
                model=model_name,
                input="Réponds exactement par OK.",
            )
        text = interaction.output_text
    except Exception as exc:  # Le message distant peut contenir des métadonnées fournisseur.
        status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        print(f"GEMINI_INTERACTION_FAILED={type(exc).__name__}")
        if status is not None:
            print(f"GEMINI_INTERACTION_STATUS={status}")
        return 4

    if not isinstance(text, str) or not text.strip():
        print("GEMINI_INTERACTION_EMPTY_RESPONSE")
        return 5

    print("GEMINI_INTERACTION_SUCCESS")
    print(f"GEMINI_INTERACTION_MODEL={model_name}")
    print(f"GEMINI_INTERACTION_TEXT_LENGTH={len(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
