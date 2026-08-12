# Contribuer à Corrector AI

Merci de vouloir améliorer Corrector AI. Le projet vise à aider les enseignants à analyser et corriger des copies avec une **supervision humaine obligatoire**. Les contributions qui améliorent la fiabilité, l’accessibilité, la sécurité, la pédagogie et l’auto-hébergement sont particulièrement bienvenues.

## Avant de commencer

Lisez le [README](README.md), le [guide de déploiement](docs/DEPLOYMENT.md) et la [politique de sécurité](SECURITY.md). Les issues GitHub servent aux défauts reproductibles et aux propositions de fonctionnalités précises. Pour une question générale, utilisez les Discussions GitHub lorsqu’elles sont activées ou ouvrez une issue avec le libellé `question`.

> Ne joignez jamais de copie d’élève identifiable, de clé API, de jeton, de mot de passe ou de capture de données personnelles à une issue ou une pull request.

## Préparer l’environnement

| Objectif | Commande |
|---|---|
| Installer le backend | `pip install -r backend/requirements.txt` |
| Installer les outils de développement et Locust | `pip install -r requirements-dev.txt` |
| Lancer les tests | `python -m pytest backend/tests/ -q` |
| Mesurer la couverture | `python -m pytest backend/tests/ --cov=backend --cov-report=term` |
| Vérifier la syntaxe | `python -m compileall -q backend performance` |

Copiez ensuite `.env.example` vers `.env`. Les services IA renvoient volontairement une erreur explicite lorsqu’aucune clé n’est configurée ; ne contournez pas ce comportement avec une note ou une transcription simulée.

## Déroulement d’une contribution

Créez une branche ciblée, avec un nom tel que `fix/validation-bareme` ou `feat/cache-sujets`. Gardez une pull request limitée à un objectif cohérent. Ajoutez ou adaptez les tests lorsque vous modifiez un contrat API, une sortie LLM, une règle de barème ou un comportement de sécurité.

Chaque pull request doit expliquer le problème, la solution, le comportement vérifié et les limites connues. Les modifications de prompts, de validation Pydantic ou de calcul de notes doivent comporter un exemple de cas de test anonymisé. Les changements de déploiement doivent indiquer une procédure de retour arrière.

## Principes de qualité

Les sorties OCR et LLM sont non déterministes et doivent rester encadrées par des contrats stricts, des erreurs explicites et une validation humaine. N’ajoutez pas de mécanisme qui attribue silencieusement une note fictive. N’enregistrez pas de contenu de copie dans les métriques, traces ou clés de cache.

Conservez les dépendances au minimum, documentez les variables d’environnement ajoutées et privilégiez les fonctions asynchrones non bloquantes sur les chemins HTTP. Toute intégration externe doit échouer de manière contrôlée et ne jamais rendre l’application indisponible par effet de bord.

## Style et revue

Utilisez des noms explicites, des docstrings pour les services critiques et des messages d’erreur destinés à une personne qui exploite l’application. Les commentaires doivent expliquer les contraintes métier ou de sécurité plutôt que paraphraser le code. Une contribution est prête à relire lorsque les tests passent localement et qu’aucun secret ou artefact généré n’est inclus dans le diff.

## Licence

En contribuant, vous acceptez que votre contribution soit distribuée sous la licence [MIT](LICENSE) du dépôt.
