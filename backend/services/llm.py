"""Service de correction via LLM.

Les réponses de Claude et DeepSeek sont validées contre un contrat strict avant toute
sauvegarde. Si aucun fournisseur ne peut produire une correction valide, l'API renvoie
une erreur explicite : elle ne génère jamais de note simulée.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from backend.config import ANTHROPIC_API_KEY, DEEPSEEK_API_KEY
from backend.schemas.ai_outputs import (
    GradingResult,
    decode_json_response,
    validate_grading_result,
)
from backend.services.exceptions import (
    AIConfigurationError,
    AIProviderUnavailableError,
    AIServiceError,
    CorrectionInputError,
)
from backend.services.observability import observe_ai_call
from backend.services.retry import call_with_exponential_backoff


SYSTEM_PROMPT = """Tu es Corrector AI, un assistant pédagogique expert du système éducatif français.
Tu corriges des copies d'élèves en comparant leurs réponses au corrigé officiel du professeur.

Tu dois évaluer chaque exercice individuellement, attribuer les points du barème, fournir
un feedback constructif et bienveillant, relever les erreurs récurrentes et rédiger une
appréciation globale. N'invente jamais de réponse élève, de critère de barème ou de note.

Tu retournes uniquement un JSON strictement conforme au contrat demandé, sans Markdown,
sans commentaire et sans clé supplémentaire."""

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
- Respecte strictement les points maximum fournis, exercice par exercice.
- Le total de "points_obtenus" doit être exactement égal à "note_totale".
- La note totale doit être comprise entre 0 et {note_sur}.
- Couvre tous les exercices, exactement une fois, sans en ajouter.
- "correct" est un booléen JSON : true ou false, jamais 0 ou 1.
- Signale une anomalie seulement si elle est étayée par l'historique fourni.

Retourne exactement ce JSON :
{{
  "exercices": [
    {{
      "numero": 1,
      "points_obtenus": 3.5,
      "points_max": 5,
      "correct": false,
      "feedback": "Bonne compréhension du théorème, mais erreur de calcul.",
      "erreurs_types": "Erreur de signe dans la soustraction"
    }}
  ],
  "note_totale": 14.5,
  "note_sur": {note_sur},
  "appreciation": "Copie sérieuse avec une bonne progression.",
  "alerte_anomalie": false,
  "message_anomalie": ""
}}
"""


def _build_prompt(
    matiere: str,
    niveau: str,
    note_sur: float,
    exercices_corrige: list[dict],
    reponses_eleve: list[dict],
    historique: list[dict] | None,
) -> str:
    """Construire le prompt à partir des données contrôlées par l'application."""
    corrige_text = "\n".join(
        f"Exercice {exercise['numero']} ({exercise.get('points_max', '?')} pts) : "
        f"{exercise.get('enonce', '')} → Réponse attendue : {exercise['reponse_attendue']}"
        for exercise in exercices_corrige
    )
    reponses_text = "\n".join(
        f"Exercice {answer['numero']} : {answer['reponse_eleve']}"
        for answer in reponses_eleve
    )
    historique_text = (
        "\n".join(
            f"- {item.get('date_examen', '?')} : "
            f"{item.get('note_totale', '?')}/{item.get('note_sur', 20)}"
            for item in historique
        )
        if historique
        else "Pas d'historique disponible (première copie)."
    )
    return GRADING_TEMPLATE.format(
        matiere=matiere,
        niveau=niveau,
        note_sur=note_sur,
        corrige=corrige_text,
        reponses_eleve=reponses_text,
        historique=historique_text,
    )


async def _grade_with_claude(prompt: str) -> GradingResult:
    """Obtenir une correction de Claude, puis valider strictement son JSON."""
    if not ANTHROPIC_API_KEY:
        raise AIConfigurationError(
            "claude", "ANTHROPIC_API_KEY n'est pas configurée pour la correction."
        )
    try:
        with observe_ai_call("claude", "grading"):
            import anthropic

            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = await asyncio.to_thread(
                client.messages.create,
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            text = response.content[0].text
            return decode_json_response(text, GradingResult, provider="claude")
    except AIServiceError:
        raise
    except Exception as exc:
        raise AIProviderUnavailableError(
            "claude", "Le fournisseur Claude est indisponible ou a rejeté la requête."
        ) from exc


async def _grade_with_deepseek(prompt: str) -> GradingResult:
    """Obtenir une correction de DeepSeek, puis valider strictement son JSON."""
    if not DEEPSEEK_API_KEY:
        raise AIConfigurationError(
            "deepseek", "DEEPSEEK_API_KEY n'est pas configurée pour la correction."
        )
    try:
        with observe_ai_call("deepseek", "grading"):
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
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 4096,
                    },
                )
                response.raise_for_status()
                data = response.json()
                text = data["choices"][0]["message"]["content"]
                return decode_json_response(text, GradingResult, provider="deepseek")
    except AIServiceError:
        raise
    except Exception as exc:
        raise AIProviderUnavailableError(
            "deepseek", "Le fournisseur DeepSeek est indisponible ou a rejeté la requête."
        ) from exc


def _validate_requested_scale(exercices_corrige: list[dict], note_sur: float) -> None:
    """Éviter d'envoyer au fournisseur un barème incohérent."""
    if not exercices_corrige:
        raise CorrectionInputError("correction", "Le barème de correction est vide.")

    numeros = [exercise.get("numero") for exercise in exercices_corrige]
    if any(not isinstance(numero, int) or numero < 1 for numero in numeros):
        raise CorrectionInputError("correction", "Le barème contient un numéro d'exercice invalide.")
    if len(numeros) != len(set(numeros)):
        raise CorrectionInputError("correction", "Le barème contient des numéros d'exercice dupliqués.")

    try:
        total = round(sum(float(exercise["points_max"]) for exercise in exercices_corrige), 2)
    except (KeyError, TypeError, ValueError) as exc:
        raise CorrectionInputError("correction", "Le barème contient un maximum de points invalide.") from exc

    if total <= 0 or abs(total - note_sur) > 0.01:
        raise CorrectionInputError(
            "correction", "La somme du barème doit correspondre exactement à la note demandée."
        )


async def grade_copy(
    matiere: str,
    niveau: str,
    note_sur: float,
    exercices_corrige: list[dict],
    reponses_eleve: list[dict],
    historique: list[dict] | None = None,
) -> dict:
    """Corriger une copie avec le premier fournisseur disponible produisant une sortie valide."""
    _validate_requested_scale(exercices_corrige, note_sur)
    prompt = _build_prompt(
        matiere, niveau, note_sur, exercices_corrige, reponses_eleve, historique
    )

    providers: list[tuple[str, Callable[[str], Awaitable[GradingResult]]]] = []
    if ANTHROPIC_API_KEY:
        providers.append(("claude", _grade_with_claude))
    if DEEPSEEK_API_KEY:
        providers.append(("deepseek", _grade_with_deepseek))

    if not providers:
        raise AIConfigurationError(
            "correction",
            "Aucun fournisseur de correction n'est configuré. Configurez ANTHROPIC_API_KEY ou DEEPSEEK_API_KEY.",
        )

    failures: list[AIServiceError] = []
    for provider_name, provider in providers:
        try:
            result = await call_with_exponential_backoff(
                provider=provider_name,
                operation="grading",
                call=lambda provider=provider: provider(prompt),
            )
            result = validate_grading_result(result, exercices_corrige, note_sur)
            payload = result.model_dump()
            payload["llm_used"] = provider_name
            return payload
        except AIServiceError as exc:
            failures.append(exc)

    invalid_output = next(
        (error for error in failures if error.code == "ai_invalid_response"), None
    )
    if invalid_output:
        raise invalid_output

    raise AIProviderUnavailableError(
        "correction", "Aucun fournisseur de correction n'a pu fournir une réponse exploitable."
    ) from failures[-1]
