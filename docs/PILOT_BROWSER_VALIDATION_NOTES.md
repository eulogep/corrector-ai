# Notes de validation navigateur — pilote synthétique

Date : 12 août 2026.

L’instance Render `https://corrector-ai.onrender.com/` a été rechargée après publication du commit `40d5dc0`. La page d’authentification ainsi que les sections de revue humaine et de pilotage sont servies correctement.

Le formulaire d’inscription a été renseigné avec le compte de test non personnel `pilot.autotest.20260812@example.test` (identité synthétique). Après activation de « Créer mon compte », l’interface est restée sur le formulaire, sans redirection, authentification ni message d’erreur visible. Cette observation doit être investiguée avant de poursuivre le parcours de correction : elle indique soit une erreur JavaScript résiduelle, soit une réponse HTTP d’inscription non traitée par l’interface.

Aucune donnée d’élève réelle, copie réelle ou clé fournisseur n’a été utilisée dans cette étape.

## État Render observé

Au contrôle effectué depuis le tableau de bord Render, le commit `40d5dc0` est bien identifié comme « Deploying next » et l’événement « Deploy started » est présent. Le service actuellement actif reste `4aa3373`, ce qui explique que `https://corrector-ai.onrender.com/app.js` serve encore `const API = 'http://localhost:8000';`. Le test d’inscription ne doit pas être interprété comme un échec du correctif : il a été exécuté sur l’ancienne version pendant le déploiement.

## Déploiement et authentification confirmés

Le 12 août 2026, le JavaScript publié par Render a été contrôlé directement : il contient désormais `const API = window.location.protocol === 'file:' ? 'http://localhost:8000' : window.location.origin;`. L’endpoint public `GET /healthz` retourne `{"status":"ok"}`.

Les journaux applicatifs Render confirment ensuite la réussite du parcours sur la nouvelle instance : `POST /api/auth/register` a retourné `200 OK`, suivi de `GET /api/stats/dashboard` en `200 OK`. Le compte synthétique a donc été créé et authentifié ; l’absence de bascule visible dans la capture immédiate du navigateur était un artefact de rafraîchissement de l’outil, et non un échec fonctionnel.

## Préparation du scénario de correction

Le compte de test authentifié a créé avec succès l’élève entièrement fictif « Élève Test », classe « 4ème A », sans adresse électronique. Cette absence d’adresse garantit qu’aucun envoi de rapport ne peut être adressé à une personne pendant le pilote.

## Contrôle du 12 août 2026 après sortie de veille

Le sandbox est disponible mais sa résolution DNS reste indisponible. La navigation reconnectée a réveillé l’instance Render ; après le délai normal de démarrage de l’offre gratuite, `GET /healthz` a de nouveau retourné `{"status":"ok"}`.

La session du compte synthétique est toujours utilisable dans le navigateur, mais le tableau de bord et la liste des élèves indiquent désormais zéro élève. L’élève fictif créé lors du contrôle précédent n’a donc pas survécu au redémarrage de l’instance. Cette observation établit un risque bloquant de persistance des données : l’instance Render actuelle n’offre pas de stockage durable effectif pour la base SQLite du pilote.

## Diagnostic confirmé par les journaux Render

La tentative de recréer l’élève fictif après le réveil de l’instance a échoué. Les journaux Render montrent une erreur `sqlite3.IntegrityError: FOREIGN KEY constraint failed` dans `create_student`. Le jeton JWT présent dans le navigateur conserve l’identifiant du professeur synthétique, mais la ligne correspondante n’est plus présente dans la base SQLite nouvellement initialisée. L’application accepte donc un jeton dont le compte sous-jacent a disparu, puis produit une erreur `500` lors de l’insertion de l’élève.

Deux défauts distincts sont ainsi confirmés : le stockage SQLite local n’est pas durable sur l’instance Render actuelle, et l’authentification doit vérifier l’existence du professeur en base avant d’autoriser les routes protégées. Ce dernier point doit être corrigé pour transformer une erreur interne en réponse d’authentification explicite.

## Recréation contrôlée du compte pilote

Après avoir constaté que le JWT ne correspondait plus à une ligne `professors`, la session synthétique a été explicitement fermée. Un nouveau compte de test est en cours de création dans l’instance SQLite actuellement active. Cette recréation ne résout pas le défaut de persistance ; elle permet seulement de poursuivre les vérifications de l’instance vivante sans réutiliser un jeton orphelin.

La recréation du compte de test a été soumise avec une identité et une adresse entièrement synthétiques, sans aucune donnée d’élève réelle. La confirmation visuelle immédiate reste au formulaire ; la réponse est vérifiée côté serveur dans l’étape suivante afin d’éviter toute interprétation fondée sur l’interface seule.

## Création synthétique réussie dans l’instance active

Les journaux Render confirment `POST /api/auth/register` en `200 OK`. La session nouvellement créée a ensuite permis l’ajout réussi de l’élève totalement fictif « Élève Test », classe « 4ème A », sans adresse électronique. L’interface confirme « Élève ajouté » et affiche la fiche. Le compte et l’élève sont donc utilisables tant que l’instance actuelle reste active, mais ils seront perdus au prochain redémarrage ou à la prochaine mise en veille de ce service Free tant qu’aucun stockage durable n’est configuré.

## Mesures de fiabilisation du stockage

La documentation officielle de Render confirme que les services Web Free perdent toute modification du système de fichiers local — notamment les bases SQLite — lors d’un redéploiement, redémarrage ou passage en veille. Elle précise que les disques persistants ne sont disponibles que pour les services payants. La voie sans disque proposée par Render consiste à utiliser Render Postgres, y compris sur l’offre Free, mais cette base expire après 30 jours et ne dispose pas de sauvegardes managées. Sources : <https://render.com/docs/free> et <https://render.com/docs/disks>.

Pour un pilote réel, la décision technique requise est donc : migrer immédiatement les données relationnelles vers Postgres (solution de pilote à durée limitée) ou passer le service Web sur une offre compatible avec un disque persistant, en écrivant la base et les fichiers de copie sous le point de montage dédié. Dans les deux scénarios, SQLite locale ne doit plus être considérée comme un stockage de production.

## Correctif de session et publication

Le correctif de validation des sessions orphelines a été ajouté avec son test de régression : un token JWT dont le professeur n’existe plus en base retourne désormais `401 Session expirée` au lieu de provoquer une erreur interne à l’insertion d’un élève. La suite backend compte maintenant 38 tests réussis. Le commit `1688557` a été publié sur `main`. À la dernière vérification, Render avait démarré son déploiement automatique à 15:14 et le statut était encore « In Progress ».

## Préparation Supabase

Le compte Supabase de l’utilisateur est accessible dans l’organisation « Euloge's projects » (plan Free, géré via Vercel Marketplace). Les projets existants listés sont distincts et en pause. Un nouvel espace dédié à Corrector AI est en cours de création afin de ne pas mélanger les données du pilote avec les autres projets. Les quotas affichés sont de 500 Mo pour la base et 1 Go pour le stockage de fichiers.

Le formulaire de projet Supabase dédié est ouvert. Un mot de passe PostgreSQL fort a été généré par la plateforme et n’a été ni copié ni enregistré dans les notes. La région Europe est sélectionnée ; la politique à appliquer est de conserver l’API de données mais de désactiver l’exposition automatique des nouvelles tables, afin que les droits soient attribués explicitement.

Le projet est nommé `corrector-ai-pilot`. L’exposition automatique des nouvelles tables a été désactivée. L’API de données reste activée pour le backend ; l’activation automatique de la RLS est disponible et doit être appliquée avant création afin que les tables de données scolaires soient protégées dès leur création.

La création du projet `corrector-ai-pilot` a été soumise avec les mesures de sécurité suivantes : API de données activée, exposition automatique des tables désactivée et activation automatique de la RLS activée. L’initialisation du projet est en cours ; aucun secret de base n’a été copié dans la documentation ni dans le dépôt.

Le projet Supabase `corrector-ai-pilot` est sain et hébergé en Europe de l’Ouest (Irlande). La connexion PostgreSQL directe est disponible ; l’URL de connexion sera placée uniquement dans la variable secrète `DATABASE_URL` du service Render, jamais dans le dépôt ni dans les notes de pilote.

La navigation vers l’espace Supabase Storage du projet a été initiée après fermeture du panneau de connexion. Le bucket qui contiendra les copies et les sujets sera privé ; aucune URL publique ou clé de lecture ne sera exposée au frontend.

Le formulaire de bucket Supabase confirme que le bucket sera privé par défaut. La création sera faite sous le nom technique `corrector-private`, avec une limite de taille et une liste de types MIME autorisés, afin de correspondre à la limite applicative de 10 Mo et aux formats effectivement acceptés.

La limite de taille du bucket privé est activée. Elle sera fixée à 10 Mo, identique à la limite FastAPI, afin que les fichiers rejetés par Supabase ne soient jamais plus gros que ceux acceptés par le backend.

La restriction MIME du bucket privé est activée. Les seuls types admis seront JPEG, PNG, WebP, PDF et documents Word, cohérents avec les formats applicatifs de copies et de sujets ; le bucket demeure non public.

Réglages finalisés avant création : bucket non public, quota strict de 10 Mo par objet et MIME autorisés limités à `image/jpeg`, `image/png`, `image/webp`, `application/pdf`, `application/msword` et document Word OpenXML. Le bouton de création est disponible.

L’éditeur SQL Supabase a chargé le script complet mais a refusé son exécution avec l’erreur d’interface « query: Too small: expected string to have >=1 characters », y compris via le raccourci Ctrl+Entrée. Aucune table n’a été confirmée comme créée par cette interface. Le schéma reste versionné dans `backend/migrations/001_supabase_postgres.sql` et sera appliqué automatiquement par `init_db()` au premier démarrage Render avec `DATABASE_URL` configurée, puis vérifié par les journaux et les routes de l’application.

La connexion Supabase retenue est le **pool transactionnel**, adapté aux connexions brèves créées par la couche de données actuelle de Corrector AI. L’URL PostgreSQL de ce pool sera placée exclusivement dans le secret `DATABASE_URL` de Render avec le chiffrement TLS requis.

Le panneau de connexion Supabase a bien sélectionné le pool transactionnel. Son interface n’a pas révélé la chaîne complète malgré le défilement, sans incidence sur le choix technique : la variable `DATABASE_URL` sera définie via les paramètres de connexion sécurisés du projet et validée au prochain démarrage Render.

La clé secrète Supabase du projet a été copiée uniquement dans le presse-papiers du navigateur pour un transfert direct vers la configuration secrète Render. Elle n’a été ni affichée intégralement, ni placée dans les fichiers, notes ou sorties de commande. L’URL publique du projet est enregistrée comme `SUPABASE_URL`; les données du bucket restent privées.

Le formulaire d’édition des variables d’environnement Render est ouvert. Les valeurs Supabase seront ajoutées comme secrets : `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET` et `REQUIRE_PERSISTENT_STORAGE`. Aucun secret n’est consigné dans cette note.

La page de gestion des clés API Supabase est accessible. Une clé secrète de projet est disponible pour le backend ; elle doit être conservée exclusivement dans Render. La tentative de transfert par presse-papiers a été abandonnée après détection d’un contenu local non fiable, sans sauvegarde de valeur erronée.

Avec l’autorisation explicite de l’utilisateur, la configuration Render est reprise directement. Les variables Supabase existantes seront renseignées avec leurs valeurs correctes dans Render ; les secrets restent exclus des notes, du dépôt et des messages utilisateur.

La configuration Render est en cours de finalisation avec une URL PostgreSQL transactionnelle chiffrée, le bucket privé et les paramètres Supabase. Les secrets ont été saisis directement dans Render avec l’autorisation de l’utilisateur et ne sont pas reproduits dans cette trace.

Le service Render est connecté. Son réglage de notification actuel est « Use workspace default (Only failure notifications) ». Il sera remplacé par une notification de service couvrant tous les événements de déploiement, afin de signaler aussi les réussites et permettre un suivi explicite du pilote.

La politique Render de **notifications de service est activée sur « All notifications »**. Le propriétaire du service recevra donc les avis e-mail Render pour les déploiements réussis, échoués et les événements de service, en complément des alertes Prometheus/Alertmanager déjà versionnées.
