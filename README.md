# 🎓 Corrector AI

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Opus_4.5-D4A853?style=for-the-badge&logo=anthropic&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-Vision-4285F4?style=for-the-badge&logo=google&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-7%2F7_✅-22C55E?style=for-the-badge)
![RGPD](https://img.shields.io/badge/RGPD-Conforme-6366F1?style=for-the-badge)
![License](https://img.shields.io/badge/Licence-MIT-F59E0B?style=for-the-badge)

**Correction intelligente de copies manuscrites par IA — OCR (Gemini Vision) + LLM (Claude)**  
**pour les professeurs du système éducatif français.**

[🚀 Démo](#-installation) · [📖 API Docs](#-api-endpoints) · [🐛 Signaler un bug](https://github.com/eulogep/corrector-ai/issues) · [💡 Proposer une feature](https://github.com/eulogep/corrector-ai/issues)

</div>

---

## 🎯 Le problème

Un professeur français passe **8 à 12 heures par semaine** à corriger des copies manuellement — un travail répétitif, épuisant, source d'incohérences et sans valeur ajoutée pédagogique.

## 💡 La solution

Corrector AI automatise tout le pipeline de correction :

```
📸 Photo de la copie  →  🔍 OCR Gemini  →  🤖 Correction Claude  →  📊 Rapport PDF  →  📧 Email élève
```

---

## ✨ Fonctionnalités

| Fonctionnalité | Description |
|---|---|
| 📸 **OCR manuscrit** | Scan de copies via Gemini Vision — cursive, script, écriture rapide |
| 🤖 **Correction IA** | Notation automatique avec Claude (barème /20, feedback pédagogique) |
| 👤 **Profils élèves** | CRUD complet avec historique longitudinal de toutes les copies |
| 📈 **Dashboard** | KPIs, graphiques, progression par matière et par classe |
| 🚨 **Détection d'anomalies** | Alerte si une note est statistiquement inhabituelle pour l'élève |
| 📄 **Rapport PDF** | Génération ReportLab avec détail exercice par exercice |
| 📧 **Envoi email** | Rapport envoyé à l'élève automatiquement via SMTP |
| 📊 **Export CSV** | Notes par classe exportables en un clic |
| 🔒 **RGPD natif** | SQLite local — aucune donnée élève envoyée à l'étranger |

---

## 🆚 Pourquoi pas Examino, GradingPal ou GradeAI ?

| Critère | Examino 🇫🇷 | GradingPal 🇺🇸 | GradeAI | **Corrector AI** |
|---|:---:|:---:|:---:|:---:|
| Profil élève individuel | ❌ | ❌ | ❌ | ✅ |
| Historique longitudinal | ❌ | ❌ | ❌ | ✅ |
| Détection d'anomalies | ❌ | ❌ | ❌ | ✅ |
| Notes /20 système français | ✅ | ❌ | ❌ | ✅ |
| RGPD — données locales | ⚠️ | ❌ | ❌ | ✅ |
| Open Source | ❌ | ❌ | ✅ | ✅ |
| Auto-hébergeable | ❌ | ❌ | ✅ | ✅ |

---

## 🏗️ Architecture

```
corrector-ai/
├── backend/
│   ├── app.py              # FastAPI — 19 endpoints
│   ├── auth.py             # JWT (register / login)
│   ├── config.py           # Variables d'environnement
│   ├── models/
│   │   └── database.py     # SQLite — 4 tables
│   ├── routes/
│   │   ├── ocr.py          # Upload image → OCR Gemini
│   │   ├── grading.py      # Correction Claude
│   │   ├── students.py     # CRUD élèves + progression
│   │   └── reports.py      # PDF + email + CSV
│   ├── services/
│   │   ├── vision.py       # Gemini 1.5 Pro Vision
│   │   └── llm.py          # Claude Opus 4.5
│   └── tests/              # 7/7 tests ✅
└── frontend/
    └── index.html          # SPA vanille JS — 6 pages
```

---

## ⚡ Installation

```bash
# 1. Clone
git clone https://github.com/eulogep/corrector-ai.git
cd corrector-ai/backend

# 2. Dépendances
pip install -r requirements.txt

# 3. Configuration
cp ../.env.example ../.env
# → Éditez .env avec vos clés API (voir ci-dessous)

# 4. Lancement
cd ..
python -m backend.app
# → http://localhost:8000        (frontend)
# → http://localhost:8000/docs   (Swagger API)
```

---

## 🔑 Variables d'environnement (.env)

| Variable | Description | Requis |
|---|---|:---:|
| `GEMINI_API_KEY` | Clé Google Gemini | Non (mode mock) |
| `ANTHROPIC_API_KEY` | Clé Anthropic Claude | Non (mode mock) |
| `JWT_SECRET_KEY` | Secret pour les tokens JWT | **Oui** |
| `SMTP_HOST/USER/PASSWORD` | Config email | Non |

> 💡 **Mode mock** : sans clés API, l'app tourne avec des réponses simulées — parfait pour tester l'UI.

---

## 🧪 Tests

```bash
cd corrector-ai
python -m pytest backend/tests/ -v
# 7 tests, 0 failing ✅
```

---

## 🔌 API Endpoints

### Auth
| Méthode | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register` | Créer un compte professeur |
| POST | `/api/auth/login` | Connexion (retourne JWT) |

### OCR
| Méthode | Endpoint | Description |
|---|---|---|
| POST | `/api/ocr/extract` | Upload image → JSON structuré par exercice |
| POST | `/api/ocr/simple` | Upload image → texte brut |

### Correction
| Méthode | Endpoint | Description |
|---|---|---|
| POST | `/api/grading/grade` | Correction complète avec sauvegarde |
| POST | `/api/grading/quick` | Correction rapide sans sauvegarde |

### Élèves
| Méthode | Endpoint | Description |
|---|---|---|
| GET/POST | `/api/students/` | Liste / Créer |
| GET/PUT | `/api/students/{id}` | Profil / Modifier |
| GET | `/api/students/{id}/progression` | Courbes par matière |
| GET | `/api/students/{id}/exams` | Historique des copies |

### Copies
| Méthode | Endpoint | Description |
|---|---|---|
| GET | `/api/exams/{id}` | Détail d'une copie corrigée |
| DELETE | `/api/exams/{id}` | Supprimer une copie |

### Rapports
| Méthode | Endpoint | Description |
|---|---|---|
| GET | `/api/reports/pdf/{id}` | Télécharger le rapport PDF |
| POST | `/api/reports/email` | Envoyer par email |
| GET | `/api/reports/csv/{classe}` | Export CSV des notes |

### Stats
| Méthode | Endpoint | Description |
|---|---|---|
| GET | `/api/stats/dashboard` | Métriques du professeur connecté |

---

## 🛠️ Stack technique

| Couche | Technologie |
|---|---|
| **Backend** | Python 3.11 + FastAPI + Uvicorn |
| **Base de données** | SQLite (natif — RGPD) |
| **OCR** | Google Gemini 1.5 Pro Vision |
| **LLM** | Anthropic Claude Opus 4.5 |
| **PDF** | ReportLab |
| **Auth** | JWT (python-jose) |
| **Frontend** | HTML / CSS / JS vanille (SPA) |

---

## 🗺️ Roadmap

- [ ] Déploiement Railway / Render (URL publique)
- [ ] Application mobile (React Native)
- [ ] Import CSV liste élèves
- [ ] Graphiques de progression (Chart.js avancé)
- [ ] Support multi-classes
- [ ] Mode hors-ligne (modèle OCR local)
- [ ] Intégration ENT (Pronote, EcoleDirecte)

---

## 🙏 Inspiré de

- [AI-Handwrite-Grader](https://github.com/wongcyrus/AI-Handwrite-Grader) — pipeline scan → rapport → email
- [GradeAI](https://github.com/GradeAI/gradeai) — structure API modulaire et correction par barème

---

## 📜 Licence

MIT — Fait avec ❤️ pour les enseignants français

---

<div align="center">
  <strong>⭐ Si ce projet vous est utile, n'oubliez pas de le star !</strong>
</div>
