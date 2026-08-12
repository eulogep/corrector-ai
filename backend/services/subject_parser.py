"""Extraction de texte et génération de barème depuis un sujet d'examen.

Pipeline : Docling → PyMuPDF → Gemini Vision, puis Claude. Les sorties IA doivent
respecter un contrat Pydantic strict ; aucun barème fictif n'est jamais généré.
"""

from __future__ import annotations

import asyncio
import os

from backend.config import ANTHROPIC_API_KEY, DEEPSEEK_API_KEY
from backend.schemas.ai_outputs import SubjectRubric, decode_json_response
from backend.services.exceptions import (
    AIConfigurationError,
    AIProviderUnavailableError,
    AIServiceError,
    SubjectExtractionError,
)
from backend.services.observability import observe_ai_call
from backend.services.retry import call_with_exponential_backoff
from backend.services.subject_cache import SubjectExtractionCache


subject_cache = SubjectExtractionCache()


BAREME_PROMPT_TEMPLATE = """Voici le texte d'un sujet d'examen, extrait depuis {source} :

---
{texte}
---

Ta mission est d'identifier la matière et le niveau, puis d'extraire tous les exercices.
Retourne uniquement un objet JSON valide respectant exactement ce contrat :
{{
  "matiere_detectee": "...",
  "niveau_detecte": "...",
  "total_points": 20,
  "exercices": [
    {{
      "numero": 1,
      "enonce": "...",
      "reponse_attendue": "...",
      "points_max": 5,
      "sous_questions": [],
      "type": "calcul"
    }}
  ],
  "confiance": 0.9,
  "remarques": "..."
}}

Contraintes impératives :
- "type" vaut exactement calcul, redaction, qcm, schema ou autre.
- Chaque numéro d'exercice est entier, positif et unique.
- Chaque énoncé est non vide.
- "confiance" est comprise entre 0 et 1.
- La somme exacte de "points_max" doit être égale à "total_points".
- N'ajoute aucune clé, aucune balise Markdown et aucune explication hors JSON.
"""


def _extract_with_docling(file_path: str) -> str:
    """Extraire la structure et le texte via IBM Docling."""
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(file_path)
    return result.document.export_to_markdown()


def _extract_with_pymupdf(file_path: str) -> str:
    """Extraire rapidement le texte natif d'un PDF avec PyMuPDF."""
    import fitz

    document = fitz.open(file_path)
    try:
        return " ".join(page.get_text() for page in document)
    finally:
        document.close()


async def _extract_with_gemini(file_path: str) -> str:
    """Utiliser l'OCR Gemini comme dernier recours pour un sujet scanné."""
    from backend.services.vision import extract_text_simple

    return await extract_text_simple(file_path)


async def _extract_text(file_path: str) -> tuple[str, str]:
    """Tenter chaque extracteur et conserver uniquement un résultat exploitable."""
    attempts: list[tuple[str, str]] = []

    try:
        text = _extract_with_docling(file_path)
        if len(text.strip()) >= 100:
            return text, "docling"
        attempts.append(("docling", "texte insuffisant"))
    except Exception:
        attempts.append(("docling", "échec"))

    try:
        text = _extract_with_pymupdf(file_path)
        if len(text.strip()) >= 100:
            return text, "pymupdf"
        attempts.append(("pymupdf", "texte insuffisant"))
    except Exception:
        attempts.append(("pymupdf", "échec"))

    try:
        text = await _extract_with_gemini(file_path)
        if len(text.strip()) >= 20:
            return text, "gemini_vision"
        attempts.append(("gemini_vision", "texte insuffisant"))
    except Exception:
        attempts.append(("gemini_vision", "échec"))

    sources = ", ".join(source for source, _ in attempts)
    raise SubjectExtractionError(
        "document", f"Le document ne contient pas de texte suffisamment lisible ({sources})."
    )


async def _generate_bareme_with_claude(texte: str, source: str) -> SubjectRubric:
    """Générer un barème Claude avec réessais transitoires et validation stricte."""
    if not ANTHROPIC_API_KEY:
        raise AIConfigurationError(
            "claude", "ANTHROPIC_API_KEY doit être configurée pour générer un barème."
        )

    prompt = BAREME_PROMPT_TEMPLATE.format(texte=texte[:4000], source=source or "inconnue")

    async def attempt() -> SubjectRubric:
        try:
            with observe_ai_call("claude", "subject_rubric"):
                import anthropic

                client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                response = await asyncio.to_thread(
                    client.messages.create,
                    model="claude-sonnet-4-20250514",
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
                text = response.content[0].text
                return decode_json_response(text, SubjectRubric, provider="claude")
        except AIServiceError:
            raise
        except Exception as exc:
            raise AIProviderUnavailableError(
                "claude", "Le fournisseur de génération de barème est indisponible ou a rejeté la requête."
            ) from exc

    return await call_with_exponential_backoff(
        provider="claude", operation="subject_rubric", call=attempt
    )


async def _generate_bareme_with_deepseek(texte: str, source: str) -> SubjectRubric:
    """Générer un barème via DeepSeek lorsque Claude est indisponible."""
    if not DEEPSEEK_API_KEY:
        raise AIConfigurationError(
            "deepseek", "DEEPSEEK_API_KEY doit être configurée pour générer un barème de repli."
        )

    prompt = BAREME_PROMPT_TEMPLATE.format(texte=texte[:4000], source=source or "inconnue")

    async def attempt() -> SubjectRubric:
        try:
            with observe_ai_call("deepseek", "subject_rubric"):
                import httpx

                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(timeout=30.0, connect=5.0)
                ) as client:
                    response = await client.post(
                        "https://api.deepseek.com/chat/completions",
                        headers={
                            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "deepseek-chat",
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.1,
                            "max_tokens": 2000,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                    text = data["choices"][0]["message"]["content"]
                    return decode_json_response(text, SubjectRubric, provider="deepseek")
        except AIServiceError:
            raise
        except Exception as exc:
            raise AIProviderUnavailableError(
                "deepseek", "Le fournisseur DeepSeek est indisponible ou a rejeté la requête."
            ) from exc

    return await call_with_exponential_backoff(
        provider="deepseek", operation="subject_rubric", call=attempt
    )


async def _generate_bareme_with_fallback(texte: str, source: str) -> tuple[SubjectRubric, str]:
    """Utiliser le premier fournisseur de barème disponible produisant une sortie valide."""
    providers = []
    if ANTHROPIC_API_KEY:
        providers.append(("claude", _generate_bareme_with_claude))
    if DEEPSEEK_API_KEY:
        providers.append(("deepseek", _generate_bareme_with_deepseek))
    if not providers:
        raise AIConfigurationError(
            "subject_rubric",
            "Aucun fournisseur de barème n'est configuré. Configurez ANTHROPIC_API_KEY ou DEEPSEEK_API_KEY.",
        )

    failures: list[AIServiceError] = []
    for provider_name, provider in providers:
        try:
            return await provider(texte, source), provider_name
        except AIServiceError as exc:
            failures.append(exc)

    invalid_output = next(
        (error for error in failures if error.code == "ai_invalid_response"), None
    )
    if invalid_output:
        raise invalid_output
    raise AIProviderUnavailableError(
        "subject_rubric", "Aucun fournisseur de barème n'a pu fournir une réponse exploitable."
    ) from failures[-1]


async def parse_subject(file_path: str, cache_namespace: str = "anonymous") -> dict:
    """Extraire un sujet ou restituer un barème validé depuis le cache Redis.

    Le namespace est fourni par la route authentifiée afin qu'un résultat de sujet ne soit
    jamais partagé entre professeurs, même si deux fichiers identiques sont chargés.
    """
    if not os.path.isfile(file_path):
        raise SubjectExtractionError("document", "Le fichier du sujet est introuvable.")

    cache_key: str | None = None
    if subject_cache.enabled:
        cache_key = await subject_cache.key_for_file(file_path, cache_namespace)
        cached = await subject_cache.get(cache_key)
        if cached:
            try:
                bareme = SubjectRubric.model_validate(cached["rubric"])
                result = bareme.model_dump()
                result["source_extraction"] = "cache"
                result["llm_used"] = cached.get("llm_used", "cache")
                result["cache_hit"] = True
                return result
            except Exception:
                # Les données non conformes ne sont jamais retournées ; l'entrée sera reconstruite.
                await subject_cache.delete(cache_key)

    texte, source = await _extract_text(file_path)
    bareme, provider = await _generate_bareme_with_fallback(texte, source)
    cache_payload = {
        "rubric": bareme.model_dump(),
        "source_extraction": source,
        "llm_used": provider,
    }
    if cache_key is not None:
        await subject_cache.set(cache_key, cache_payload)

    result = bareme.model_dump()
    result["source_extraction"] = source
    result["llm_used"] = provider
    result["cache_hit"] = False
    return result
