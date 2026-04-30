# 🎓 Corrector AI

**Correction intelligente de copies manuscrites par IA** — OCR (Gemini Vision) + LLM (Claude) pour les professeurs du système éducatif français.

## ✨ Fonctionnalités

- 📷 **OCR** : Scan de copies manuscrites via Gemini Vision
- 🤖 **Correction IA** : Notation automatique avec Claude (barème /20)
- 👥 **Profils élèves** : CRUD complet avec historique longitudinal
- 📊 **Dashboard** : KPI, graphiques, dernières corrections
- ⚠️ **Détection d'anomalies** : Alerte si note inhabituelle
- 📄 **Rapports PDF** : Génération ReportLab + envoi email SMTP
- 📊 **Export CSV** : Notes par classe
- 🔒 **RGPD** : SQLite local, aucune donnée élève envoyée

## 🚀 Installation

```bash
cd corrector-ai/backend
python -m pip install -r requirements.txt
cp ../.env.example ../.env
# Éditez .env avec vos clés API (optionnel pour le mode mock)
```

## ▶️ Lancement

```bash
cd corrector-ai
python -m backend.app
# → http://localhost:8000 (frontend)
# → http://localhost:8000/docs (Swagger API)
```

## 🧪 Tests

```bash
cd corrector-ai
python -m pytest backend/tests/ -v
# 7 tests, tous passent (mocks LLM/Gemini)
```

## 🔑 Variables d'environnement (.env)

| Variable | Description | Requis |
|----------|-------------|--------|
| `GEMINI_API_KEY` | Clé Google Gemini | Non (mode mock) |
| `ANTHROPIC_API_KEY` | Clé Anthropic Claude | Non (mode mock) |
| `JWT_SECRET_KEY` | Secret pour les tokens JWT | Oui |
| `SMTP_HOST/USER/PASSWORD` | Config email | Non |

## 📡 API Endpoints

### Auth
- `POST /api/auth/register` — Créer un compte professeur
- `POST /api/auth/login` — Connexion (retourne JWT)

### OCR
- `POST /api/ocr/extract` — Upload image → JSON structuré par exercice
- `POST /api/ocr/simple` — Upload image → texte brut

### Correction
- `POST /api/grading/grade` — Correction complète avec sauvegarde
- `POST /api/grading/quick` — Correction rapide sans sauvegarde

### Élèves
- `GET/POST /api/students/` — Liste / Créer
- `GET/PUT /api/students/{id}` — Profil / Modifier
- `GET /api/students/{id}/progression` — Courbes par matière
- `GET /api/students/{id}/exams` — Historique copies

### Copies
- `GET /api/exams` — Liste paginée
- `GET /api/grading/exams/{id}` — Détail copie
- `DELETE /api/grading/exams/{id}` — Supprimer

### Rapports
- `GET /api/reports/pdf/{exam_id}` — Télécharger PDF
- `POST /api/reports/email` — Envoyer PDF par email
- `GET /api/reports/csv/classe/{classe}` — Export CSV

### Stats
- `GET /api/stats/dashboard` — Métriques du professeur

## 🏗️ Stack technique

- **Backend** : Python 3.11+ / FastAPI / Uvicorn
- **BDD** : SQLite (sqlite3 natif)
- **OCR** : Google Gemini 1.5 Pro Vision
- **LLM** : Anthropic Claude
- **PDF** : ReportLab
- **Auth** : JWT (python-jose)
- **Frontend** : HTML/CSS/JS vanille (SPA)
