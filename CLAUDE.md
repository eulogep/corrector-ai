# CLAUDE.md — Instructions persistantes pour Corrector AI

## Architecture du projet

```
corrector-ai/
├── backend/
│   ├── app.py              # FastAPI — 19 endpoints, CORS, static files
│   ├── auth.py             # JWT + bcrypt (pas passlib — Python 3.14)
│   ├── config.py           # Détection auto Render (/data) vs local
│   ├── models/database.py  # SQLite — 4 tables (professors, students, exams, exercises)
│   ├── routes/
│   │   ├── ocr.py          # Upload → Gemini Vision OCR
│   │   ├── grading.py      # Correction Claude/DeepSeek/Mock
│   │   ├── students.py     # CRUD élèves + progression
│   │   ├── subjects.py     # Import de barèmes PDF
│   │   └── reports.py      # PDF ReportLab + email SMTP + CSV
│   ├── services/
│   │   ├── vision.py       # Gemini 1.5 Pro Vision + fallback mock
│   │   ├── llm.py          # Claude → DeepSeek → Mock (chaîne de fallback)
│   │   ├── cache.py        # Cache en mémoire avec TTL
│   │   └── utils.py        # Helpers (validation des uploads)
│   └── tests/              # 22 tests pytest (mocks IA, uploads)
├── frontend/
│   ├── index.html          # SPA 6 pages (login, dashboard, corriger, élèves, historique, rapports)
│   ├── style.css           # Design dark premium (Syne + DM Sans)
│   └── app.js              # Vanilla JS — connexion API, graphiques Canvas
├── tests/
│   └── test_api_live.py    # 15 tests contre l'API déployée (Render)
├── render.yaml             # Config Render — disque persistant /data
├── .env.example            # Template variables d'environnement
└── README.md               # Badges, architecture, API docs, roadmap
```

## Déploiement

- **Production** : https://corrector-ai.onrender.com
- **GitHub** : https://github.com/eulogep/corrector-ai
- **Hébergement** : Render (Free tier + disque 1 GB pour SQLite)
- **Start command** : `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`

## Chaîne LLM (fallback)

1. **Claude** (Anthropic) — prioritaire
2. **DeepSeek** — fallback si Claude échoue (API OpenAI-compatible)
3. **Mock** — réponses simulées si aucune clé API

Chaque réponse inclut `"llm_used": "claude"|"deepseek"|"mock"`.

## Règles absolues

1. Jamais de clés API en dur — toujours `os.getenv()`
2. Jamais de React/Vue — HTML/CSS/JS vanille uniquement
3. SQLite uniquement — pas de PostgreSQL, pas de SQLAlchemy
4. Commentaires en français, docstrings en anglais
5. Chaque fichier Python a un docstring en tête
6. RGPD : aucune donnée élève sensible envoyée à l'extérieur
7. Pas de passlib — utiliser `bcrypt` directement (compat Python 3.14)
8. Config Render : chemins dynamiques via détection `/data`
9. **Sécurité native** :
   - CORS whitelist (Render, localhost)
   - Rate limiting via `slowapi`
   - Validation uploads via magic bytes et size limit
   - CSRF token exigé pour tout appel POST/PUT/DELETE
10. **Performance** : Utilisation du cache en mémoire avec TTL pour limiter les recalculs (ex: dashboard)

## Variables d'environnement

| Variable | Usage |
|---|---|
| `GEMINI_API_KEY` | OCR Gemini Vision |
| `ANTHROPIC_API_KEY` | Correction Claude |
| `DEEPSEEK_API_KEY` | Fallback DeepSeek |
| `JWT_SECRET_KEY` / `SECRET_KEY` | Tokens JWT |
| `ALLOWED_ORIGINS` | Whitelist CORS |
| `SMTP_HOST/USER/PASSWORD` | Envoi email |

## Tests

- `python -m pytest backend/tests/ -v` → 22/22 (mocks, uploads, validation)
- `python tests/test_api_live.py` → 15/15 (API Render, live)

## Patterns retenus des repos sources

### AI-Handwrite-Grader (wongcyrus)
- Pipeline en étapes : scan → annotation → scoring → rapport → email
- Gemini Vision pour OCR manuscrit
- Email SMTP avec rapport PDF en pièce jointe

### GradeAI (gradeai)
- Routes modulaires séparées par domaine
- Prompt engineering : rôle système + format JSON imposé
- Réponse structurée par critère avec feedback
