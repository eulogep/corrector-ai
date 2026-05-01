"""
Service d'extraction automatique de barème depuis un sujet PDF/DOCX/image.
Pipeline : Docling (extraction) → Claude (génération barème JSON).
Fallbacks : Docling → PyMuPDF → Gemini Vision (si PDF scanné).
"""

import json
import os
from backend.config import ANTHROPIC_API_KEY


# Prompt Claude — français, JSON strict
BAREME_PROMPT_TEMPLATE = """Voici le sujet d'examen extrait par OCR (source : {source}) :

---
{texte}
---

Ta mission :
1. Identifier la matière et le niveau scolaire
2. Extraire TOUS les exercices et questions
3. Pour chaque exercice : numéro, énoncé complet, réponse attendue si visible,
   points (ou proposer une répartition équitable sur 20 points)
4. Calculer un score de confiance (0.0 à 1.0) selon la clarté du sujet
5. Retourner UNIQUEMENT le JSON (pas de markdown, pas de commentaires)

Format JSON exact attendu :
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
      "type": "calcul|redaction|qcm|schema|autre"
    }}
  ],
  "confiance": 0.9,
  "remarques": "..."
}}
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ÉTAPE 1 — Extraction texte depuis fichier
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _extract_with_docling(file_path: str) -> str:
    """Extract text using IBM Docling. Returns markdown string."""
    from docling.document_converter import DocumentConverter
    converter = DocumentConverter()
    result = converter.convert(file_path)
    return result.document.export_to_markdown()


def _extract_with_pymupdf(file_path: str) -> str:
    """Fallback extraction with PyMuPDF (text-only, fast)."""
    import fitz  # pymupdf
    doc = fitz.open(file_path)
    texte = " ".join([page.get_text() for page in doc])
    doc.close()
    return texte


async def _extract_with_gemini(file_path: str) -> str:
    """Last-resort fallback: OCR via Gemini Vision for scanned PDFs."""
    from backend.services.vision import extract_text_simple
    return await extract_text_simple(file_path)


async def _extract_text(file_path: str) -> tuple[str, str]:
    """
    Extract text from a file with multiple fallbacks.
    Returns (texte, source) where source ∈ {docling, pymupdf, gemini_vision}.
    """
    # 1. Docling (gère PDF, DOCX, images avec structure)
    try:
        texte = _extract_with_docling(file_path)
        source = "docling"
    except Exception as e:
        print(f"[subject_parser] Docling échoué : {e}")
        texte = ""
        source = ""

    # 2. Fallback PyMuPDF si Docling échoue ou renvoie trop peu de texte
    if len(texte.strip()) < 100:
        try:
            texte = _extract_with_pymupdf(file_path)
            source = "pymupdf"
        except Exception as e:
            print(f"[subject_parser] PyMuPDF échoué : {e}")

    # 3. Fallback Gemini Vision si texte toujours vide (PDF scanné)
    if len(texte.strip()) < 100:
        try:
            texte = await _extract_with_gemini(file_path)
            source = "gemini_vision"
        except Exception as e:
            print(f"[subject_parser] Gemini Vision échoué : {e}")

    return texte, source


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ÉTAPE 2 — Génération du barème via Claude
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_json_response(text: str) -> dict:
    """Strip markdown fences and parse JSON."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return json.loads(text)


def _generate_bareme_with_claude(texte: str, source: str) -> dict | None:
    """Ask Claude to structure the exam into a barème JSON. Returns None on failure."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        # Limite à 4000 caractères pour rester raisonnable en tokens
        prompt = BAREME_PROMPT_TEMPLATE.format(texte=texte[:4000], source=source or "inconnue")
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        return _parse_json_response(message.content[0].text)
    except Exception as e:
        print(f"[subject_parser] Claude échoué : {e}")
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Fallback mock
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _mock_bareme(texte: str = "", reason: str = "") -> dict:
    """Return a minimal mock barème when Claude unavailable or extraction fails."""
    return {
        "matiere_detectee": "Non détectée",
        "niveau_detecte": "Non détecté",
        "total_points": 20,
        "exercices": [
            {
                "numero": 1,
                "enonce": "[Mode mock — à compléter manuellement]",
                "reponse_attendue": "",
                "points_max": 10,
                "sous_questions": [],
                "type": "autre",
            },
            {
                "numero": 2,
                "enonce": "[Mode mock — à compléter manuellement]",
                "reponse_attendue": "",
                "points_max": 10,
                "sous_questions": [],
                "type": "autre",
            },
        ],
        "confiance": 0.0,
        "remarques": reason or "Configurez ANTHROPIC_API_KEY pour activer l'analyse IA.",
        "mock": True,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API publique
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def parse_subject(file_path: str) -> dict:
    """
    Main entry point: extract text from a subject file and generate a barème JSON.
    Pipeline: Docling → PyMuPDF → Gemini Vision, then Claude for structuring.
    Always returns a valid dict even if some steps fail.
    """
    if not os.path.exists(file_path):
        return _mock_bareme(reason=f"Fichier introuvable : {file_path}")

    # 1. Extraction texte
    texte, source = await _extract_text(file_path)
    if not texte or len(texte.strip()) < 20:
        return _mock_bareme(reason="Extraction du texte impossible (fichier vide ou illisible).")

    # 2. Structuration via Claude
    bareme = _generate_bareme_with_claude(texte, source)
    if bareme is None:
        return _mock_bareme(texte=texte, reason="Analyse IA indisponible — barème par défaut.")

    # 3. Métadonnées & normalisation défensive
    bareme.setdefault("total_points", 20)
    bareme.setdefault("exercices", [])
    bareme.setdefault("confiance", 0.5)
    bareme.setdefault("remarques", "")
    bareme["source_extraction"] = source
    return bareme
