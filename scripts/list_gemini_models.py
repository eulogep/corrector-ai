#!/usr/bin/env python3
"""Lister les modèles Gemini accessibles par une clé fournie par l’environnement ou stdin.

Le script ne journalise jamais la clé API. Il sert uniquement au diagnostic d’un
endpoint Gemini indisponible et affiche seulement des métadonnées de modèles.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY_REQUIRED_ON_STDIN", flush=True)
        api_key = sys.stdin.readline().strip()

    if not api_key:
        print("GEMINI_API_KEY_MISSING")
        return 2

    try:
        from google import genai
    except ImportError:
        print("GOOGLE_GENAI_SDK_MISSING")
        return 3

    try:
        with genai.Client(api_key=api_key) as client:
            models = client.models.list()
            models_with_actions = sorted(
                (
                    str(getattr(model, "name", "")),
                    tuple(str(action) for action in (getattr(model, "supported_actions", None) or [])),
                )
                for model in models
                if str(getattr(model, "name", ""))
            )
    except Exception as exc:  # Le détail peut contenir des informations fournisseur.
        print(f"GEMINI_MODEL_LIST_FAILED={type(exc).__name__}")
        return 4

    print(f"GEMINI_MODEL_COUNT={len(models_with_actions)}")
    for name, actions in models_with_actions:
        if "generateContent" in actions:
            print(f"GEMINI_GENERATE_MODEL={name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
