#!/usr/bin/env python3
"""Exécute un parcours pilote synthétique contre une instance Corrector AI.

Les identifiants sont lus exclusivement depuis l'environnement. Le script ne
journalise jamais le JWT, le mot de passe, les réponses OCR complètes ni les
chaînes de connexion. Il s'arrête au premier contrôle métier invalide.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

BASE_URL = os.environ.get("PILOT_BASE_URL", "https://corrector-ai.onrender.com").rstrip("/")
PILOT_EMAIL = os.environ.get("PILOT_EMAIL", "")
PILOT_PASSWORD = os.environ.get("PILOT_PASSWORD", "")
COPY_PATH = Path(os.environ.get("PILOT_COPY_PATH", "performance/copie_test_pilote.png"))
OUTPUT_PATH = Path(os.environ.get("PILOT_RESULT_PATH", "docs/pilot_api_validation_result.json"))


class PilotValidationError(RuntimeError):
    """Raised when a pilot assertion fails without disclosing sensitive bodies."""


def request_json(
    session: requests.Session,
    method: str,
    path: str,
    *,
    expected: int | tuple[int, ...],
    **kwargs: Any,
) -> dict[str, Any]:
    """Call the API and expose only an endpoint and a status on failure."""
    response = session.request(method, f"{BASE_URL}{path}", timeout=120, **kwargs)
    expected_codes = (expected,) if isinstance(expected, int) else expected
    if response.status_code not in expected_codes:
        safe_detail = ""
        try:
            payload = response.json()
            detail = payload.get("detail") if isinstance(payload, dict) else None
            if isinstance(detail, dict) and detail.get("code") == "persistent_storage_unavailable":
                message = detail.get("message")
                if isinstance(message, str) and len(message) <= 200:
                    safe_detail = f" ({message})"
            elif isinstance(detail, str) and "stockage" in detail.lower() and len(detail) <= 200:
                # Les routes FastAPI standards peuvent sérialiser ce détail comme texte.
                safe_detail = f" ({detail})"
        except ValueError:
            pass
        raise PilotValidationError(
            f"{method} {path}: statut HTTP {response.status_code}, attendu {expected_codes}{safe_detail}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise PilotValidationError(f"{method} {path}: réponse JSON attendue") from exc


def main() -> int:
    if not PILOT_EMAIL or not PILOT_PASSWORD:
        raise PilotValidationError("PILOT_EMAIL et PILOT_PASSWORD doivent être définis")
    if not COPY_PATH.is_file():
        raise PilotValidationError(f"Copie synthétique absente: {COPY_PATH}")

    session = requests.Session()
    login = request_json(
        session,
        "POST",
        "/api/auth/login",
        expected=200,
        json={"email": PILOT_EMAIL, "password": PILOT_PASSWORD},
    )
    token = login.get("token")
    if not isinstance(token, str) or not token:
        raise PilotValidationError("La connexion n’a fourni aucun jeton de session")
    session.headers.update({"Authorization": f"Bearer {token}"})

    students = request_json(session, "GET", "/api/students/", expected=200).get("students", [])
    student = next(
        (
            item
            for item in students
            if item.get("nom") == "Test"
            and item.get("prenom") == "Élève"
            and item.get("classe") == "4ème A"
        ),
        None,
    )
    if not student or not isinstance(student.get("id"), int):
        raise PilotValidationError("Élève synthétique de pilote introuvable")

    with COPY_PATH.open("rb") as copy_file:
        ocr = request_json(
            session,
            "POST",
            "/api/ocr/extract",
            expected=200,
            files={"file": (COPY_PATH.name, copy_file, "image/png")},
        )

    extracted_exercises = ocr.get("exercices")
    image_path = ocr.get("image_path")
    if not isinstance(extracted_exercises, list) or len(extracted_exercises) < 2:
        raise PilotValidationError("L’OCR n’a pas produit les deux exercices attendus")
    if not isinstance(image_path, str) or not image_path:
        raise PilotValidationError("L’OCR n’a pas retourné de référence de stockage durable")

    extracted_by_number = {
        item.get("numero"): item.get("texte_brut", "")
        for item in extracted_exercises
        if isinstance(item, dict) and isinstance(item.get("numero"), int)
    }
    if not extracted_by_number.get(1) or not extracted_by_number.get(2):
        raise PilotValidationError("Les exercices OCR numérotés 1 et 2 sont requis pour le pilote")

    grade_payload = {
        "student_id": student["id"],
        "matiere": "Sciences",
        "niveau": "4ème",
        "date_examen": "2026-08-13",
        "note_sur": 20,
        "image_path": image_path,
        "exercices_corrige": [
            {
                "numero": 1,
                "enonce": "Expliquer la photosynthèse.",
                "reponse_attendue": (
                    "La photosynthèse permet aux plantes de produire de la matière organique "
                    "grâce à la lumière, à l’eau et au dioxyde de carbone, et libère du dioxygène."
                ),
                "points_max": 10,
            },
            {
                "numero": 2,
                "enonce": "Calculer 2 + 2.",
                "reponse_attendue": "2 + 2 = 4.",
                "points_max": 10,
            },
        ],
        "reponses_eleve": [
            {"numero": 1, "reponse_eleve": extracted_by_number[1]},
            {"numero": 2, "reponse_eleve": extracted_by_number[2]},
        ],
    }
    grading = request_json(session, "POST", "/api/grading/grade", expected=200, json=grade_payload)
    exam_id = grading.get("exam_id")
    if not isinstance(exam_id, int) or grading.get("review_status") != "pending_review":
        raise PilotValidationError("La correction n’est pas entrée dans la file de revue humaine")

    # Ne déclenche pas d’envoi : le code 409 doit intervenir avant SMTP et avant
    # toute transmission externe tant que le correcteur humain n’a pas validé.
    email_guard = request_json(
        session,
        "POST",
        "/api/reports/email",
        expected=409,
        json={"exam_id": exam_id, "to_email": "delivery.blocked@example.test"},
    )
    if "valid" not in str(email_guard.get("detail", "")).lower():
        raise PilotValidationError("Le blocage pré-revue ne retourne pas le motif attendu")

    queue = request_json(
        session,
        "GET",
        "/api/grading/reviews/queue?status=pending_review&limit=50",
        expected=200,
    )
    if exam_id not in {item.get("id") for item in queue.get("exams", []) if isinstance(item, dict)}:
        raise PilotValidationError("La copie pilote est absente de la file de revue")

    review = request_json(
        session,
        "POST",
        f"/api/grading/exams/{exam_id}/review",
        expected=200,
        json={
            "status": "approved",
            "comment": "Validation humaine — copie synthétique de pilote.",
            "final_note": 20,
            "final_appreciation": "Copie synthétique conforme au barème pilote.",
        },
    )
    if review.get("review_status") != "approved" or review.get("note_totale") != 20:
        raise PilotValidationError("La revue humaine synthétique n’a pas fixé la note finale attendue")

    calibration = request_json(
        session,
        "POST",
        "/api/grading/pilot/calibration",
        expected=200,
        json={
            "exam_id": exam_id,
            "reference_note": 20,
            "reference_note_sur": 20,
            "reference_source": "copie_synthetique_pilote",
            "notes": "Référence contrôlée sur copie synthétique.",
        },
    )
    metrics = request_json(session, "GET", "/api/grading/pilot/metrics", expected=200)
    detail = request_json(session, "GET", f"/api/grading/exams/{exam_id}", expected=200)

    summary = {
        "base_url": BASE_URL,
        "student_id": student["id"],
        "exam_id": exam_id,
        "ocr_exercise_count": len(extracted_exercises),
        "durable_storage_reference_recorded": True,
        "ai_note_sur_20": grading.get("ai_note_totale"),
        "review_status": detail.get("review_status"),
        "final_note_sur_20": detail.get("note_totale"),
        "email_guard_status": 409,
        "calibration_case_id": calibration.get("id"),
        "pilot_metrics": metrics,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "PILOT_OK "
        f"exam_id={exam_id} ocr_exercises={len(extracted_exercises)} "
        f"email_guard=409 review=approved calibration=recorded"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PilotValidationError as exc:
        print(f"PILOT_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
