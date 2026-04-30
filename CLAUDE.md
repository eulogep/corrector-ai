# CLAUDE.md — Instructions persistantes pour Corrector AI

## Patterns retenus des repos sources

### Repo 1 — AI-Handwrite-Grader (wongcyrus)
- **Pipeline en étapes** : scan → annotation par question → scoring → rapport → email
- **Découpe d'image** : chaque question est annotée séparément (question_annotations)
- **Email SMTP** : envoi du rapport PDF en pièce jointe via SMTP (Gmail)
- **Gemini Vision** : utilisation de Vertex AI / Gemini Pro pour lire l'écriture manuscrite
- **Template Excel** : liste élèves + réponses type (on remplace par SQLite + JSON)
- **Serveur Flask** : sert les fichiers statiques + sauvegarde les scores en JSON
- **Pattern retenu** : séparer clairement les phases du pipeline (OCR → Grading → Report)

### Repo 2 — GradeAI (gradeai)
- **Structure blueprint** : routes modulaires séparées par domaine (query, ocr, upload)
- **Endpoint /query_essay** : reçoit rubric + essay → retourne JSON structuré par critère
- **Format de réponse** : [{Criteria, Level, Feedback}, ..., {Grade, Percentage}]
- **CORS** : activé pour connecter frontend et backend séparément
- **Prompt engineering** : rôle système détaillé + instructions de notation + format JSON imposé
- **Pattern retenu** : structure modulaire des routes + format JSON structuré de réponse

## Ce qui est amélioré par rapport aux deux repos
- Flask → **FastAPI** (async, validation Pydantic, Swagger auto)
- Notebooks → **API REST complète**
- Pas de BDD → **SQLite avec CRUD complet**
- GPT-3.5 → **Claude claude-opus-4-5** (Anthropic)
- Cantonais → **Français** (système /20, barèmes officiels)
- Pas de profils → **Profils élèves persistants + historique longitudinal**
- Pas d'UI → **Dashboard SPA complet en HTML/CSS/JS vanille**

## Règles absolues
1. Jamais de clés API en dur — toujours `os.getenv()`
2. Jamais de React/Vue — HTML/CSS/JS vanille uniquement
3. SQLite uniquement — pas de PostgreSQL, pas de SQLAlchemy
4. Commentaires en français, docstrings en anglais
5. Chaque fichier Python a un docstring en tête
6. RGPD : aucune donnée élève sensible envoyée à l'extérieur
