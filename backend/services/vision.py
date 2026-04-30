"""
Service OCR via Google Gemini Vision.
Extrait le texte manuscrit d'une image et le structure par exercice.
Fallback en mode mock si la clé Gemini n'est pas configurée.
"""

import json
import os
import base64
from backend.config import GEMINI_API_KEY

# Prompt structuré pour Gemini Vision — français
OCR_PROMPT = """Tu es un système OCR spécialisé dans la lecture de copies manuscrites d'élèves français.

Analyse cette image d'une copie manuscrite et extrais le contenu.

Retourne un JSON valide avec cette structure exacte :
{
  "nom_eleve_detecte": "nom détecté sur la copie ou null",
  "exercices": [
    {
      "numero": 1,
      "texte_brut": "texte écrit par l'élève pour cet exercice",
      "lisibilite": "bonne|moyenne|faible"
    }
  ]
}

Règles :
- Si tu détectes des numéros d'exercices (Ex 1, Exercice 1, Q1, etc.), sépare par exercice
- Si pas de numérotation claire, mets tout dans un seul exercice numéro 1
- Retourne UNIQUEMENT le JSON, sans markdown, sans commentaires
- Si le texte est illisible, indique lisibilite: "faible" et fais de ton mieux
"""

# Prompt simple — texte brut uniquement
SIMPLE_PROMPT = """Tu es un système OCR. Lis le texte manuscrit sur cette image et retourne-le en texte brut.
Ne formate pas en JSON. Retourne juste le texte tel que tu le lis, ligne par ligne.
"""


async def extract_text_structured(image_path: str) -> dict:
    """
    Extract structured text from a handwritten image using Gemini Vision.
    Returns JSON with exercises breakdown.
    Falls back to mock if no API key.
    """
    if not GEMINI_API_KEY:
        return _mock_structured_response(image_path)

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-pro")

        # Lire l'image et l'encoder
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Déterminer le type MIME
        ext = os.path.splitext(image_path)[1].lower()
        mime_types = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp",
            ".pdf": "application/pdf",
        }
        mime_type = mime_types.get(ext, "image/jpeg")

        # Appel Gemini Vision
        response = model.generate_content([
            OCR_PROMPT,
            {"mime_type": mime_type, "data": image_data},
        ])

        # Parser la réponse JSON
        text = response.text.strip()
        # Nettoyer si enveloppé dans des backticks markdown
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        return json.loads(text)

    except Exception as e:
        # En cas d'erreur, retourner le fallback mock
        return _mock_structured_response(image_path, error=str(e))


async def extract_text_simple(image_path: str) -> str:
    """
    Extract raw text from a handwritten image using Gemini Vision.
    Returns plain text string.
    Falls back to mock if no API key.
    """
    if not GEMINI_API_KEY:
        return _mock_simple_response()

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-pro")

        with open(image_path, "rb") as f:
            image_data = f.read()

        ext = os.path.splitext(image_path)[1].lower()
        mime_types = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp",
            ".pdf": "application/pdf",
        }
        mime_type = mime_types.get(ext, "image/jpeg")

        response = model.generate_content([
            SIMPLE_PROMPT,
            {"mime_type": mime_type, "data": image_data},
        ])
        return response.text.strip()

    except Exception as e:
        return _mock_simple_response(error=str(e))


# ━━━ Fallbacks mock ━━━

def _mock_structured_response(image_path: str = "", error: str = "") -> dict:
    """Return mock OCR data when Gemini is unavailable."""
    return {
        "nom_eleve_detecte": None,
        "exercices": [
            {
                "numero": 1,
                "texte_brut": "[Mode mock — OCR Gemini non configuré] Réponse exercice 1 de l'élève.",
                "lisibilite": "bonne",
            },
            {
                "numero": 2,
                "texte_brut": "[Mode mock — OCR Gemini non configuré] Réponse exercice 2 de l'élève.",
                "lisibilite": "moyenne",
            },
        ],
        "mock": True,
        "error": error if error else None,
    }


def _mock_simple_response(error: str = "") -> str:
    """Return mock text when Gemini is unavailable."""
    msg = "[Mode mock — OCR Gemini non configuré]\n"
    msg += "Exercice 1 : L'élève a écrit une réponse ici.\n"
    msg += "Exercice 2 : Suite de la copie manuscrite.\n"
    if error:
        msg += f"\n(Erreur: {error})"
    return msg
