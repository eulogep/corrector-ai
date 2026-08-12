"""Service OCR via Google Gemini Vision.

Aucune réponse simulée n'est produite : une indisponibilité, une mauvaise configuration
ou une sortie non conforme du fournisseur génère une erreur métier explicite.
"""

from __future__ import annotations

import asyncio
import os

from backend.config import GEMINI_API_KEY
from backend.schemas.ai_outputs import (
    OCRStructuredResult,
    decode_json_response,
    validate_ocr_simple_text,
)
from backend.services.exceptions import (
    AIConfigurationError,
    AIProviderUnavailableError,
)
from backend.services.observability import observe_ai_call
from backend.services.retry import call_with_exponential_backoff


OCR_PROMPT = """Tu es un système OCR spécialisé dans la lecture de copies manuscrites d'élèves français.

Analyse cette image d'une copie manuscrite et extrais le contenu.

Retourne uniquement un objet JSON valide ayant exactement cette structure :
{
  "nom_eleve_detecte": "nom détecté sur la copie ou null",
  "exercices": [
    {
      "numero": 1,
      "texte_brut": "texte écrit par l'élève pour cet exercice",
      "lisibilite": "bonne"
    }
  ]
}

Contraintes impératives :
- "lisibilite" vaut exactement "bonne", "moyenne" ou "faible".
- Chaque exercice a un numéro entier positif unique et un texte non vide.
- Si la numérotation est absente, renvoie un seul exercice numéro 1.
- N'ajoute aucune clé, explication, balise Markdown ou donnée inventée.
"""

SIMPLE_PROMPT = """Tu es un système OCR. Lis le texte manuscrit sur cette image et retourne-le en texte brut.
N'ajoute ni explication, ni mise en forme Markdown. Si aucun texte n'est lisible, réponds exactement : [illisible].
"""

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


def _read_file_for_gemini(image_path: str) -> tuple[bytes, str]:
    """Lire le support fourni et dériver son type MIME supporté."""
    if not os.path.isfile(image_path):
        raise AIProviderUnavailableError("gemini", "Le fichier OCR temporaire est introuvable.")

    try:
        with open(image_path, "rb") as file:
            data = file.read()
    except OSError as exc:
        raise AIProviderUnavailableError("gemini", "Le fichier OCR ne peut pas être lu.") from exc

    if not data:
        raise AIProviderUnavailableError("gemini", "Le fichier OCR est vide.")

    extension = os.path.splitext(image_path)[1].lower()
    return data, MIME_TYPES.get(extension, "application/octet-stream")


def _generate_content(prompt: str, image_path: str) -> str:
    """Appeler Gemini Vision et retourner son texte sans le transformer."""
    if not GEMINI_API_KEY:
        raise AIConfigurationError(
            "gemini", "GEMINI_API_KEY doit être configurée pour utiliser l'OCR."
        )

    image_data, mime_type = _read_file_for_gemini(image_path)
    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = model.generate_content([
            prompt,
            {"mime_type": mime_type, "data": image_data},
        ])
        return response.text
    except AIConfigurationError:
        raise
    except Exception as exc:
        raise AIProviderUnavailableError(
            "gemini", "Le fournisseur OCR Gemini est indisponible ou a rejeté la requête."
        ) from exc


async def extract_text_structured(image_path: str) -> dict:
    """Extraire des réponses structurées avec réessais limités d'erreurs Gemini transitoires."""
    async def attempt() -> dict:
        with observe_ai_call("gemini", "ocr_structured"):
            text = await asyncio.to_thread(_generate_content, OCR_PROMPT, image_path)
            result = decode_json_response(text, OCRStructuredResult, provider="gemini")
            return result.model_dump()

    return await call_with_exponential_backoff(
        provider="gemini", operation="ocr_structured", call=attempt
    )


async def extract_text_simple(image_path: str) -> str:
    """Extraire le texte OCR avec réessais limités sans jamais simuler de résultat."""
    async def attempt() -> str:
        with observe_ai_call("gemini", "ocr_simple"):
            text = await asyncio.to_thread(_generate_content, SIMPLE_PROMPT, image_path)
            return validate_ocr_simple_text(text, provider="gemini")

    return await call_with_exponential_backoff(
        provider="gemini", operation="ocr_simple", call=attempt
    )
