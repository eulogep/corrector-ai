# PROMPT CLAUDE CODE — Intégration Docling dans Corrector AI

## Comment utiliser
1. Ouvre ton terminal dans le dossier `corrector-ai`
2. Lance : `claude`
3. Colle le prompt ci-dessous en entier

---

## LE PROMPT

```
Tu es un ingénieur senior. Ta mission : intégrer Docling (IBM)
dans Corrector AI pour permettre la génération automatique
du barème depuis un sujet PDF uploadé par le prof.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXTE DU PROJET
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Corrector AI est une app FastAPI déjà déployée sur
https://corrector-ai.onrender.com

Stack existante :
- Backend : Python 3.11 + FastAPI (backend/app.py)
- LLM : Claude claude-opus-4-5 (services/llm.py)
- OCR copies : Gemini Vision (services/vision.py)
- BDD : SQLite (models/database.py)

Problème actuel : le prof doit taper manuellement
chaque exercice et sa réponse dans un formulaire.

Objectif : uploader le sujet PDF → Docling extrait
le texte → Claude génère le barème automatiquement
→ le prof valide en 1 clic → correction lancée.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CE QUE TU DOIS CRÉER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FICHIER 1 — backend/services/subject_parser.py
  Service principal qui :
  1. Reçoit un fichier PDF (sujet d'examen)
  2. Utilise Docling pour extraire le texte + structure
  3. Envoie le texte extrait à Claude avec ce prompt :
     "Voici le sujet d'un examen. Extrait tous les exercices
      et génère un barème JSON. Pour chaque exercice détecte :
      le numéro, l'énoncé, la réponse attendue (si visible),
      le nombre de points (si indiqué, sinon propose une
      répartition équilibrée sur 20 points au total).
      Retourne UNIQUEMENT un JSON valide."
  4. Retourne le JSON du barème structuré

  Structure JSON attendue en sortie :
  {
    "matiere_detectee": "Mathématiques",
    "niveau_detecte": "lycée",
    "total_points": 20,
    "exercices": [
      {
        "numero": 1,
        "enonce": "Résoudre l'équation 2x + 3 = 7",
        "reponse_attendue": "x = 2",
        "points_max": 4,
        "sous_questions": [],
        "type": "calcul"
      }
    ],
    "confiance": 0.92,
    "remarques": "Barème proposé car non indiqué dans le sujet"
  }

  Gère ces cas :
  - PDF avec texte natif → Docling extrait directement
  - PDF scanné (image) → Docling + OCR fallback Gemini
  - DOCX ou image → Docling supporte aussi ces formats
  - Si Docling échoue → fallback PyMuPDF simple

FICHIER 2 — backend/routes/subjects.py
  Nouveaux endpoints :

  POST /api/subjects/parse
    - Reçoit : fichier PDF/DOCX/image (multipart)
    - Traitement : Docling → Claude
    - Retourne : JSON barème structuré
    - Headers : Content-Type: multipart/form-data

  POST /api/subjects/validate
    - Reçoit : barème JSON (après validation du prof)
    - Sauvegarde dans SQLite table "subjects"
    - Retourne : subject_id

  GET /api/subjects/{subject_id}
    - Retourne le barème sauvegardé

  GET /api/subjects/
    - Liste tous les sujets du prof connecté

FICHIER 3 — Mise à jour backend/models/database.py
  Ajoute la table "subjects" :
  CREATE TABLE IF NOT EXISTS subjects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    professor_id  INTEGER NOT NULL,
    matiere       TEXT,
    niveau        TEXT,
    titre         TEXT,
    total_points  REAL DEFAULT 20,
    exercices_json TEXT NOT NULL,
    pdf_path      TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (professor_id) REFERENCES professors(id)
  )

  Ajoute les helpers :
  - save_subject(professor_id, data) → subject_id
  - get_subject(subject_id) → dict
  - list_subjects(professor_id) → list

FICHIER 4 — Mise à jour backend/routes/grading.py
  Modifie le endpoint POST /api/grading/grade pour
  accepter un subject_id optionnel :
  - Si subject_id fourni → charge le barème depuis SQLite
  - Si non → utilise correction_officielle manuelle (existant)
  Rétrocompatible : ne casse pas l'existant.

FICHIER 5 — Mise à jour backend/requirements.txt
  Ajoute :
  docling==2.15.0
  pymupdf==1.24.10   # fallback rapide
  surya-ocr==0.6.0   # fallback OCR local

FICHIER 6 — Mise à jour frontend/index.html
  Dans la page "Corriger une copie" (pipeline 5 étapes),
  ajoute AVANT l'étape 1 une nouvelle étape 0 :

  ÉTAPE 0 — "📋 Importer le sujet (optionnel)"
    - Zone upload drag & drop pour le PDF du sujet
    - Bouton "Analyser le sujet avec l'IA"
    - Spinner pendant l'analyse Docling + Claude
    - Affichage du barème généré sous forme de tableau :
      | Ex | Énoncé | Réponse attendue | Points |
      |----|--------|-----------------|--------|
      | 1  | ...    | ...             | 4 pts  |
    - Chaque ligne est ÉDITABLE par le prof
    - Bouton "Valider ce barème" → passe à l'étape suivante
      avec le barème pré-rempli
    - Lien "Saisir manuellement" pour garder l'ancienne méthode

  Indicateur de confiance (confiance * 100)% :
    - > 85% → badge vert "Barème détecté automatiquement"
    - 60-85% → badge orange "Vérifiez les points"
    - < 60% → badge rouge "Correction manuelle recommandée"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LOGIQUE TECHNIQUE DÉTAILLÉE — subject_parser.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_subject(file_path: str) -> dict:

  ÉTAPE 1 — Extraction texte avec Docling
    try:
      from docling.document_converter import DocumentConverter
      converter = DocumentConverter()
      result = converter.convert(file_path)
      texte = result.document.export_to_markdown()
      source = "docling"
    except Exception:
      # Fallback PyMuPDF
      import fitz
      doc = fitz.open(file_path)
      texte = " ".join([p.get_text() for p in doc])
      source = "pymupdf"

  ÉTAPE 2 — Si texte vide (PDF scanné) → Gemini Vision
    if len(texte.strip()) < 100:
      texte = extract_text_simple(file_path)  # services/vision.py
      source = "gemini_vision"

  ÉTAPE 3 — Claude génère le barème
    prompt = f"""
    Voici le sujet d'examen extrait par OCR (source: {source}) :

    ---
    {texte[:4000]}  # limite tokens
    ---

    Ta mission :
    1. Identifier la matière et le niveau scolaire
    2. Extraire TOUS les exercices et questions
    3. Pour chaque exercice : numéro, énoncé complet,
       réponse attendue si visible, points (ou proposer
       une répartition équitable sur 20 points)
    4. Calculer un score de confiance (0.0 à 1.0)
       selon la clarté du sujet
    5. Retourner UNIQUEMENT le JSON (pas de markdown)

    Format JSON exact attendu :
    {{
      "matiere_detectee": "...",
      "niveau_detecte": "...",
      "total_points": 20,
      "exercices": [
        {{
          "numero": 1,
          "enonce": "...",
          "reponse_attendue": "...",
          "points_max": 5,
          "type": "calcul|redaction|qcm|schema|autre"
        }}
      ],
      "confiance": 0.9,
      "remarques": "..."
    }}
    """

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
      model="claude-opus-4-5",
      max_tokens=2000,
      messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(message.content[0].text)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TESTS À CRÉER — backend/tests/test_subjects.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

test_parse_subject_mock()
  → Crée un PDF simple avec reportlab (3 exercices)
  → Mock Claude → vérifie structure JSON retournée
  → Vérifie que exercices est une liste non vide
  → Vérifie que total_points == 20

test_parse_endpoint()
  → POST /api/subjects/parse avec PDF de test
  → Vérifie status 200 + clés JSON présentes

test_validate_and_retrieve()
  → POST /api/subjects/validate avec barème JSON
  → GET /api/subjects/{id} → vérifie cohérence

test_grade_with_subject_id()
  → Crée un subject, récupère subject_id
  → POST /api/grading/grade avec subject_id
  → Vérifie que le barème est bien utilisé

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RÈGLES ABSOLUES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Ne casse RIEN de l'existant — les 15 tests API
   doivent continuer à passer après tes modifications
2. Docling peut être lent au premier appel
   (télécharge ses modèles) — ajoute un timeout de 120s
3. Si Docling n'est pas installable (mémoire Render free)
   → le fallback PyMuPDF doit fonctionner seul
4. Toujours retourner un JSON valide même si
   l'extraction échoue partiellement
5. Limite le texte envoyé à Claude à 4000 caractères
   pour rester dans les limites de tokens
6. Enregistre le subject_id dans la table exams
   quand un grade est lancé depuis un sujet

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PLAN D'EXÉCUTION — dans cet ordre exact
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE 1 — Installation et service
  1. pip install docling pymupdf dans requirements.txt
  2. Crée backend/services/subject_parser.py
  3. Teste : python -c "from services.subject_parser import parse_subject; print('OK')"
  → PAUSE : dis "Phase 1 OK"

PHASE 2 — Backend
  4. Ajoute table subjects dans database.py
  5. Crée backend/routes/subjects.py
  6. Enregistre le router dans app.py
  7. Modifie grading.py (subject_id optionnel)
  8. Lance python -m backend.app → vérifie /docs
  → PAUSE : dis "Phase 2 OK" + montre les nouveaux
    endpoints dans Swagger

PHASE 3 — Tests
  9. Crée backend/tests/test_subjects.py
  10. Lance pytest backend/tests/ -v
  → Tous les anciens tests + nouveaux doivent passer
  → PAUSE : dis "Phase 3 OK" + résultat pytest

PHASE 4 — Frontend
  11. Ajoute l'étape 0 dans index.html
  12. Connecte au endpoint /api/subjects/parse
  13. Affiche le tableau éditable du barème
  14. Connecte "Valider" → /api/subjects/validate
  → PAUSE : dis "Phase 4 OK"

PHASE 5 — Push GitHub
  15. git add -A
  16. git commit -m "feat: génération automatique du barème depuis sujet PDF (Docling + Claude)"
  17. git push
  → Render redéploie automatiquement
  → PAUSE : dis "Phase 5 OK — déployé sur Render"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITÈRES D'ACCEPTATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ curl -X POST .../api/subjects/parse -F "file=@sujet.pdf"
   → retourne JSON avec exercices et barème

✅ Le prof peut uploader un sujet PDF dans le dashboard
   et voir le barème généré en moins de 30 secondes

✅ Le barème généré est éditable avant validation

✅ POST /api/grading/grade avec subject_id charge
   le barème automatiquement

✅ pytest backend/tests/ → 0 failing (anciens + nouveaux)

✅ git push → Render redéploie sans erreur

Commence maintenant par la Phase 1.
```
