"""Contrats stricts et validation centralisée des sorties des fournisseurs IA.

Les fournisseurs de modèles ne sont pas considérés comme des sources fiables : toute sortie
est décodée, validée puis comparée au contexte applicatif avant utilisation.
"""

from __future__ import annotations

import json
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.services.exceptions import AIOutputValidationError


ModelT = TypeVar("ModelT", bound=BaseModel)


class StrictAIModel(BaseModel):
    """Base commune : aucun champ inattendu, aucune coercition implicite."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class OCRExercise(StrictAIModel):
    numero: int = Field(ge=1, le=500)
    texte_brut: str = Field(min_length=1, max_length=50_000)
    lisibilite: Literal["bonne", "moyenne", "faible"]


class OCRStructuredResult(StrictAIModel):
    nom_eleve_detecte: str | None = Field(default=None, max_length=300)
    exercices: list[OCRExercise] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def exercise_numbers_are_unique(self) -> "OCRStructuredResult":
        numeros = [exercise.numero for exercise in self.exercices]
        if len(numeros) != len(set(numeros)):
            raise ValueError("Chaque exercice OCR doit avoir un numéro unique.")
        return self


class OCRSimpleResult(StrictAIModel):
    text: str = Field(min_length=1, max_length=200_000)


class RubricExercise(StrictAIModel):
    numero: int = Field(ge=1, le=500)
    enonce: str = Field(min_length=1, max_length=20_000)
    reponse_attendue: str = Field(default="", max_length=20_000)
    points_max: float = Field(gt=0, le=1000)
    sous_questions: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    type: Literal["calcul", "redaction", "qcm", "schema", "autre"]


class SubjectRubric(StrictAIModel):
    matiere_detectee: str = Field(min_length=1, max_length=200)
    niveau_detecte: str = Field(min_length=1, max_length=200)
    total_points: float = Field(gt=0, le=1000)
    exercices: list[RubricExercise] = Field(min_length=1, max_length=500)
    confiance: float = Field(ge=0, le=1)
    remarques: str = Field(default="", max_length=10_000)

    @model_validator(mode="after")
    def rubric_is_consistent(self) -> "SubjectRubric":
        numeros = [exercise.numero for exercise in self.exercices]
        if len(numeros) != len(set(numeros)):
            raise ValueError("Chaque exercice du barème doit avoir un numéro unique.")

        total_exercices = round(sum(exercise.points_max for exercise in self.exercices), 2)
        if abs(total_exercices - self.total_points) > 0.01:
            raise ValueError(
                "La somme des points des exercices doit correspondre au total du barème."
            )
        return self


class GradedExercise(StrictAIModel):
    numero: int = Field(ge=1, le=500)
    points_obtenus: float = Field(ge=0, le=1000)
    points_max: float = Field(gt=0, le=1000)
    correct: bool
    feedback: str = Field(min_length=1, max_length=20_000)
    erreurs_types: str = Field(default="", max_length=10_000)

    @model_validator(mode="after")
    def score_is_bounded(self) -> "GradedExercise":
        if self.points_obtenus > self.points_max:
            raise ValueError("Les points obtenus ne peuvent pas dépasser les points maximum.")
        return self


class GradingResult(StrictAIModel):
    exercices: list[GradedExercise] = Field(min_length=1, max_length=500)
    note_totale: float = Field(ge=0, le=1000)
    note_sur: float = Field(gt=0, le=1000)
    appreciation: str = Field(min_length=1, max_length=10_000)
    alerte_anomalie: bool
    message_anomalie: str = Field(default="", max_length=10_000)

    @model_validator(mode="after")
    def grade_is_consistent(self) -> "GradingResult":
        numeros = [exercise.numero for exercise in self.exercices]
        if len(numeros) != len(set(numeros)):
            raise ValueError("Chaque exercice corrigé doit avoir un numéro unique.")

        total_exercices = round(sum(exercise.points_obtenus for exercise in self.exercices), 2)
        if abs(total_exercices - self.note_totale) > 0.01:
            raise ValueError(
                "La note totale doit correspondre à la somme des points attribués."
            )
        if self.note_totale > self.note_sur:
            raise ValueError("La note totale ne peut pas dépasser la note maximale.")
        return self


def decode_json_response(text: str, model_type: type[ModelT], provider: str) -> ModelT:
    """Décoder une réponse JSON de fournisseur puis l'associer à un contrat strict."""
    if not isinstance(text, str) or not text.strip():
        raise AIOutputValidationError(provider, "La réponse du fournisseur est vide.")

    payload = text.strip()
    if payload.startswith("```"):
        lines = payload.splitlines()
        if len(lines) < 3 or not lines[-1].strip().startswith("```"):
            raise AIOutputValidationError(provider, "Le bloc JSON retourné est incomplet.")
        payload = "\n".join(lines[1:-1]).strip()

    try:
        decoded = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AIOutputValidationError(provider, "La réponse n'est pas un JSON valide.") from exc

    try:
        return model_type.model_validate(decoded)
    except ValidationError as exc:
        raise AIOutputValidationError(
            provider, "La réponse JSON ne respecte pas le contrat attendu."
        ) from exc


def validate_ocr_simple_text(text: str, provider: str) -> str:
    """Valider une extraction OCR non structurée."""
    try:
        return OCRSimpleResult.model_validate({"text": text}).text
    except ValidationError as exc:
        raise AIOutputValidationError(
            provider, "Le texte OCR est vide ou ne respecte pas les limites attendues."
        ) from exc


def validate_grading_result(
    payload: GradingResult,
    expected_exercises: list[dict[str, Any]],
    requested_note_sur: float,
) -> GradingResult:
    """Vérifier la cohérence d'une correction IA avec le barème demandé."""
    expected_by_number = {exercise["numero"]: exercise for exercise in expected_exercises}
    result_by_number = {exercise.numero: exercise for exercise in payload.exercices}

    if set(result_by_number) != set(expected_by_number):
        raise AIOutputValidationError(
            "correction", "La correction ne couvre pas exactement les exercices du barème."
        )

    if abs(payload.note_sur - requested_note_sur) > 0.01:
        raise AIOutputValidationError(
            "correction", "L'échelle de notation retournée ne correspond pas à celle demandée."
        )

    for numero, result in result_by_number.items():
        expected_max = float(expected_by_number[numero]["points_max"])
        if abs(result.points_max - expected_max) > 0.01:
            raise AIOutputValidationError(
                "correction", f"Le maximum de points de l'exercice {numero} ne correspond pas au barème."
            )

    expected_total = round(sum(float(item["points_max"]) for item in expected_exercises), 2)
    if abs(expected_total - requested_note_sur) > 0.01:
        raise AIOutputValidationError(
            "correction", "Le barème fourni ne correspond pas à l'échelle de notation demandée."
        )

    return payload
