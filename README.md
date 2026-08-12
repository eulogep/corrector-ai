# Corrector AI

![Tests](https://img.shields.io/badge/tests-pytest-0ea5e9.svg)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-2563eb.svg)](LICENSE)
[![Contributions](https://img.shields.io/badge/contributions-welcome-16a34a.svg)](CONTRIBUTING.md)
[![Stars](https://img.shields.io/github/stars/eulogep/corrector-ai?style=social)](https://github.com/eulogep/corrector-ai/stargazers)

> **Correction assistée de copies pour le système éducatif français.** Corrector AI structure les sujets, lit les réponses, génère une proposition de barème et produit un retour pédagogique détaillé. La note et le barème restent soumis à la validation de l’enseignant.

Corrector AI est une application open source, auto-hébergeable et pensée pour des flux de travail pédagogiques réels : OCR, barèmes, correction structurée, rapports, suivi des élèves et exploitation de production. Les sorties des fournisseurs IA sont validées par des contrats Pydantic stricts ; une erreur fournisseur ne devient jamais une note simulée.

**English summary.** Corrector AI is a self-hostable, teacher-supervised grading assistant for French educational workflows. It combines document extraction, OCR, strict structured LLM outputs, monitoring and deployment tooling. It never returns a fabricated grade when an AI provider is unavailable.

| Démarrer | Explorer | Participer |
|---|---|---|
| [Installation locale](#démarrage-rapide) | [API](#api-et-contrats) | [Guide de contribution](CONTRIBUTING.md) |
| [Déploiement Docker](docs/DEPLOYMENT.md) | [Runbook observabilité](docs/OBSERVABILITY.md) | [Signaler un bug](https://github.com/eulogep/corrector-ai/issues/new/choose) |
| [Démo](https://corrector-ai.onrender.com) | [Stratégie IA](#fiabilité-des-fournisseurs-ia) | [Sécurité](SECURITY.md) |

## Pourquoi ce projet

La correction de copies demande du temps, de la cohérence et une attention pédagogique soutenue. Corrector AI n’a pas vocation à remplacer le jugement d’un enseignant : il réduit le travail répétitif, structure les éléments de correction et signale les incertitudes afin que l’enseignant puisse prendre la décision finale.

| Besoin | Réponse de Corrector AI |
|---|---|
| Sujet PDF ou scanné | Docling, PyMuPDF et OCR Gemini en repli contrôlé |
| Barème exploitable | Extraction JSON validée : exercices, points, réponses attendues et confiance |
| Correction détaillée | Claude, avec DeepSeek comme bascule, points par exercice et feedback |
| Confiance opérationnelle | Validation Pydantic, erreurs HTTP explicites, traces corrélées et métriques Prometheus |
| Auto-hébergement | Docker, Redis, Prometheus, Grafana, Alertmanager et Caddy optionnel |

## Fonctionnalités principales

| Domaine | Capacités actuelles |
|---|---|
| OCR et documents | Upload de PDF ou images, extraction structurée par exercice, détection de lisibilité |
| Barèmes | Génération de barème depuis un sujet, total de points cohérent et validation humaine avant usage |
| Correction | Score par exercice, feedback constructif, appréciation et alerte d’anomalie contextualisée |
| Suivi pédagogique | Élèves, historique de copies, progression par matière, rapports PDF et export CSV |
| Fiabilité IA | Schémas stricts, erreurs normalisées, réessais bornés et repli Claude → DeepSeek |
| Exploitation | Santé applicative, Prometheus, Grafana, Alertmanager, Redis et scénario Locust |

## Démarrage rapide

### Docker Compose — recommandé pour une instance complète

```bash
git clone https://github.com/eulogep/corrector-ai.git
cd corrector-ai
cp .env.docker.example .env.production
# Renseigner les clés IA, JWT_SECRET_KEY et REDIS_PASSWORD dans .env.production
mkdir -p .secrets
umask 077
openssl rand -hex 32 > .secrets/metrics_token
openssl rand -base64 32 > .secrets/grafana_admin_password

docker compose \
  -f docker-compose.yml \
  -f docker-compose.monitoring.yml \
  up --build --detach
```

L’application est ensuite disponible localement sur `http://127.0.0.1:8000`, sa documentation sur `/docs`, Prometheus sur le port local `9090` et Grafana sur le port local `3000`. Le guide [DEPLOYMENT.md](docs/DEPLOYMENT.md) couvre TLS, sauvegardes, Redis, alertes, Locust et les procédures de retour arrière.

### Développement local

```bash
pip install -r backend/requirements.txt
cp .env.example .env
# Renseigner au moins JWT_SECRET_KEY, puis les clés IA nécessaires au flux testé.
python -m backend.app
```

Les endpoints IA répondent **503** lorsqu’aucun fournisseur n’est configuré. Ce comportement est volontaire : aucune transcription ou note de démonstration ne peut être confondue avec un résultat réel.

## API et contrats

La documentation interactive est disponible sur `GET /docs`. Les principaux groupes d’API sont l’authentification, les élèves, les sujets, l’OCR, les corrections, les rapports et le dashboard.

| Endpoint | Usage |
|---|---|
| `POST /api/subjects/parse` | Extraire un sujet et proposer un barème validé |
| `POST /api/subjects/validate` | Valider le barème avant persistance et correction |
| `POST /api/ocr/extract` | Produire une lecture OCR structurée par exercice |
| `POST /api/grading/quick` | Obtenir une correction sans sauvegarde |
| `POST /api/grading/grade` | Corriger et enregistrer une copie rattachée à un élève |
| `GET /healthz` | Vérifier la disponibilité de l’application |
| `GET /metrics` | Exposer les métriques Prometheus protégées par jeton |

## Fiabilité des fournisseurs IA

Chaque réponse Gemini, Claude ou DeepSeek est décodée et validée avant utilisation. Les champs inattendus, scores incohérents, exercices dupliqués, totaux incompatibles et JSON mal formé sont rejetés. Une sortie invalide n’est pas réessayée : elle requiert une correction de prompt ou de fournisseur.

Les indisponibilités transitoires suivent un backoff exponentiel borné. Avec la configuration par défaut, un fournisseur reçoit au maximum trois tentatives avec délais de `0,5 s`, puis `1 s`, plafonnés à `4 s`; après épuisement, le flux de correction ou de barème bascule de Claude vers DeepSeek lorsque celui-ci est configuré. L’OCR Gemini est réessayé, mais ne possède pas encore de second fournisseur.

| Réglage | Valeur par défaut | Rôle |
|---|---:|---|
| `LLM_RETRY_MAX_ATTEMPTS` | `3` | Tentatives totales, appel initial inclus |
| `LLM_RETRY_BASE_SECONDS` | `0.5` | Délai initial du backoff |
| `LLM_RETRY_MAX_SECONDS` | `4` | Plafond de délai par tentative |
| `SUBJECT_CACHE_TTL_SECONDS` | `86400` | Durée de cache des sujets déjà analysés |

## Observabilité et production

Chaque requête possède un `X-Request-ID`. Les appels IA produisent des traces JSON contenant l’opération, le fournisseur, le résultat, le code d’erreur et la durée, sans prompts, copies, noms, emails ou secrets. Grafana provisionne un tableau qui permet d’analyser débit, taux d’erreur, latence P95, réessais et erreurs par fournisseur.

| Signal | Lecture utile |
|---|---|
| `corrector_ai_ai_calls_total` | Volume de succès et d’échecs par fournisseur et opération |
| `corrector_ai_ai_call_duration_seconds` | Latence P50/P95 OCR, barème et correction |
| `corrector_ai_ai_retries_total` | Dégradation fournisseur ou limites de quota |
| `corrector_ai_subject_cache_requests_total` | Efficacité et disponibilité du cache Redis |

Les règles Prometheus alertent sur la cible indisponible, un taux d’échec supérieur à 10 %, une P95 supérieure à 12 secondes, une tempête de réessais et une indisponibilité fournisseur durable. Les modèles webhook et e-mail Alertmanager sont décrits dans le [guide de déploiement](docs/DEPLOYMENT.md).

## Réduire la latence sans sacrifier la qualité

Commencez par observer la P95 par fournisseur et opération dans Grafana. Réduisez ensuite le volume de prompt, adaptez `max_tokens` à la tâche, mettez en cache les sujets déjà traités, limitez le parallélisme selon les quotas, conservez des délais de connexion courts et réutilisez les clients réseau lorsque la charge le justifie. Les SDK synchrones Claude et Gemini sont déjà exécutés hors de la boucle FastAPI, tandis que DeepSeek dispose d’un délai de connexion court pour accélérer la bascule.

Le scénario `performance/locustfile.py` permet d’établir une ligne de base concurrente sans appels IA. L’option `LOCUST_INCLUDE_AI=true` ne doit être activée qu’en préproduction, avec des quotas de test approuvés.

## Utilisation responsable des données

Les données applicatives sont stockées localement dans SQLite et les résultats de sujets peuvent être mis en cache dans Redis. En revanche, l’OCR et les corrections envoient le contenu nécessaire aux fournisseurs IA configurés. Avant toute utilisation avec des élèves, votre établissement doit vérifier les conditions de traitement, la base légale, la conservation, les contrats fournisseurs et les droits d’accès applicables.

La validation humaine reste indispensable avant de communiquer une note. N’utilisez pas Corrector AI comme unique dispositif de décision à fort impact sur un élève.

## Contribuer

Les contributions sont les bienvenues : tests, documentation, accessibilité, connecteurs, exemples de déploiement, compatibilité d’OCR local et amélioration de la qualité pédagogique. Consultez [CONTRIBUTING.md](CONTRIBUTING.md), le [code de conduite](CODE_OF_CONDUCT.md), le [support](SUPPORT.md) et la [politique de sécurité](SECURITY.md).

Le workflow GitHub Actions est fourni comme modèle ; consultez [CI_SETUP.md](docs/CI_SETUP.md) pour l’activer avec un jeton disposant de la permission `workflows`.

Avant une pull request :

```bash
python -m pytest backend/tests/ -q
python -m compileall -q backend performance
```

## Feuille de route

Les prochaines priorités sont l’activation d’un second fournisseur OCR, une évaluation sur corpus anonymisé avec double correction humaine, le contrôle de concurrence par fournisseur, l’amélioration de l’accessibilité du frontend et des connecteurs institutionnels documentés.

## Licence

Corrector AI est distribué sous licence [MIT](LICENSE).

---

Si ce projet vous est utile, une étoile GitHub aide réellement d’autres enseignants, développeurs et établissements à le découvrir. Les retours concrets, issues bien décrites et contributions de documentation ont le même impact à long terme.
