# État de préflight du pilote

Contrôle réalisé le 12 août 2026 :

- La branche `main` contient le commit pilote `4aa3373` et est publiée sur GitHub.
- Docker n’est pas disponible dans l’environnement de validation local ; la composition Docker n’a donc pas été démarrée ici.
- Aucun fichier `.env.production` avec clés fournisseurs n’est présent dans l’environnement de validation.
- Une instance locale isolée a été démarrée et validée : `/healthz` retourne 200, `/metrics` est refusé sans jeton (403) et accessible avec un jeton (200), et une correction sans fournisseur IA retourne bien 503 avec le code `ai_provider_not_configured`.
- L’URL Render publique `https://corrector-ai.onrender.com/healthz` était en réveil lors du contrôle, avec affichage « Application loading ». Aucun test OCR ou LLM réel n’a été lancé sur cette instance.
- L’instance Render est à jour sur le commit `4aa3373` et les variables fournisseurs `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY` et `GEMINI_API_KEY` sont configurées. Leurs valeurs n’ont pas été consultées ni exportées.
