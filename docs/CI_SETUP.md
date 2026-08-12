# Activer l’intégration continue GitHub Actions

Le workflow de tests est fourni sous `docs/github-actions-ci.yml.example`. Il exécute les tests backend à chaque push et pull request vers `main`.

Le jeton GitHub utilisé pour les publications automatisées de ce dépôt ne possède pas la permission `workflows`, ce qui empêche de créer ou modifier directement un fichier sous `.github/workflows/`. Cette restriction protège les dépôts contre l’ajout non autorisé de code exécuté par GitHub Actions.

Pour activer la CI, utilisez un compte ou un jeton autorisé à gérer les workflows, puis exécutez :

```bash
mkdir -p .github/workflows
cp docs/github-actions-ci.yml.example .github/workflows/ci.yml
git add .github/workflows/ci.yml
git commit -m "ci: add backend test workflow"
git push origin main
```

Après la publication, vérifiez l’exécution dans l’onglet **Actions** du dépôt. Le badge du README devient vert après le premier passage réussi. Toute pull request future recevra alors un contrôle automatisé des tests backend.
