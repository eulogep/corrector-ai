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
