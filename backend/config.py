"""
Configuration centrale de l'application Corrector AI.
Charge les variables d'environnement depuis .env et expose les constantes.
Détecte automatiquement si on tourne en local ou sur Render.
"""

import os
from dotenv import load_dotenv

# Charger le .env depuis la racine du projet (local uniquement)
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

def _read_secret(env_name: str) -> str:
    """Lire une variable ou, pour Docker, le contenu d'un fichier de secret associé."""
    value = os.getenv(env_name, "")
    secret_file = os.getenv(f"{env_name}_FILE", "")
    if value or not secret_file:
        return value
    try:
        with open(secret_file, "r", encoding="utf-8") as file:
            return file.read().strip()
    except OSError:
        return ""


# ━━━ Clés API ━━━
GEMINI_API_KEY = _read_secret("GEMINI_API_KEY")
# Modèle multimodal stable, remplaçable sans redéploiement en cas d’évolution fournisseur.
GEMINI_OCR_MODEL = os.getenv("GEMINI_OCR_MODEL", "gemini-2.5-flash").strip()
ANTHROPIC_API_KEY = _read_secret("ANTHROPIC_API_KEY")
DEEPSEEK_API_KEY = _read_secret("DEEPSEEK_API_KEY")

# ━━━ JWT ━━━
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.getenv("SECRET_KEY", "dev-secret-change-me"))
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

# ━━━ Observabilité ━━━
# L'endpoint Prometheus /metrics est désactivé tant que ce jeton n'est pas configuré.
METRICS_TOKEN = _read_secret("METRICS_TOKEN")

# ━━━ Résilience des appels LLM ━━━
# L'essai initial est inclus dans LLM_RETRY_MAX_ATTEMPTS.
LLM_RETRY_MAX_ATTEMPTS = max(1, int(os.getenv("LLM_RETRY_MAX_ATTEMPTS", "3")))
LLM_RETRY_BASE_SECONDS = max(0.0, float(os.getenv("LLM_RETRY_BASE_SECONDS", "0.5")))
LLM_RETRY_MAX_SECONDS = max(
    LLM_RETRY_BASE_SECONDS, float(os.getenv("LLM_RETRY_MAX_SECONDS", "4"))
)

# ━━━ Persistance PostgreSQL et stockage Supabase ━━━
# DATABASE_URL active PostgreSQL (Supabase ou autre service compatible). Sans cette
# variable, SQLite reste disponible uniquement pour le développement et les tests.
DATABASE_URL = _read_secret("DATABASE_URL")
SUPABASE_URL = _read_secret("SUPABASE_URL").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = _read_secret("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "corrector-private")
REQUIRE_PERSISTENT_STORAGE = os.getenv("REQUIRE_PERSISTENT_STORAGE", "false").lower() == "true"

# ━━━ Cache Redis ━━━
# Laisser REDIS_URL vide pour désactiver le cache sans bloquer le pipeline pédagogique.
REDIS_URL = _read_secret("REDIS_URL")
REDIS_PASSWORD = _read_secret("REDIS_PASSWORD")
if not REDIS_URL and REDIS_PASSWORD:
    REDIS_URL = f"redis://:{REDIS_PASSWORD}@redis:6379/0"
SUBJECT_CACHE_TTL_SECONDS = max(
    60, int(os.getenv("SUBJECT_CACHE_TTL_SECONDS", "86400"))
)

# ━━━ Serveur ━━━
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# ━━━ SMTP ━━━
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")

# ━━━ Chemins — compatibles Render (disque /data) et local ━━━
if os.path.exists("/data"):
    # Render : disque persistant monté sur /data
    DATA_DIR = "/data"
    UPLOADS_DIR = "/data/uploads"
    REPORTS_DIR = "/data/reports"
    DATABASE_PATH = "/data/corrector.db"
else:
    # Local : dossier data/ du projet
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
