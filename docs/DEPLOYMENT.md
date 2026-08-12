# Déploiement de production — Corrector AI

Ce guide déploie Corrector AI sous Docker Compose avec un volume persistant pour SQLite, les documents chargés et les rapports. Il ajoute Prometheus pour les métriques et Caddy pour l’exposition HTTPS. Les appels OCR et LLM ne renvoient jamais de contenu simulé : une clé absente ou un fournisseur indisponible produit une erreur explicite.

> **Précondition pédagogique et RGPD :** les copies et données d’élèves doivent être hébergées dans une région et sur une infrastructure compatibles avec les obligations de votre établissement. Les notes générées restent des propositions à valider par l’enseignant.

## Choisir le mode de déploiement

| Approche | Usage | Atouts | Limites |
|---|---|---|---|
| **Docker Compose avec ce guide** | Serveur Linux, machine de l’établissement ou VPS que vous administrez | Contrôle du stockage, des sauvegardes, du réseau, de la version et du monitoring | Vous gérez les mises à jour, les certificats et les alertes |
| **Hébergement applicatif managé** | Besoin léger sans administration système | Mise en ligne plus rapide et exploitation simplifiée | Docker, le proxy et Prometheus ne sont pas pilotés par ce dépôt ; vérifier l’emplacement des données et les volumes persistants |

La suite du document couvre la première approche, exigée lorsqu’un déploiement Docker contrôlé est souhaité.

## 1. Architecture livrée

```text
Internet ── HTTPS :443 ── Caddy ── Corrector AI :8000 ── volume Docker /data
                                      │                  ├─ SQLite
                                      │                  ├─ uploads
                                      │                  ├─ rapports PDF
                                      │                  └─ cache Docling
                                      └─ Prometheus :9090 (privé, collecte /metrics)
```

| Fichier | Rôle |
|---|---|
| `Dockerfile` | Image Python 3.11 non privilégiée, endpoint de santé et dépendances Docling |
| `docker-compose.yml` | Application, volume persistant et configuration de sécurité minimale |
| `docker-compose.monitoring.yml` | Prometheus, rétention locale de 30 jours et collecte authentifiée |
| `docker-compose.proxy.yml` | Caddy et certificats TLS automatiques pour un domaine public |
| `monitoring/prometheus.yml` | Configuration de collecte de `/metrics` |
| `docker/Caddyfile` | Reverse proxy HTTPS vers l’application |

## 2. Prérequis serveur

Utilisez un hôte Linux 64 bits administré par votre organisation. Installez Docker Engine et le module Compose conformément à la documentation officielle de Docker. Le serveur doit disposer d’espace disque durable pour les copies, les rapports et les modèles documentaires ; prévoyez des sauvegardes externes du volume Docker.

Si vous activez l’exposition HTTPS avec Caddy, le nom de domaine doit déjà pointer vers l’IP publique du serveur et les ports TCP **80** et **443** doivent être ouverts. Le port 8000 de l’application et le port 9090 de Prometheus restent liés à `127.0.0.1` : ils ne doivent pas être exposés directement sur Internet.

```bash
git clone https://github.com/eulogep/corrector-ai.git
cd corrector-ai
```

## 3. Préparer les secrets

Le fichier `.env.production` contient les clés de fournisseurs et les paramètres SMTP. Il n’est pas versionné. Le jeton Prometheus est séparé dans un fichier monté en lecture seule, afin de ne pas le transmettre à l’application sous forme de variable d’environnement ordinaire.

```bash
cp .env.docker.example .env.production
chmod 600 .env.production
mkdir -p .secrets
umask 077
openssl rand -hex 32 > .secrets/metrics_token
chmod 600 .secrets/metrics_token
```

Éditez ensuite `.env.production` et renseignez les clés réelles. Une configuration minimale est présentée ci-dessous.

```dotenv
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=...
DEEPSEEK_API_KEY=...
JWT_SECRET_KEY=une_valeur_aleatoire_longue
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
```

| Variable | Requise pour | Commentaire |
|---|---|---|
| `GEMINI_API_KEY` | OCR de copies et OCR de repli pour sujets scannés | Requise dès qu’un endpoint OCR est utilisé |
| `ANTHROPIC_API_KEY` | Barèmes automatiques et fournisseur principal de correction | Recommandée pour le flux complet |
| `DEEPSEEK_API_KEY` | Repli de correction | Réduit l’indisponibilité d’un fournisseur unique |
| `JWT_SECRET_KEY` | Jetons de connexion | Valeur aléatoire, propre à chaque environnement |
| `SMTP_*` | Envoi des rapports PDF | Facultatif |
| `.secrets/metrics_token` | Lecture Prometheus de `/metrics` | Ne pas réutiliser le secret JWT |

> Ne placez jamais de clés dans une image Docker, un `Dockerfile`, une issue, une capture d’écran ou un commit. Renouvelez immédiatement toute clé exposée.

## 4. Vérifier et lancer l’application

Validez la configuration avant la première mise en ligne. La commande suivante résout les variables et vérifie la syntaxe Compose sans démarrer de service.

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.monitoring.yml \
  config >/dev/null
```

Démarrez ensuite l’application et Prometheus. Le premier démarrage peut être plus long si Docling doit initialiser ses composants.

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.monitoring.yml \
  up --build --detach

# Vérifier l’état et le contrôle de santé
docker compose ps
curl --fail http://127.0.0.1:8000/healthz
```

La réponse attendue est :

```json
{"status":"ok"}
```

Les journaux applicatifs sont disponibles sans afficher les prompts, réponses ou noms d’élèves dans le tracing IA.

```bash
docker compose logs --follow corrector-ai
```

## 5. Activer HTTPS avec Caddy

Définissez le domaine public et l’adresse de notification ACME uniquement dans votre session shell ; elles ne sont pas des secrets applicatifs.

```bash
export DOMAIN=corrector.exemple.fr
export ACME_EMAIL=administration@exemple.fr

docker compose \
  -f docker-compose.yml \
  -f docker-compose.monitoring.yml \
  -f docker-compose.proxy.yml \
  up --build --detach
```

Caddy obtient et renouvelle les certificats TLS, puis transmet les requêtes à `corrector-ai:8000` sur le réseau Docker interne. Vérifiez l’URL publique, l’authentification, un téléchargement de test non sensible et le rapport PDF avant l’ouverture aux utilisateurs.

## 6. Monitoring et tracing des appels IA

Chaque appel Gemini, Claude ou DeepSeek produit un événement JSON de début et de fin avec : `trace_id`, `request_id`, fournisseur, opération, résultat, code d’erreur et durée en millisecondes. Les journaux **n’incluent pas** les prompts, réponses, copies, noms, emails, tokens ou clés API.

Chaque réponse HTTP reçoit aussi les en-têtes `X-Request-ID` et `X-Response-Time-Ms`. Conservez le `X-Request-ID` lors d’un signalement : il permet de relier la requête aux événements d’observabilité correspondants.

Prometheus collecte `/metrics` toutes les 30 secondes via le token contenu dans `.secrets/metrics_token`. Son interface est privée sur `http://127.0.0.1:9090` ; accédez-y au besoin via un tunnel SSH plutôt que par une publication Internet directe.

```bash
ssh -L 9090:127.0.0.1:9090 administrateur@serveur
# Ouvrir ensuite http://localhost:9090
```

| Métrique | Usage opérationnel |
|---|---|
| `corrector_ai_ai_calls_total` | Volume de requêtes par fournisseur, opération et résultat |
| `corrector_ai_ai_call_errors_total` | Erreurs par code contrôlé : absence de clé, indisponibilité ou JSON invalide |
| `corrector_ai_ai_call_duration_seconds` | Latence des appels OCR, barème et correction ; utilisable en P50/P95 |
| `corrector_ai_ai_calls_in_progress` | Appels IA simultanés et détection de saturation |

Exemples de requêtes PromQL :

```promql
# Taux d'erreurs sur cinq minutes
sum(rate(corrector_ai_ai_calls_total{outcome="error"}[5m]))
/
sum(rate(corrector_ai_ai_calls_total[5m]))

# Latence P95 de correction sur quinze minutes
histogram_quantile(
  0.95,
  sum(rate(corrector_ai_ai_call_duration_seconds_bucket{operation="grading"}[15m])) by (le)
)
```

Configurez une alerte lorsque le taux d’erreurs IA dépasse votre seuil accepté, lorsque la latence P95 dégrade l’expérience utilisateur ou lorsqu’aucune métrique n’est reçue depuis plusieurs intervalles de collecte.

## 7. Exploitation courante

### Mettre à jour

Avant une mise à jour, sauvegardez le volume puis récupérez une version identifiée. Évitez de déployer directement une branche non testée sur le serveur de production.

```bash
# Depuis le répertoire du dépôt
git fetch --tags
git checkout <tag-ou-commit-approuve>
docker compose \
  -f docker-compose.yml \
  -f docker-compose.monitoring.yml \
  -f docker-compose.proxy.yml \
  up --build --detach
```

### Sauvegarder et restaurer

Le volume nommé `corrector_ai_data` contient la base SQLite, les uploads, les rapports et le cache de modèles. Sauvegardez-le régulièrement, chiffré et hors du serveur de production.

```bash
# Sauvegarde : à déposer dans un stockage chiffré et à accès restreint
mkdir -p backups
docker run --rm \
  -v corrector_ai_data:/source:ro \
  -v "$PWD/backups":/backup \
  alpine:3.20 \
  tar czf /backup/corrector-ai-data-"$(date +%F)".tar.gz -C /source .

# Restaurer uniquement après arrêt de l'application et validation de l'archive
docker compose down
docker run --rm \
  -v corrector_ai_data:/target \
  -v "$PWD/backups":/backup:ro \
  alpine:3.20 \
  sh -c 'rm -rf /target/* && tar xzf /backup/<archive>.tar.gz -C /target'
```

### Revenir en arrière

En cas de régression applicative, déployez le commit ou tag précédent connu comme valide avec la procédure de mise à jour. Le volume persistant n’est pas remplacé par cette opération ; vérifiez la compatibilité de tout changement de schéma SQLite avant une restauration de code.

## 8. Contrôles avant ouverture aux utilisateurs

| Contrôle | Validation attendue |
|---|---|
| Santé | `GET /healthz` répond `200` |
| Authentification | Création et connexion d’un compte de test réussies |
| OCR | Une copie de démonstration non sensible retourne une structure validée ou une erreur explicite |
| Correction | Le barème et la correction sont validés par un enseignant pilote |
| Monitoring | Prometheus marque la cible `corrector-ai` comme `UP` |
| TLS | Navigateur sans alerte de certificat et redirection HTTPS en place |
| Sauvegarde | Archive chiffrée créée et procédure de restauration testée sur un environnement isolé |
| Accès | Ports 8000 et 9090 non accessibles depuis Internet ; seules les routes HTTPS publiques sont exposées |

## 9. Arrêt contrôlé

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.monitoring.yml \
  -f docker-compose.proxy.yml \
  down
```

Cette commande arrête les conteneurs sans supprimer les volumes nommés. N’utilisez `docker compose down --volumes` qu’après vérification d’une sauvegarde exploitable, car cette option supprimerait les données persistantes.


## 10. Alertes Prometheus et tableau Grafana

L’extension `docker-compose.monitoring.yml` démarre désormais trois composants : Prometheus, Alertmanager et Grafana. Prometheus charge `monitoring/alerts.yml`; Alertmanager regroupe les alertes; Grafana provisionne automatiquement la source Prometheus et le tableau **Corrector AI — Observabilité IA**.

Avant le démarrage, créez le mot de passe administrateur Grafana, distinct de tous les autres secrets.

```bash
umask 077
openssl rand -base64 32 > .secrets/grafana_admin_password
chmod 600 .secrets/grafana_admin_password
```

Démarrez ou mettez à jour la stack de monitoring.

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.monitoring.yml \
  up --build --detach
```

Grafana est volontairement lié à `127.0.0.1:3000`. Accédez-y par tunnel SSH et connectez-vous avec l’utilisateur `admin` et le mot de passe contenu dans `.secrets/grafana_admin_password`.

```bash
ssh -L 3000:127.0.0.1:3000 administrateur@serveur
# Ouvrir ensuite http://localhost:3000
```

| Alerte | Condition | Réaction opérationnelle recommandée |
|---|---|---|
| `CorrectorAiTargetDown` | Prometheus ne peut plus collecter l’API pendant 2 minutes | Vérifier les conteneurs, `healthz`, le volume et les journaux |
| `CorrectorAiLlmErrorRateHigh` | Plus de 10 % d’échecs IA pendant 10 minutes | Distinguer erreur de clé, JSON invalide et fournisseur indisponible dans Grafana |
| `CorrectorAiLlmP95LatencyHigh` | P95 supérieure à 12 secondes pendant 15 minutes | Identifier le fournisseur ou l’opération lente; vérifier les réessais |
| `CorrectorAiRetryStorm` | Plus de 20 réessais en 10 minutes | Contrôler les limites de quotas, le réseau et l’état du fournisseur |
| `CorrectorAiProviderUnavailable` | Échecs persistants d’un fournisseur pendant 10 minutes | Vérifier la bascule, le statut fournisseur et les clés; envisager de désactiver temporairement le fournisseur défaillant |

Alertmanager est livré avec un récepteur `discard` sûr par défaut : les alertes sont visibles dans Prometheus et Grafana mais ne sont pas expédiées à un tiers. Pour une notification e-mail, webhook ou messagerie, remplacez ce récepteur dans `monitoring/alertmanager.yml` et montez tout secret de canal sous `.secrets/`. Testez toujours le routage avec une alerte de démonstration avant de le considérer opérationnel.

Le tableau Grafana permet de suivre le débit par fournisseur/opération/résultat, le taux d’erreur par fournisseur, la latence P95, les réessais et les codes d’erreur. Il ne contient aucune donnée de copie ni d’identité élève.

## 11. Réessais exponentiels et bascule fournisseur

Les appels OCR Gemini, les corrections LLM et la génération de barèmes disposent maintenant de réessais limités. L’essai initial compte dans `LLM_RETRY_MAX_ATTEMPTS`; avec les valeurs par défaut, un fournisseur est appelé au maximum trois fois avec un délai de `0,5 s`, puis `1 s`, plafonné à `4 s` et légèrement désynchronisé par jitter. Après épuisement, Corrector AI bascule vers le fournisseur suivant lorsque celui-ci est configuré.

| Flux | Fournisseur principal | Repli | Réessaie | Ne réessaie jamais |
|---|---|---|---|---|
| OCR de copie | Gemini | Aucun fournisseur OCR alternatif dans cette version | Indisponibilité transitoire Gemini | Clé absente, fichier invalide, JSON OCR invalide |
| Correction de copie | Claude | DeepSeek | Indisponibilité transitoire du fournisseur courant | Barème invalide, contrat JSON non respecté, clé absente |
| Génération de barème | Claude | DeepSeek | Indisponibilité transitoire du fournisseur courant | Sujet illisible, contrat JSON non respecté, clé absente |

Cette séparation est intentionnelle : répéter une requête dont le JSON est structurellement invalide augmente le coût et la latence sans améliorer la probabilité d’un résultat correct. Les métriques `corrector_ai_ai_retries_total` et les événements `ai_retry_scheduled` rendent chaque réessai visible dans Prometheus et dans les journaux.

## 12. Réduire la latence LLM en production

La première source de ralentissement doit être identifiée dans Grafana, par fournisseur et opération, avant toute modification. Les optimisations suivantes sont classées par impact et risque.

| Optimisation | Effet attendu | Précaution |
|---|---|---|
| Réduire la taille des prompts | Diminue le temps réseau, de traitement et le coût | Ne retirer ni le barème ni les réponses nécessaires à une note vérifiable |
| Réduire `max_tokens` selon la tâche | Les réponses courtes sont produites plus vite | Mesurer le taux de troncature et conserver une marge pour les copies longues |
| Réutiliser les clients HTTP et fournisseurs | Évite les coûts répétés de connexion | Introduire un cycle de vie applicatif et des limites de concurrence testées avant activation |
| Exécuter les bibliothèques synchrones hors boucle asynchrone | Préserve la réactivité FastAPI sous charge | Claude et Gemini sont déjà exécutés via `asyncio.to_thread` dans cette version |
| Fixer des délais de connexion et de requête | Réduit l’attente lors d’une panne et déclenche plus tôt la bascule | Ne pas fixer un délai inférieur à la latence normale P95 observée |
| Limiter le parallélisme des corrections | Évite la saturation, les 429 et une tempête de réessais | Ajuster le seuil à partir de `ai_calls_in_progress` et des quotas fournisseur |
| Préparer et mettre en cache l’extraction des sujets | Évite de retraiter un même PDF lorsqu’un enseignant ajuste seulement le barème | Le cache doit avoir une durée limitée et respecter la politique de conservation des copies |
| Utiliser un parcours rapide pour l’aperçu | Répond plus vite lors d’une prévisualisation | Toute note finale doit toujours passer par le même contrôle de contrat et une validation humaine |

Les gains à faible risque déjà implémentés sont le passage hors boucle asynchrone des SDK synchrones Claude et Gemini, un délai de connexion HTTP DeepSeek de cinq secondes, une durée de requête DeepSeek de trente secondes, les réessais plafonnés et la bascule automatique. Avant de modifier les nombres de tentatives, les tokens ou les délais, observez sur plusieurs jours la latence P95, le taux d’erreur et le volume de réessais.
