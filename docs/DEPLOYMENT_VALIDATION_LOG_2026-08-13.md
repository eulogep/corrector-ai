# Journal de validation du déploiement — 13 août 2026

## Migration Google GenAI en cours

Le commit `0b21d78` (`fix: migrate OCR to official Google GenAI SDK`) a été publié sur `main` le 13 août 2026. Le tableau de bord Render, consulté avec une session authentifiée, a confirmé le démarrage de son déploiement automatique à 11:11. Au moment de cette observation, le service *live* restait sur `2433a00`.

Un diagnostic OCR exécuté avant l’achèvement de ce déploiement a donc interrogé l’ancienne version et a retourné `503 ai_provider_unavailable`, avec le message assaini : « Le modèle Gemini configuré est indisponible. » Ce résultat ne doit pas être interprété comme une régression de la migration. La validation doit être rejouée uniquement après confirmation du statut *Deploy live* pour `0b21d78`.

Aucune clé, donnée personnelle, copie réelle ni contenu fournisseur n’est reproduit dans ce journal.

## Déploiement confirmé

Le détail du déploiement Render confirme ensuite que `0b21d78` a atteint l’état **Live**. La construction a installé `google-genai 2.18.0` et `httpx 0.28.1`, puis le journal a confirmé `Application startup complete` et `Your service is live` à 11:17. Le diagnostic OCR peut désormais être relancé contre la version migrée.

## Contrôle après mise en production

Le tableau de bord Render confirme que `0b21d78` est actif depuis 11:17. Le diagnostic OCR rejoué contre cette version retourne encore `503 ai_provider_unavailable` avec le message assaini « Le modèle Gemini configuré est indisponible ». La migration du SDK est donc bien déployée et l’échec restant relève de l’accès effectif du projet Google au modèle configuré, non de la dépendance Python historique. La documentation officielle Gemini conserve `gemini-2.5-flash` parmi les endpoints disponibles et indique que les clés exposées peuvent être bloquées ; la prochaine vérification porte sur la configuration de la clé et du modèle dans l’environnement Render.

## Vérification de configuration

Le service Render est confirmé actif et relié à la branche `main`. Les paramètres généraux confirment le démarrage par Uvicorn et le déploiement automatique sur commit. Aucun secret n’a été consulté ni modifié lors de cette vérification. La valeur de `GEMINI_OCR_MODEL` reste à contrôler dans les variables d’environnement du service ; elle doit être ajustée seulement après avoir identifié un endpoint accessible par la clé du projet.

## Accès aux variables d’environnement

La page dédiée aux variables d’environnement du service Render est accessible. Les valeurs sont masquées par l’interface, conformément à l’attendu ; aucune valeur secrète n’a été révélée ni modifiée. La vérification suivante consiste à identifier seulement le nom et la valeur non sensible de `GEMINI_OCR_MODEL` depuis ce tableau, ou à modifier explicitement ce paramètre après sélection d’un endpoint compatible.

## Accès au compte Gemini du projet

Le navigateur a été basculé vers le compte Google associé au projet Gemini de production. La page de gestion des clés AI Studio du projet est ouverte pour un contrôle non destructif de l’état de la clé et de l’accès aux modèles. Aucune clé n’a été affichée, copiée, créée, supprimée ou modifiée au cours de cette opération.

## Mesure de sécurité — rotation préventive Gemini

Le compte Google du projet confirme l’existence de la clé affectée au projet Corrector AI, au niveau gratuit. L’ouverture de son panneau de détail peut révéler sa valeur dans l’interface ; conformément aux règles de sécurité, cette valeur n’est ni copiée ni retranscrite. Étant donné l’exposition antérieure de cette clé dans la session de diagnostic, une rotation préventive est engagée : une nouvelle clé dédiée sera créée pour le même projet, injectée uniquement dans le secret `GEMINI_API_KEY` de Render, validée par un OCR, puis l’ancienne clé sera supprimée.

## Préparation de la clé de remplacement

La création d’une clé de remplacement est préparée dans Google AI Studio. Le projet sélectionné est celui qui héberge Corrector AI et la nouvelle clé reçoit un nom d’exploitation explicite lié à Render. Aucune clé n’a encore été créée ou copiée à ce stade ; aucune donnée secrète n’a été écrite dans le dépôt ou dans ce journal.

## Mise à jour Render en cours

L’édition des variables d’environnement Render est ouverte. La clé de remplacement fournie par l’utilisateur sera renseignée exclusivement dans le champ masqué `GEMINI_API_KEY`, puis la configuration sera sauvegardée avec reconstruction et redéploiement. Aucune valeur de secret n’est inscrite dans ce journal ni dans les fichiers du dépôt.

## Secret Gemini remplacé — sauvegarde en attente

La clé de remplacement fournie a été saisie exclusivement dans le champ masqué `GEMINI_API_KEY` de Render. Le secret n’est pas reproduit ici. La configuration est prête à être sauvegardée avec reconstruction et redéploiement ; cette action sera suivie d’un diagnostic OCR réel avant toute suppression de l’ancienne clé.

## Déploiement de rotation déclenché

Render a confirmé l’enregistrement des variables d’environnement et le déclenchement d’un nouveau déploiement. La nouvelle clé Gemini est maintenant stockée uniquement dans le secret Render ; aucun secret n’est conservé dans le dépôt. La validation OCR reprendra dès que ce déploiement sera *live*.

## Suivi du redéploiement de rotation

Le redéploiement déclenché par la mise à jour de `GEMINI_API_KEY` est en phase de construction. Les journaux Render indiquent une résolution de dépendances lourde liée à `docling` et ses dépendances de traitement de documents ; aucune erreur de configuration, de base de données ou de secret n’est signalée à ce stade. Le diagnostic OCR restera différé jusqu’au statut *live*.

## Service actif après rotation

Les journaux Render confirment que le redéploiement lié au remplacement de `GEMINI_API_KEY` a construit l’application, terminé son initialisation FastAPI et atteint l’état *live*. La version exécute bien `google-genai 2.18.0` et `httpx 0.28.1`. Le diagnostic OCR de production peut maintenant être relancé contre la configuration de clé remplacée.

## Diagnostic OCR après rotation de clé

Le diagnostic OCR exécuté après confirmation du service *live* retourne encore `503 ai_provider_unavailable` avec le diagnostic assaini indiquant un modèle indisponible. La rotation de la clé est donc appliquée mais n’a pas, à elle seule, rétabli l’accès à l’endpoint de modèle configuré. L’étape suivante consiste à interroger la liste des modèles accessible par cette nouvelle clé, sans jamais afficher ni enregistrer sa valeur, afin de sélectionner un endpoint OCR réellement autorisé.

## Cause racine et modèle validé

Le diagnostic local effectué avec la clé de remplacement confirme que la clé peut lister 52 modèles et que `gemini-2.5-flash` déclare la capacité de génération, mais les appels de génération et d’interaction vers ce modèle retournent HTTP `404`. Ce même test, exécuté avec `gemini-3.5-flash`, réussit en texte comme en multimodal sur l’image de copie synthétique. Le correctif retenu est donc de remplacer la valeur OCR par défaut par `gemini-3.5-flash` : il s’agit d’un modèle explicitement testé avec la clé de production, sans altérer le mécanisme d’appel du SDK officiel.

## Déploiement du modèle OCR validé

Le commit `39dc292` (`fix: default OCR to tested Gemini model`) a été publié sur `main`. Render confirme le démarrage de son déploiement automatique à 11:48. La version active demeure `0b21d78` tant que cet événement n’a pas atteint l’état *live* ; aucun diagnostic OCR sur la nouvelle valeur par défaut ne doit être interprété avant cette confirmation.

## Correctif Gemini 3.5 actif

Le détail du déploiement Render confirme que `39dc292` est **Live**. Le service a démarré avec succès ; l’extraction OCR de pilote peut maintenant être testée contre le modèle validé `gemini-3.5-flash` et la clé remplacée.

## Validation OCR réussie, validation complète partiellement bloquée

Le diagnostic OCR de pilote contre `39dc292` retourne HTTP `200` avec la structure attendue (`nom_eleve_detecte`, `exercices`, `image_path`) : l’OCR Gemini réel est de nouveau opérationnel. Le parcours complet de pilote atteint ensuite la route de correction mais reçoit HTTP `503` sur `POST /api/grading/grade`. Cette seconde erreur concerne la phase LLM de notation, distincte de l’OCR ; elle doit être diagnostiquée avant de déclarer le parcours de correction intégralement validé.

## Repli de correction Gemini ajouté

Le diagnostic de parcours complet a confirmé que l’OCR et le stockage durable réussissent, tandis que la correction n’obtenait aucune sortie valide de Claude ni de DeepSeek et remontait donc `provider:correction`. Un troisième repli contrôlé a été ajouté : Gemini 3.5 Flash, déjà validé avec la clé de production. Il demande explicitement une réponse JSON et applique le même contrat Pydantic strict avant toute sauvegarde ; aucune note simulée n’est possible. Les tests ciblés de validation IA (21) et la suite backend complète (43) sont passés avant publication.

## Déploiement du repli de correction en cours

Render indique que le commit `34a9e28` (`fix: add Gemini grading fallback`) est en cours de déploiement. La précédente version `39dc292` reste active pendant la reconstruction. Le test intégral du pilote reste différé jusqu’à la confirmation explicite de l’état *live* de ce commit.

## Correctif de persistance PostgreSQL

La trace du pilote a isolé un défaut de compatibilité : le contrat Pydantic produit un booléen pour `correct`, alors que le schéma PostgreSQL pilote persiste explicitement cette colonne en entier contrôlé (`0` ou `1`). L’insertion normalise désormais ce booléen vers `int(bool(correct))`, ce qui préserve le contrat strict IA tout en respectant le schéma existant et SQLite. Le test de sauvegarde couvre maintenant ce cas et les tests ciblés (26) ainsi que la suite complète (43) passent avant publication.

## Déploiement du correctif PostgreSQL en cours

Render confirme le démarrage du déploiement automatique du commit `862d538` (`fix: normalize grading booleans for Postgres`). La précédente version avec le repli Gemini est toujours signalée *live* pendant cette reconstruction ; la validation finale reste volontairement en attente du nouveau statut *live*.

## Parcours pilote complet validé

Le commit `862d538` est confirmé *live* sur Render. Le parcours synthétique complet a réussi : authentification, lecture de l’élève de test, OCR réel avec deux exercices, persistance Supabase, correction via la chaîne de fournisseurs avec validation de schéma, création d’une proposition en attente de revue, blocage de l’e-mail avant validation humaine (`409`), revue approuvée, et enregistrement d’un cas de calibration. Le validateur retourne `PILOT_OK` avec `review=approved` et `calibration=recorded`.

## Rotation de secrets et contrôle post-rotation

La clé Gemini antérieure a été supprimée avec confirmation utilisateur depuis le projet Google Cloud historique ; la clé de remplacement associée au service reste distincte. `JWT_SECRET_KEY` a ensuite été remplacée dans Render par une valeur aléatoire et le déploiement est devenu *live*, ce qui invalide volontairement les sessions antérieures. Après rotation, `/healthz` répond toujours `200` et une nouvelle authentification fonctionne. Un appel OCR de production retourne toutefois `503` avec un diagnostic assaini indiquant une requête Gemini invalide pour le modèle configuré, tandis que le même appel multimodal au modèle `gemini-3.5-flash` réussit localement avec la clé de remplacement. La configuration Render du modèle OCR est donc en cours de vérification explicite avant nouvelle validation pilote.

## Vérification approfondie de l’OCR post-rotation

La variable `GEMINI_OCR_MODEL` n’était pas définie dans Render ; elle a été fixée explicitement à `gemini-3.5-flash`, et la clé de remplacement a été réenregistrée avant redéploiement. Le diagnostic OCR de production reste toutefois en échec `503` après cette mesure. La requête multimodale exacte de l’OCR, avec le même prompt, le même fichier PNG, le même SDK et la clé de remplacement, réussit localement. Les tests backend complets restent au vert (`43` tests). Une amélioration de classification sans fuite a été ajoutée pour distinguer, lors du prochain déploiement, une clé fournisseur rejetée d’une requête modèle réellement invalide.

## Invalidation de sessions renforcée

Après une rotation de secret de session suivie d’un redéploiement, une session navigateur antérieure est restée fonctionnelle. Pour rendre l’invalidation indépendante de toute éventuelle persistance de configuration fournisseur, le backend ajoute désormais une version de session (`JWT_TOKEN_VERSION=2`) dans chaque nouveau JWT et refuse tout jeton dont la version est absente ou différente. Cette mesure invalide explicitement toutes les sessions antérieures au déploiement de sécurité et est couverte par deux tests unitaires dédiés. La suite backend complète est au vert (`45` tests).

## Déploiement JWT et diagnostic d’authentification Gemini

Le déploiement `79718c5` est confirmé *live* sur Render. Le contrôle public `/healthz` retourne `{"status":"ok"}`. L’ancienne session navigateur est rejetée et le compte pilote peut ouvrir une nouvelle session, ce qui valide l’invalidation explicite par version de jeton. Le diagnostic OCR assaini retourne toutefois `503 ai_provider_unavailable` avec le message « L’authentification Gemini est refusée (clé API à vérifier) ».

La clé de remplacement a été saisie de nouveau dans le champ secret `GEMINI_API_KEY` de Render, puis le déploiement `dep-d9uvnmh5efls73djel90` a construit et démarré avec succès. Après cet état *live*, le même diagnostic retourne encore le même refus d’authentification. En parallèle, la reproduction locale de l’appel multimodal structuré, avec le même modèle, le même fichier synthétique et la même clé, réussit avec une réponse non vide. La divergence est donc spécifique au contexte hébergé, et ne relève ni du prompt OCR, ni du format de fichier, ni du SDK officiel, ni du modèle configuré.

Google AI Studio confirme que la clé est rattachée au projet Corrector AI et l’interface la traite comme une clé d’autorisation. Le compte Google disponible peut consulter l’entrée dans AI Studio mais ne dispose pas de `resourcemanager.projects.get` dans Cloud Console pour ce projet : les restrictions d’origine ou d’accès ne peuvent pas y être auditées ou modifiées par cette identité. Aucune valeur de clé, aucune donnée de copie et aucun détail brut de réponse fournisseur ne sont consignés dans ce journal.

## Repli OCR fournisseur ajouté

Afin de ne pas bloquer le traitement d’une copie réelle sur la disponibilité ou le refus ponctuel de Gemini, une chaîne OCR multi-fournisseur a été ajoutée. Gemini reste prioritaire. En cas d’échec contrôlé, Claude Vision est sollicité avec le même prompt, le support original encodé côté serveur et un modèle configurable par `CLAUDE_OCR_MODEL`. La réponse du repli suit exactement le même contrat Pydantic `OCRStructuredResult` avant tout retour à la route API ; une réponse vide, simulée ou hors contrat est rejetée explicitement.

Le repli ne requiert pas de nouveau secret : il exploite `ANTHROPIC_API_KEY`, déjà utilisé par la chaîne de correction. L’exemple de configuration de préproduction documente le modèle Claude OCR sans y introduire de secret. Les tests couvrent l’encodage multimodal Claude, le basculement après indisponibilité Gemini, la validation JSON stricte et les messages assainis. La suite applicative backend termine avec `48 passed`.

## Repli local retiré de la production Free

L’activation contrôlée du repli EasyOCR sur l’instance Render Free a provoqué un dépassement de délai lors du premier chargement et Render a ensuite signalé l’échec de l’instance. La variable d’activation a été immédiatement remise à `false`, puis un redéploiement de restauration a atteint l’état **Live**. Le point de santé public répond à nouveau `{"status":"ok"}`.

La conclusion est qu’EasyOCR, bien que fonctionnel sur la copie synthétique locale, ne respecte pas le budget de mémoire ou de démarrage de cette instance gratuite. Pour éviter tout risque de réactivation involontaire, le code, le paramètre et le script associés ont été retirés par le revert `48cf65f`. La branche de production conserve donc uniquement la chaîne OCR distante Gemini puis Claude, avec erreurs explicites et validation stricte ; aucun repli local non validé ne reste exposé.

La tentative automatisée de création d’une nouvelle clé Gemini dédiée au serveur a été refusée par AI Studio avec le diagnostic « request is suspicious ». Aucun nouveau secret n’a été créé, révélé, enregistré dans Render ou écrit dans Git. La clé Gemini actuelle reste fonctionnelle pour le même appel local mais refusée depuis Render, ce qui maintient l’hypothèse d’une restriction ou d’une politique fournisseur propre à l’environnement hébergé.
