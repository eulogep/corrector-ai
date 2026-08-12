"""Scénario Locust pour Corrector AI.

Par défaut, le test charge les chemins HTTP ne déclenchant pas de fournisseurs externes.
Définir LOCUST_INCLUDE_AI=true ajoute /api/grading/quick : cette option peut consommer des
quotas LLM et doit être utilisée uniquement avec des clés de test et une autorisation claire.
"""

from __future__ import annotations

import os
import time
import uuid

from locust import HttpUser, between, task


INCLUDE_AI = os.getenv("LOCUST_INCLUDE_AI", "false").lower() == "true"


class CorrectorAiUser(HttpUser):
    """Utilisateur enseignant simulé avec compte isolé par instance Locust."""

    wait_time = between(0.2, 1.0)

    def on_start(self) -> None:
        suffix = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
        self.email = f"load-{suffix}@example.invalid"
        self.password = "Locust-Test-Only-Change-Me"

        register_payload = {
            "email": self.email,
            "password": self.password,
            "nom": "Charge",
            "prenom": "Locust",
        }
        with self.client.post("/api/auth/register", json=register_payload, name="/api/auth/register") as response:
            if response.status_code != 200:
                response.failure(f"Inscription impossible : HTTP {response.status_code}")
                return

        with self.client.post(
            "/api/auth/login",
            json={"email": self.email, "password": self.password},
            name="/api/auth/login",
        ) as response:
            if response.status_code != 200:
                response.failure(f"Connexion impossible : HTTP {response.status_code}")
                return
            token = response.json().get("token")
            if not token:
                response.failure("Jeton JWT absent")
                return
            self.headers = {"Authorization": f"Bearer {token}"}

    @task(5)
    def health(self) -> None:
        self.client.get("/healthz", name="/healthz")

    @task(3)
    def dashboard(self) -> None:
        self.client.get("/api/stats/dashboard", headers=self.headers, name="/api/stats/dashboard")

    @task(2)
    def students(self) -> None:
        self.client.get("/api/students/", headers=self.headers, name="/api/students/")

    @task(1)
    def quick_grading(self) -> None:
        """Exercice facultatif : appelle réellement le pipeline de correction LLM."""
        if not INCLUDE_AI:
            return

        payload = {
            "matiere": "Mathématiques",
            "niveau": "4ème",
            "note_sur": 10.0,
            "exercices_corrige": [
                {
                    "numero": 1,
                    "enonce": "Calculer 2 + 2.",
                    "reponse_attendue": "4",
                    "points_max": 10.0,
                }
            ],
            "reponses_eleve": [{"numero": 1, "reponse_eleve": "4"}],
        }
        with self.client.post(
            "/api/grading/quick",
            json=payload,
            headers=self.headers,
            name="/api/grading/quick",
        ) as response:
            if response.status_code != 200:
                response.failure(f"Correction rapide : HTTP {response.status_code}")
