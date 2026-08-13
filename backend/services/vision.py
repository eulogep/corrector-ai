"""Service OCR via Google Gemini Vision.

Aucune réponse simulée n'est produite : une indisponibilité, une mauvaise configuration
ou une sortie non conforme du fournisseur génère une erreur métier explicite.
"""

from __future__ import annotations

import asyncio
import os

from backend.config import GEMINI_API_KEY, GEMINI_OCR_MODEL
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


def _safe_gemini_error_message(exc: Exception) -> str:
    """Classifier une erreur Gemini sans exposer de détail, de copie ou de clé fournisseur."""
    error_type = type(exc).__name__
    messages = {
        "PermissionDenied": "L’accès à Gemini est refusé (clé, projet ou autorisation à vérifier).",
        "Unauthenticated": "L’authentification Gemini est refusée (clé API à vérifier).",
        "ResourceExhausted": "Le quota Gemini est épuisé ou la limite de débit est atteinte.",
        "NotFound": "Le modèle Gemini configuré est indisponible.",
        "InvalidArgument": "La requête Gemini est invalide pour le modèle configuré.",
        "ServiceUnavailable": "Le service Gemini est temporairement indisponible.",
        "DeadlineExceeded": "Gemini n’a pas répondu avant le délai prévu.",
    }
    if error_type in messages:
        return messages[error_type]

    # Le SDK Google GenAI maintenu expose ClientError/ServerError avec un code
    # HTTP, plutôt que les classes gRPC du SDK historique.
    raw_status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    try:
        status_code = int(raw_status_code)
    except (TypeError, ValueError):
        status_code = None

    # Certains 400 du SDK HTTP correspondent à une clé API non valide plutôt qu'à
    # un défaut du contenu. On ne journalise jamais le message brut du fournisseur,
    # mais on classe ce cas pour rendre le diagnostic de production actionnable.
    raw_error_text = str(exc).lower()
    if "api key not valid" in raw_error_text or "api_key_invalid" in raw_error_text:
        return "L’authentification Gemini est refusée (clé API à vérifier)."

    status_messages = {
        400: "La requête Gemini est invalide pour le modèle configuré.",
        401: "L’authentification Gemini est refusée (clé API à vérifier).",
        403: "L’accès à Gemini est refusé (clé, projet ou autorisation à vérifier).",
        404: "Le modèle Gemini configuré est indisponible.",
        408: "Gemini n’a pas répondu avant le délai prévu.",
        429: "Le quota Gemini est épuisé ou la limite de débit est atteinte.",
        500: "Le service Gemini est temporairement indisponible.",
        502: "Le service Gemini est temporairement indisponible.",
        503: "Le service Gemini est temporairement indisponible.",
        504: "Gemini n’a pas répondu avant le délai prévu.",
    }
    return status_messages.get(
        status_code, "Le fournisseur OCR Gemini est indisponible ou a rejeté la requête."
    )


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
    """Appeler Gemini Vision via le SDK Google GenAI officiel et retourner son texte."""
    if not GEMINI_API_KEY:
        raise AIConfigurationError(
            "gemini", "GEMINI_API_KEY doit être configurée pour utiliser l'OCR."
        )
    if not GEMINI_OCR_MODEL:
        raise AIConfigurationError(
            "gemini", "GEMINI_OCR_MODEL doit désigner un modèle OCR Gemini valide."
        )

    image_data, mime_type = _read_file_for_gemini(image_path)
    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError as exc:
        raise AIConfigurationError(
            "gemini", "Le SDK officiel google-genai doit être installé pour utiliser l'OCR."
        ) from exc

    try:
        # Un client éphémère est fermé après chaque OCR afin de ne pas laisser de
        # connexions HTTP ouvertes dans les workers FastAPI longuement exécutés.
        with google_genai.Client(api_key=GEMINI_API_KEY) as client:
            response = client.models.generate_content(
                model=GEMINI_OCR_MODEL,
                contents=[
                    genai_types.Part.from_text(text=prompt),
                    genai_types.Part.from_bytes(data=image_data, mime_type=mime_type),
                ],
            )
        text = response.text
    except Exception as exc:
        raise AIProviderUnavailableError("gemini", _safe_gemini_error_message(exc)) from exc

    if not isinstance(text, str) or not text.strip():
        raise AIProviderUnavailableError(
            "gemini", "Gemini a retourné une réponse OCR vide ou inexploitable."
        )
    return text


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
