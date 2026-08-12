"""Extraction de texte et génération de barème depuis un sujet d'examen.

Pipeline : Docling → PyMuPDF → Gemini Vision, puis Claude. Les sorties IA doivent
respecter un contrat Pydantic strict ; aucun barème fictif n'est jamais généré.
"""

from __future__ import annotations

import os

from backend.config import ANTHROPIC_API_KEY
from backend.schemas.ai_outputs import SubjectRubric, decode_json_response
from backend.services.exceptions import (
    AIConfigurationError,
    AIProviderUnavailableError,
    AIServiceError,
    SubjectExtractionError,
)
from backend.services.observability import observe_ai_call


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


def _generate_bareme_with_claude(texte: str, source: str) -> SubjectRubric:
    """Générer puis valider un barème structuré avec Claude."""
    if not ANTHROPIC_API_KEY:
        raise AIConfigurationError(
            "claude", "ANTHROPIC_API_KEY doit être configurée pour générer un barème."
        )

    prompt = BAREME_PROMPT_TEMPLATE.format(texte=texte[:4000], source=source or "inconnue")
    try:
        with observe_ai_call("claude", "subject_rubric"):
            import anthropic

            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
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


async def parse_subject(file_path: str) -> dict:
    """Extraire un sujet puis produire un barème validé, sans jamais simuler de résultat."""
    if not os.path.isfile(file_path):
        raise SubjectExtractionError("document", "Le fichier du sujet est introuvable.")

    texte, source = await _extract_text(file_path)
    bareme = _generate_bareme_with_claude(texte, source)
    result = bareme.model_dump()
    result["source_extraction"] = source
    return result
