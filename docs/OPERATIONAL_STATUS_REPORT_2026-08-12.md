# Rapport opérationnel — Corrector AI

**Date :** 12 août 2026  
**Dépôt :** [`eulogep/corrector-ai`](https://github.com/eulogep/corrector-ai)  
**Environnement pilote :** [`https://corrector-ai.onrender.com`](https://corrector-ai.onrender.com)

## Conclusion exécutive

Le projet a franchi un cap important de fiabilisation : les sorties des fournisseurs IA sont validées par des schémas stricts, les échecs fournisseur sont explicites, les appels sont observables, la revue humaine est obligatoire avant toute note finale ou transmission de rapport, et l’interface déployée appelle désormais correctement l’API de son propre domaine. Le correctif frontend de même origine est effectivement déployé et l’authentification ainsi que l’ajout d’un élève fictif ont été vérifiés sur une instance active.

Le contrôle de terrain a cependant mis au jour un **bloquant de production** : la base SQLite locale est effacée lorsque le service Render Free redémarre ou sort de veille. Cela a supprimé le compte et l’élève synthétiques déjà créés, laissant un jeton JWT orphelin. Le défaut applicatif associé a été corrigé et publié dans le commit `1688557` : un jeton dont le professeur n’existe plus renvoie maintenant une erreur `401` explicite au lieu de provoquer une erreur interne de clé étrangère. Au moment du dernier contrôle, Render construisait encore ce commit.

> **Décision opérationnelle :** l’instance actuelle est adaptée à une démonstration éphémère, mais **ne doit pas accueillir un pilote réel ni des copies d’élèves** avant migration vers un stockage relationnel durable.

| Axe | État | Élément vérifié |
|---|---|---|
| Tests backend | **Validé** | 38 tests réussis en 4,17 s après le correctif de session. |
| Frontend déployé | **Validé** | Le JavaScript public utilise l’API de même origine, et non `localhost`. |
| Santé API | **Validé** | `GET /healthz` retourne `200` avec `{"status":"ok"}` après réveil. |
| Compte synthétique | **Créé sur instance active** | Inscription API confirmée par journal Render (`200`). |
| Élève synthétique | **Créé sur instance active** | « Élève Test », classe « 4ème A », sans adresse email. |
| Persistance des données | **Bloquante** | Perte constatée de SQLite après mise en veille/redémarrage. |
| Correctif sessions orphelines | **Publié, déploiement en cours** | Commit `1688557` sur `main`, état Render « In Progress » au dernier contrôle. |
| OCR et correction IA réels | **À reprendre après persistance** | Non exécutés sur une base qui peut disparaître à tout moment. |

## Corrections et améliorations livrées

Les livraisons successives ont transformé le prototype en base de pilote contrôlable. La validation Pydantic des sorties OCR, de barème et de correction refuse les champs inattendus et les réponses incomplètes. Les modes simulés de production ont été supprimés : l’absence d’un fournisseur ou une réponse IA invalide est remontée par un code HTTP métier plutôt que masquée par une note inventée.

| Domaine | Mesure appliquée | Bénéfice opérationnel |
|---|---|---|
| Sorties IA | Schémas Pydantic stricts et `extra="forbid"` | Évite l’acceptation silencieuse de JSON LLM ambigu ou incomplet. |
| Erreurs IA | Exceptions métier et gestionnaire FastAPI global | Réponses API explicites, sans fuite de secrets fournisseur. |
| Résilience | Réessais exponentiels bornés, délais asynchrones et fallback Claude/DeepSeek | Réduction des échecs transitoires et de la latence bloquante. |
| Observabilité | Métriques Prometheus, logs structurés et identifiants de requête | Analyse des appels, erreurs, durées, retries et cache sans contenu de copies. |
| Surveillance | Règles Prometheus, Alertmanager et dashboard Grafana | Détection de l’indisponibilité, du taux d’erreur, de la latence P95 et des tempêtes de retries. |
| Cache | Cache Redis isolé par professeur et dégradation gracieuse | Réduction des appels d’analyse de sujet sans partage inter-professeurs. |
| Gouvernance | Revue humaine obligatoire, audit, calibration et blocage de l’email avant approbation | La note IA reste une proposition jusqu’à la validation d’un correcteur. |
| Charge | Scénario Locust | Préparation aux essais concurrents et à la mesure de capacité. |
| Déploiement | Docker, Compose, TLS Caddy, documentation de production | Chemin de déploiement reproductible pour une cible hors Render Free. |

## Déploiement et parcours pilote observés

Le commit [`40d5dc0`](https://github.com/eulogep/corrector-ai/commit/40d5dc0) a corrigé le défaut qui rendait le site déployé inutilisable : le frontend appelait `http://localhost:8000`, qui désigne l’ordinateur du visiteur et non le backend Render. Il détermine maintenant l’URL API comme suit :

```javascript
const API = window.location.protocol === 'file:'
  ? 'http://localhost:8000'
  : window.location.origin;
```

Cette correction a été vérifiée dans le JavaScript réellement servi par Render. Le formulaire d’inscription a alors envoyé `POST /api/auth/register` avec une réponse `200`, et l’API de tableau de bord a répondu `200`. Un élève fictif sans email a été ajouté avec succès. Aucune identité réelle, copie réelle, adresse d’élève ou clé fournisseur n’a été utilisée lors de ce test.

Le service Free est entré en veille. Après réveil, l’endpoint `/healthz` a de nouveau répondu correctement, mais la liste d’élèves était vide. Une nouvelle insertion a alors échoué par `sqlite3.IntegrityError: FOREIGN KEY constraint failed` : le navigateur détenait encore un JWT pour un professeur supprimé avec la base locale. Le compte et l’élève ont été recréés dans l’instance active uniquement, puis la correction suivante a été ajoutée :

```text
JWT valide + professeur absent en base → 401 « Session expirée. Connectez-vous à nouveau. »
```

Le commit [`1688557`](https://github.com/eulogep/corrector-ai/commit/1688557) inclut cette protection ainsi qu’un test de non-régression. Il a été poussé sur la branche `main`; Render a déclenché automatiquement le déploiement, encore marqué « In Progress » lors de la dernière consultation.

## État de la navigation et du système

| Composant | Observation | Impact |
|---|---|---|
| Sandbox de vérification | Disponible ; charge ponctuelle observée, mais commandes et tests exécutables. | Les tests locaux sont exploitables. |
| DNS du sandbox | Résolution instable pour les domaines externes. | Le push GitHub a nécessité l’utilisation temporaire d’une adresse résolue, puis a abouti. |
| Navigateur connecté | Revenu à un état fonctionnel. | Tests Render, journaux et création synthétique effectués. |
| Render Free | Réveil observé après une mise en veille, avec page de chargement intermédiaire. | Délai perceptible avant le premier accès utilisateur. |
| API Render | `/healthz` renvoie `200` lorsque le service est démarré. | Backend et SQLite accessibles au moment du contrôle. |
| Déploiement `1688557` | En cours au dernier contrôle. | Contrôle final de `401` à refaire dès qu’il passe à « Deploy live ». |

## Risque critique de persistance

La cause racine est confirmée par la documentation Render : un service Web Free possède un système de fichiers éphémère. Les changements locaux, y compris une base SQLite et des fichiers envoyés, sont perdus lors d’un redéploiement, redémarrage ou passage en veille. Render précise également qu’un disque persistant n’est pas disponible pour un service Free. [1] [2]

| Option | Adaptation au pilote | Contraintes |
|---|---|---|
| **Render Postgres** | Meilleure solution immédiate sans disque local ; stocke comptes, élèves, corrections, audit et calibration hors du conteneur web. | Une base Postgres Free expire au bout de 30 jours et n’offre pas de sauvegardes managées. [1] |
| **Service Render payant + disque persistant** | Préserve SQLite et les fichiers écrits sous le point de montage configuré. | Le disque ne s’applique qu’au répertoire monté, n’est accessible que par une instance et implique une indisponibilité brève au redéploiement. [2] |
| **Postgres géré durable + stockage objet pour les copies** | Cible recommandée pour un vrai pilote : données relationnelles séparées des images/PDF, sauvegardes et montée en charge. | Nécessite une migration du code SQLite et une configuration de secrets côté serveur. |

> La recommandation technique est de **migrer immédiatement les données relationnelles vers Postgres**, puis de stocker les copies dans un stockage objet chiffré avec politiques de rétention. La solution SQLite + service Free ne doit rester qu’un environnement de démonstration sans données personnelles.

## Actions à effectuer avant le premier pilote réel

1. Attendre que Render passe le commit `1688557` à l’état **Deploy live**, puis vérifier qu’un JWT orphelin renvoie bien `401`.
2. Mettre en place Postgres et migrer les tables `professors`, `students`, `exams`, `review_audit_log` et `calibration_cases` ; ne pas créer de corpus réel avant cette étape.
3. Configurer un stockage durable des fichiers de copie et appliquer une rétention courte, des accès restreints et une suppression vérifiable.
4. Recréer le compte et l’élève synthétiques après la migration persistante, puis exécuter le scénario complet : barème manuel, OCR Gemini, correction IA, validation humaine, test du blocage d’email avant approbation et enregistrement de la calibration.
5. Constituer le corpus anonymisé de 30 à 50 copies et mesurer MAE, biais et part des notes à ±1 point avant toute utilisation pédagogique.

## Références

[1] [Render — Deploy for Free](https://render.com/docs/free)  
[2] [Render — Persistent Disks](https://render.com/docs/disks)  
[3] [Corrector AI — commit `40d5dc0`](https://github.com/eulogep/corrector-ai/commit/40d5dc0)  
[4] [Corrector AI — commit `1688557`](https://github.com/eulogep/corrector-ai/commit/1688557)
