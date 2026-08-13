"""Service OCR multimodal avec validation stricte et repli fournisseur.

Le fournisseur Gemini est prioritaire. Si celui-ci est indisponible ou rejette une
requête, Claude Vision peut reprendre l'extraction, à condition d'être configuré.
Aucune réponse simulée n'est produite : une indisponibilité ou une sortie non
conforme entraîne toujours une erreur métier explicite et assainie.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import Callable

from backend.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_OCR_MODEL,
    GEMINI_API_KEY,
    GEMINI_OCR_MODEL,
    LOCAL_OCR_FALLBACK_ENABLED,
)
from backend.schemas.ai_outputs import (
    OCRStructuredResult,
    decode_json_response,
    validate_ocr_simple_text,
)
from backend.services.exceptions import (
    AIConfigurationError,
    AIOutputValidationError,
    AIProviderUnavailableError,
    AIServiceError,
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
CLAUDE_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


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

    raw_status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    try:
        status_code = int(raw_status_code)
    except (TypeError, ValueError):
        status_code = None

    # Certains 400 du SDK HTTP correspondent à une clé API non valide plutôt qu'à
    # un défaut du contenu. On ne journalise jamais le message brut du fournisseur.
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


def _safe_claude_error_message(exc: Exception) -> str:
    """Classifier une erreur Claude sans exposer de détail brut ni de données de copie."""
    error_type = type(exc).__name__
    messages = {
        "AuthenticationError": "L’authentification Claude est refusée (clé API à vérifier).",
        "PermissionDeniedError": "L’accès à Claude est refusé (clé, projet ou autorisation à vérifier).",
        "NotFoundError": "Le modèle Claude configuré est indisponible.",
        "RateLimitError": "Le quota Claude est épuisé ou la limite de débit est atteinte.",
        "APITimeoutError": "Claude n’a pas répondu avant le délai prévu.",
        "InternalServerError": "Le service Claude est temporairement indisponible.",
        "APIConnectionError": "Le service Claude est temporairement indisponible.",
    }
    if error_type in messages:
        return messages[error_type]

    raw_status_code = getattr(exc, "status_code", None)
    try:
        status_code = int(raw_status_code)
    except (TypeError, ValueError):
        status_code = None
    status_messages = {
        400: "La requête Claude est invalide pour le modèle configuré.",
        401: "L’authentification Claude est refusée (clé API à vérifier).",
        403: "L’accès à Claude est refusé (clé, projet ou autorisation à vérifier).",
        404: "Le modèle Claude configuré est indisponible.",
        408: "Claude n’a pas répondu avant le délai prévu.",
        429: "Le quota Claude est épuisé ou la limite de débit est atteinte.",
        500: "Le service Claude est temporairement indisponible.",
        502: "Le service Claude est temporairement indisponible.",
        503: "Le service Claude est temporairement indisponible.",
        504: "Claude n’a pas répondu avant le délai prévu.",
    }
    return status_messages.get(
        status_code, "Le fournisseur OCR Claude est indisponible ou a rejeté la requête."
    )


def _read_file_for_ocr(image_path: str) -> tuple[bytes, str]:
    """Lire le support fourni et dériver son type MIME supporté."""
    if not os.path.isfile(image_path):
        raise AIProviderUnavailableError("ocr", "Le fichier OCR temporaire est introuvable.")

    try:
        with open(image_path, "rb") as file:
            data = file.read()
    except OSError as exc:
        raise AIProviderUnavailableError("ocr", "Le fichier OCR ne peut pas être lu.") from exc

    if not data:
        raise AIProviderUnavailableError("ocr", "Le fichier OCR est vide.")

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

    image_data, mime_type = _read_file_for_ocr(image_path)
    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError as exc:
        raise AIConfigurationError(
            "gemini", "Le SDK officiel google-genai doit être installé pour utiliser l'OCR."
        ) from exc

    try:
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


def _generate_content_with_easyocr(prompt: str, image_path: str) -> str:
    """Lire une image avec EasyOCR local, sans résultat artificiel ni appel distant."""
    image_data, mime_type = _read_file_for_ocr(image_path)
    if mime_type not in CLAUDE_IMAGE_MIME_TYPES:
        raise AIProviderUnavailableError(
            "easyocr", "Le format de fichier OCR n’est pas pris en charge par EasyOCR."
        )
    if not image_data:
        raise AIProviderUnavailableError("easyocr", "Le fichier OCR est vide.")

    try:
        import easyocr

        reader = easyocr.Reader(["fr", "en"], gpu=False, verbose=False)
        entries = reader.readtext(image_path, detail=1, paragraph=False)
        valid_entries = [
            entry for entry in entries if len(entry) >= 2 and str(entry[1]).strip()
        ]
        text_parts = [str(entry[1]).strip() for entry in valid_entries]
        text = "\n".join(text_parts)
        confidences = [
            float(entry[2]) for entry in valid_entries if len(entry) >= 3 and isinstance(entry[2], (int, float))
        ]
    except Exception as exc:
        raise AIProviderUnavailableError(
            "easyocr", "Le moteur OCR local est indisponible ou a rejeté le fichier."
        ) from exc

    if not text.strip():
        raise AIProviderUnavailableError(
            "easyocr", "Le moteur OCR local n’a détecté aucun texte exploitable."
        )
    if prompt == SIMPLE_PROMPT:
        return text

    average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    lisibilite = "bonne" if average_confidence >= 0.75 else "moyenne" if average_confidence >= 0.45 else "faible"
    return json.dumps(
        {
            "nom_eleve_detecte": None,
            "exercices": [
                {"numero": 1, "texte_brut": text, "lisibilite": lisibilite}
            ],
        },
        ensure_ascii=False,
    )


def _generate_content_with_claude(prompt: str, image_path: str) -> str:
    """Appeler Claude Vision comme repli OCR, sans jamais simuler une extraction."""
    if not ANTHROPIC_API_KEY:
        raise AIConfigurationError(
            "claude", "ANTHROPIC_API_KEY doit être configurée pour le repli OCR."
        )
    if not CLAUDE_OCR_MODEL:
        raise AIConfigurationError(
            "claude", "CLAUDE_OCR_MODEL doit désigner un modèle Claude valide pour le repli OCR."
        )

    image_data, mime_type = _read_file_for_ocr(image_path)
    if mime_type not in CLAUDE_IMAGE_MIME_TYPES and mime_type != "application/pdf":
        raise AIProviderUnavailableError(
            "claude", "Le format de fichier OCR n’est pas pris en charge par le repli Claude."
        )

    source = {
        "type": "base64",
        "media_type": mime_type,
        "data": base64.b64encode(image_data).decode("ascii"),
    }
    visual_part = {
        "type": "image" if mime_type in CLAUDE_IMAGE_MIME_TYPES else "document",
        "source": source,
    }

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=CLAUDE_OCR_MODEL,
            max_tokens=4096,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        visual_part,
                    ],
                }
            ],
        )
        text_blocks = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text" and isinstance(getattr(block, "text", None), str)
        ]
        text = "\n".join(text_blocks)
    except Exception as exc:
        raise AIProviderUnavailableError("claude", _safe_claude_error_message(exc)) from exc

    if not text.strip():
        raise AIProviderUnavailableError(
            "claude", "Claude a retourné une réponse OCR vide ou inexploitable."
        )
    return text


def _ocr_providers() -> list[tuple[str, Callable[[str, str], str]]]:
    """Retourner la chaîne OCR ; Gemini demeure la source d’erreur explicite par défaut."""
    # Gemini est toujours évalué en premier : en l’absence de clé, son erreur de
    # configuration explicite reste compatible avec les contrats API existants. Si
    # Claude est configuré, cette erreur cède ensuite la main au repli multimodal.
    providers: list[tuple[str, Callable[[str, str], str]]] = [("gemini", _generate_content)]
    if ANTHROPIC_API_KEY:
        providers.append(("claude", _generate_content_with_claude))
    if LOCAL_OCR_FALLBACK_ENABLED:
        providers.append(("easyocr", _generate_content_with_easyocr))
    return providers


async def _run_ocr_structured(provider_name: str, generate: Callable[[str, str], str], image_path: str) -> dict:
    """Exécuter un fournisseur OCR et valider immédiatement sa réponse structurée."""
    async def attempt() -> dict:
        with observe_ai_call(provider_name, "ocr_structured"):
            text = await asyncio.to_thread(generate, OCR_PROMPT, image_path)
            result = decode_json_response(text, OCRStructuredResult, provider=provider_name)
            return result.model_dump()

    return await call_with_exponential_backoff(
        provider=provider_name, operation="ocr_structured", call=attempt
    )


async def _run_ocr_simple(provider_name: str, generate: Callable[[str, str], str], image_path: str) -> str:
    """Exécuter un fournisseur OCR pour le mode texte brut avec validation de contenu."""
    async def attempt() -> str:
        with observe_ai_call(provider_name, "ocr_simple"):
            text = await asyncio.to_thread(generate, SIMPLE_PROMPT, image_path)
            return validate_ocr_simple_text(text, provider=provider_name)

    return await call_with_exponential_backoff(
        provider=provider_name, operation="ocr_simple", call=attempt
    )


async def extract_text_structured(image_path: str) -> dict:
    """Extraire une copie via Gemini puis Claude, avec contrats et réessais bornés."""
    providers = _ocr_providers()
    failures: list[AIServiceError] = []
    for provider_name, generate in providers:
        try:
            return await _run_ocr_structured(provider_name, generate, image_path)
        except AIServiceError as exc:
            failures.append(exc)

    configuration_error = next(
        (error for error in failures if isinstance(error, AIConfigurationError)), None
    )
    if configuration_error and all(isinstance(error, AIConfigurationError) for error in failures):
        raise configuration_error
    invalid_output = next(
        (error for error in failures if isinstance(error, AIOutputValidationError)), None
    )
    if invalid_output:
        raise invalid_output
    raise AIProviderUnavailableError(
        "ocr", "Aucun fournisseur OCR n'a pu fournir une extraction exploitable."
    ) from failures[-1]


async def extract_text_simple(image_path: str) -> str:
    """Extraire le texte d’une copie avec la même chaîne de repli que l’OCR structuré."""
    providers = _ocr_providers()
    failures: list[AIServiceError] = []
    for provider_name, generate in providers:
        try:
            return await _run_ocr_simple(provider_name, generate, image_path)
        except AIServiceError as exc:
            failures.append(exc)

    configuration_error = next(
        (error for error in failures if isinstance(error, AIConfigurationError)), None
    )
    if configuration_error and all(isinstance(error, AIConfigurationError) for error in failures):
        raise configuration_error
    invalid_output = next(
        (error for error in failures if isinstance(error, AIOutputValidationError)), None
    )
    if invalid_output:
        raise invalid_output
    raise AIProviderUnavailableError(
        "ocr", "Aucun fournisseur OCR n'a pu fournir une extraction exploitable."
    ) from failures[-1]
