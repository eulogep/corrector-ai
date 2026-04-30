"""
Configuration centrale de l'application Corrector AI.
Charge les variables d'environnement depuis .env et expose les constantes.
"""

import os
from dotenv import load_dotenv

# Charger le .env depuis la racine du projet
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# ━━━ Clés API ━━━
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ━━━ JWT ━━━
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

# ━━━ Serveur ━━━
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "true").lower() == "true"

# ━━━ SMTP ━━━
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")

# ━━━ Chemins ━━━
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(DATA_DIR, "corrector.db"))

# Créer les dossiers si nécessaire
for d in [DATA_DIR, UPLOADS_DIR, REPORTS_DIR]:
    os.makedirs(d, exist_ok=True)

# ━━━ Formats acceptés pour les images ━━━
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
