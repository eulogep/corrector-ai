# Persistance durable du pilote avec Supabase

> **Objectif.** Remplacer le fichier SQLite éphémère et le système de fichiers local d’un service Render Free par PostgreSQL et un bucket Supabase Storage privé.

## Architecture retenue

| Composant | Service | Rôle | Propriété de sécurité |
|---|---|---|---|
| Données métier | PostgreSQL Supabase | Professeurs, élèves, sujets, corrections, revue et calibration | Contraintes, index, audit et RLS activée sur chaque table |
| Documents | Supabase Storage, bucket `corrector-private` | Copies et sujets importés | Bucket non public, limite de 10 Mo, formats MIME restreints |
| Application | Render Web Service | API FastAPI et interface | Secrets injectés seulement au runtime |
| Notification | Render Service Notifications | Événements de déploiement et de service | Politique `All notifications` |

Le backend conserve des fichiers temporaires uniquement durant l’OCR ou l’analyse documentaire. Avant cette étape, il envoie l’objet dans Supabase Storage sous un chemin isolé par professeur. Après traitement, le fichier temporaire est supprimé. En pilote, `REQUIRE_PERSISTENT_STORAGE=true` interdit tout repli silencieux sur le disque éphémère.

## Variables de production

Les valeurs réelles sont des secrets Render et ne doivent jamais être ajoutées à Git, aux journaux ou aux tickets.

| Variable | Usage | Valeur indicative |
|---|---|---|
| `DATABASE_URL` | URI PostgreSQL Supabase du pool transactionnel | `postgresql://…?sslmode=require` |
| `SUPABASE_URL` | URL HTTPS du projet Supabase | `https://<project-ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Écriture serveur vers le bucket privé | Secret Supabase |
| `SUPABASE_STORAGE_BUCKET` | Bucket de copies et sujets | `corrector-private` |
| `REQUIRE_PERSISTENT_STORAGE` | Refuse un traitement non persistant | `true` en pilote/production |

Le pool transactionnel est privilégié car la couche de données ouvre des opérations courtes. Le connecteur PostgreSQL désactive les prepared statements automatiques afin de rester compatible avec PgBouncer.

## Schéma et démarrage

Le schéma versionné se trouve dans [`backend/migrations/001_supabase_postgres.sql`](../backend/migrations/001_supabase_postgres.sql). Au premier démarrage avec `DATABASE_URL`, `init_db()` applique ce schéma de façon idempotente. La migration n’altère pas la base SQLite locale : l’absence de `DATABASE_URL` conserve le mode de développement local.

Après un déploiement, vérifier dans les journaux Render l’initialisation sans erreur, puis créer un compte et un élève synthétiques. L’absence de persistance d’un compte après une veille/redéploiement indique que `DATABASE_URL` est absent ou que l’URI du pool ne peut pas être jointe.

## Contrôles de stockage

| Contrôle | Comportement attendu |
|---|---|
| Bucket non public | Aucun lien public de copie ou de sujet n’est généré |
| Taille maximale | Les objets supérieurs à 10 Mo sont rejetés avant et par le stockage |
| MIME autorisés | JPEG, PNG, WebP, PDF, DOC et DOCX uniquement |
| Panne Supabase avec garde-fou actif | HTTP 503 avec le code `persistent_storage_unavailable` |
| Panne Supabase hors pilote | Dégradation contrôlée vers le fichier temporaire local, à ne pas utiliser pour des données réelles |

## Déploiement et surveillance

Render est configuré pour déployer automatiquement la branche `main`. Les notifications de service sont réglées sur **All notifications**, ce qui envoie les événements de démarrage, succès, échec et incidents de service au canal de notification Render du propriétaire.

Les alertes Render ne remplacent pas Prometheus et Alertmanager : elles surveillent le cycle de déploiement, tandis que les règles versionnées dans `monitoring/alerts.yml` surveillent la disponibilité, les erreurs, la latence et les réessais applicatifs.

## Limites du plan gratuit

Supabase Free reste approprié à un pilote, pas à une conservation réglementaire définitive. Avant de traiter des copies réelles à l’échelle, définir une politique de rétention, un mécanisme d’export/sauvegarde chiffrée, la résidence des données appropriée et la base juridique applicable. Les copies doivent être anonymisées autant que possible pendant la calibration.
