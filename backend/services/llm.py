"""
Service de correction via Anthropic Claude.
Compare les réponses de l'élève au corrigé type et attribue les points.
Intègre l'historique pour la détection d'anomalies.
"""

import json
from backend.config import ANTHROPIC_API_KEY

# Prompt système pour Claude — correction de copies françaises
SYSTEM_PROMPT = """Tu es Corrector AI, un assistant pédagogique expert du système éducatif français.
Tu corriges des copies d'élèves en comparant leurs réponses au corrigé officiel du professeur.

Tu dois :
1. Évaluer chaque exercice individuellement
2. Attribuer les points selon le barème
3. Fournir un feedback pédagogique constructif et bienveillant
4. Détecter les erreurs types récurrentes
5. Rédiger une appréciation globale style bulletin français
6. Détecter toute anomalie par rapport à l'historique de l'élève

IMPORTANT : Retourne UNIQUEMENT un JSON valide, sans markdown, sans commentaires."""

GRADING_TEMPLATE = """
Corrige cette copie d'élève.

## Informations
- Matière : {matiere}
- Niveau : {niveau}
- Note sur : {note_sur}

## Corrigé officiel (réponses attendues)
{corrige}

## Réponses de l'élève
{reponses_eleve}

## Historique récent de l'élève dans cette matière
{historique}

## Consignes de notation
- Barème français : notes sur {note_sur}
- Sois juste mais bienveillant : l'élève est en apprentissage
- Pour chaque exercice, indique les points obtenus, le feedback, et les erreurs types
- Détecte si la note est anormalement haute (+3 pts au-dessus de la moyenne habituelle)
  ou si le style de raisonnement est très différent de l'habituel

Retourne ce JSON exact :
{{
  "exercices": [
    {{
      "numero": 1,
      "points_obtenus": 3.5,
      "points_max": 5,
      "correct": 0,
      "feedback": "Bonne compréhension du théorème mais erreur de calcul à la ligne 3...",
      "erreurs_types": "Erreur de signe dans la soustraction"
    }}
  ],
  "note_totale": 14.5,
  "note_sur": {note_sur},
  "appreciation": "Copie sérieuse avec une bonne progression. Attention aux erreurs de calcul récurrentes.",
  "alerte_anomalie": false,
  "message_anomalie": ""
}}
"""


async def grade_copy(
    matiere: str,
    niveau: str,
    note_sur: float,
    exercices_corrige: list[dict],
    reponses_eleve: list[dict],
    historique: list[dict] | None = None,
) -> dict:
    """
    Grade a student's copy using Claude.
    
    Args:
        matiere: Subject name
        niveau: Level (6ème, 3ème, Terminale, etc.)
        note_sur: Total points (usually 20)
        exercices_corrige: Expected answers [{numero, enonce, reponse_attendue, points_max}]
        reponses_eleve: Student answers [{numero, reponse_eleve}]
        historique: Recent exam history [{note_totale, note_sur, date_examen}]
    
    Returns:
        Grading result dict with exercises, note_totale, appreciation, etc.
    """
    if not ANTHROPIC_API_KEY:
        return _mock_grading(exercices_corrige, reponses_eleve, note_sur)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Formater le corrigé
        corrige_text = "\n".join([
            f"Exercice {ex['numero']} ({ex.get('points_max', '?')} pts) : {ex.get('enonce', '')} → Réponse attendue : {ex['reponse_attendue']}"
            for ex in exercices_corrige
        ])

        # Formater les réponses élève
        reponses_text = "\n".join([
            f"Exercice {r['numero']} : {r['reponse_eleve']}"
            for r in reponses_eleve
        ])

        # Formater l'historique
        if historique:
            hist_text = "\n".join([
                f"- {h.get('date_examen', '?')} : {h.get('note_totale', '?')}/{h.get('note_sur', 20)}"
                for h in historique
            ])
        else:
            hist_text = "Pas d'historique disponible (première copie)"

        # Construire le prompt
        prompt = GRADING_TEMPLATE.format(
            matiere=matiere,
            niveau=niveau,
            note_sur=note_sur,
            corrige=corrige_text,
            reponses_eleve=reponses_text,
            historique=hist_text,
        )

        # Appel Claude
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        # Parser la réponse
        text = response.content[0].text.strip()
        # Nettoyer si enveloppé dans des backticks
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        return json.loads(text)

    except Exception as e:
        return _mock_grading(exercices_corrige, reponses_eleve, note_sur, error=str(e))


def _mock_grading(exercices_corrige: list, reponses_eleve: list, note_sur: float, error: str = "") -> dict:
    """Return mock grading when Claude is unavailable."""
    exercices = []
    total = 0
    for ex in exercices_corrige:
        pts_max = ex.get("points_max", 5)
        # Attribuer 70% des points en mode mock
        pts = round(pts_max * 0.7, 1)
        total += pts
        exercices.append({
            "numero": ex["numero"],
            "points_obtenus": pts,
            "points_max": pts_max,
            "correct": 0 if pts < pts_max else 1,
            "feedback": f"[Mode mock — Claude non configuré] Correction automatique exercice {ex['numero']}.",
            "erreurs_types": "",
        })

    return {
        "exercices": exercices,
        "note_totale": round(total, 1),
        "note_sur": note_sur,
        "appreciation": "[Mode mock] Copie corrigée automatiquement sans IA. Configurez ANTHROPIC_API_KEY pour une correction réelle.",
        "alerte_anomalie": False,
        "message_anomalie": "",
        "mock": True,
        "error": error if error else None,
    }
