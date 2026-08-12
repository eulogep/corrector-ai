# Runbook d’observabilité et de performance

Ce document explique comment interpréter les signaux de production de Corrector AI sans exposer le contenu des copies, des prompts ou des secrets. Il complète le [guide de déploiement](DEPLOYMENT.md).

## 1. Partir d’une requête précise

Chaque réponse HTTP contient `X-Request-ID` et `X-Response-Time-Ms`. Lorsqu’un enseignant signale une lenteur ou une erreur, demandez d’abord ces deux valeurs, l’heure approximative et l’endpoint concerné. Recherchez ensuite l’identifiant dans les journaux JSON de l’application.

```bash
docker compose logs corrector-ai | grep '<X-Request-ID>'
```

Les événements `ai_call_started`, `ai_call_finished`, `ai_call_failed` et `ai_retry_scheduled` permettent de reconstituer le parcours d’une opération. Ils indiquent le fournisseur, l’opération, le résultat, le code d’erreur et la durée, mais ne doivent contenir ni copie, ni prompt, ni identité d’élève.

| Signal de trace | Interprétation | Action initiale |
|---|---|---|
| `ai_call_finished` | Appel fournisseur terminé correctement | Comparer la durée aux P50/P95 Grafana |
| `ai_call_failed` avec `ai_provider_unavailable` | Incident ou limite côté fournisseur | Vérifier les réessais, puis la bascule |
| `ai_call_failed` avec `ai_invalid_response` | JSON ou contrat de sortie incompatible | Examiner le fournisseur/prompt, sans réessayer automatiquement |
| `ai_retry_scheduled` | Réessai transitoire planifié | Vérifier que le volume reste faible |
| `subject_cache_result: hit` | Sujet déjà analysé servi depuis Redis | Mesurer le gain de latence et le taux de hit |

## 2. Lire Grafana et Prometheus

Après tunnel SSH, ouvrez Grafana sur `http://localhost:3000` et sélectionnez le tableau **Corrector AI — Observabilité IA**. Commencez par une période de six heures, puis resserrez autour d’un incident. Comparez toujours la latence, le taux d’erreur et les réessais dans la même fenêtre temporelle.

```bash
ssh -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 administrateur@serveur
```

| Panneau Grafana | Ce qu’il répond | Lecture utile |
|---|---|---|
| Débit des appels IA | Quel fournisseur et quelle opération reçoivent du trafic ? | Une hausse soudaine prépare souvent une saturation ou un quota |
| Taux d’erreur | Quel fournisseur échoue et à quelle fréquence ? | Distinguer un échec isolé d’une dérive persistante |
| Latence P95 | Quelle expérience subissent les 5 % de requêtes les plus lentes ? | Comparer Claude, DeepSeek, OCR et génération de barème |
| Réessais programmés | Les pannes transitoires augmentent-elles ? | Une hausse durable annonce une bascule ou une limite de quota |
| Codes d’erreur | L’échec est-il une configuration, une indisponibilité ou une sortie invalide ? | La réponse opérationnelle dépend du code |

### Requêtes PromQL utiles

```promql
# Taux global d'échec IA sur cinq minutes
sum(rate(corrector_ai_ai_calls_total{outcome="error"}[5m]))
/
clamp_min(sum(rate(corrector_ai_ai_calls_total[5m])), 0.001)

# Latence P95 par fournisseur et opération
histogram_quantile(
  0.95,
  sum(rate(corrector_ai_ai_call_duration_seconds_bucket[15m]))
  by (le, provider, operation)
)

# Réessais sur dix minutes
sum(increase(corrector_ai_ai_retries_total[10m])) by (provider, operation)

# Taux de hit du cache de sujets sur quinze minutes
sum(increase(corrector_ai_subject_cache_requests_total{result="hit"}[15m]))
/
clamp_min(
  sum(increase(corrector_ai_subject_cache_requests_total{result=~"hit|miss"}[15m])),
  1
)
```

## 3. Réessais et bascule fournisseur

Le backoff est contrôlé par `LLM_RETRY_MAX_ATTEMPTS`, `LLM_RETRY_BASE_SECONDS` et `LLM_RETRY_MAX_SECONDS`. L’appel initial compte dans le nombre maximal de tentatives. La configuration par défaut effectue donc au plus trois tentatives avec des délais courts et un léger jitter, puis bascule vers le fournisseur suivant s’il existe.

| Flux | Principal | Repli | Cas réessayés | Cas refusés immédiatement |
|---|---|---|---|---|
| Correction | Claude | DeepSeek | Indisponibilité fournisseur | Clé absente, barème invalide, sortie JSON invalide |
| Barème de sujet | Claude | DeepSeek | Indisponibilité fournisseur | Sujet illisible, clé absente, sortie JSON invalide |
| OCR | Gemini | Aucun dans cette version | Indisponibilité Gemini | Fichier invalide, clé absente, JSON OCR invalide |

Un taux élevé de réessais ne doit pas être masqué en augmentant aveuglément le nombre maximal de tentatives. Vérifiez d’abord les quotas, le statut fournisseur, les délais réseau et la fréquence de bascule. Les erreurs de contrat ne sont pas transitoires : une répétition augmenterait coûts et latence sans bénéfice.

## 4. Réduire la latence méthodiquement

La bonne optimisation dépend de la métrique qui se dégrade. Mesurez une ligne de base, ne changez qu’un paramètre à la fois, puis observez les P50/P95 et le taux d’erreur sur une période représentative.

| Symptôme | Optimisation prioritaire | Validation |
|---|---|---|
| P95 élevée sur les sujets répétés | Vérifier le taux de hit Redis et la TTL | Hausse des hits, baisse de durée `subject_rubric` |
| P95 élevée sur tous les appels | Réduire la taille de prompt et les tokens de sortie | Absence de troncature ou baisse de validité JSON |
| Échecs longs avant bascule | Garder des délais de connexion courts et plafonner les réessais | Baisse de `ai_provider_unavailable` et des temps de réponse |
| Saturation sous charge | Ajouter une limite de concurrence par fournisseur et une file de traitement | Baisse de `ai_calls_in_progress` et des erreurs 429 |
| OCR ou Claude bloque l’API | Conserver les SDK synchrones hors de la boucle asynchrone | Latence des endpoints non IA stable sous charge |
| Coût et délai de sujets longs | Extraire le texte une fois, tronquer de façon documentée et mettre le barème en cache | Régression contrôlée sur un corpus de référence |

Les optimisations suivantes sont volontairement **non appliquées automatiquement** : réduction agressive de `max_tokens`, augmentation du nombre de tentatives, cache de copies d’élèves et parallélisme massif. Elles exigent un benchmark sur corpus anonymisé et une validation pédagogique, de confidentialité et de coût.

## 5. Réponse aux alertes

| Alerte | Première vérification | Mesure corrective |
|---|---|---|
| `CorrectorAiTargetDown` | `docker compose ps`, `/healthz`, logs et disque | Restaurer le conteneur, la connectivité ou le volume avant d’augmenter la capacité |
| `CorrectorAiLlmErrorRateHigh` | Répartition des codes d’erreur et fournisseur affecté | Corriger configuration, quota ou fournisseur; surveiller la bascule |
| `CorrectorAiLlmP95LatencyHigh` | P95 par fournisseur/opération et réessais | Réduire le prompt, vérifier Redis, délais et saturation |
| `CorrectorAiRetryStorm` | Quotas, réseau et statut fournisseur | Réduire la concurrence ou désactiver temporairement le fournisseur défaillant |
| `CorrectorAiProviderUnavailable` | Test de connectivité et clés sans les afficher | Vérifier la bascule et escalader vers le fournisseur si nécessaire |

Après tout incident, conservez une chronologie sans données élèves : heure de début, requêtes concernées, métriques, action prise, résultat et mesure de prévention. Cette discipline permet d’ajuster les seuils avec des données plutôt que par intuition.
