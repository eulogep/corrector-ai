"""
Application principale Corrector AI.
FastAPI app avec tous les middlewares et routers enregistrés.
Sert aussi le frontend statique.
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Patch Starlette Config AVANT d'importer slowapi
# (slowapi utilise Config() qui lit .env avec encodage par défaut — crash sur Windows)
import starlette.config
_OrigConfig = starlette.config.Config
class _SafeConfig(_OrigConfig):
    def __init__(self, env_file=starlette.config.undefined, **kwargs):
        super().__init__(env_file=None, **kwargs)
starlette.config.Config = _SafeConfig

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

starlette.config.Config = _OrigConfig
from backend.config import (
    HOST, PORT, DEBUG, ALLOWED_ORIGINS,
    RATE_LIMIT_AUTH, RATE_LIMIT_AI, RATE_LIMIT_DEFAULT,
)
from backend.auth import hash_password, verify_password, create_token, get_current_professor
from backend.models.database import init_db, create_professor, get_professor_by_email
from backend.routes.students import router as students_router
from backend.routes.ocr import router as ocr_router
from backend.routes.grading import router as grading_router
from backend.routes.reports import router as reports_router
from backend.models.database import get_professor_stats, get_exams_by_professor
from fastapi import Depends

logger = logging.getLogger("corrector_ai.app")

# ━━━ Rate limiter ━━━
limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT_DEFAULT])


# ━━━ Lifespan — init DB au démarrage ━━━
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    init_db()
    logger.info("Base de données initialisée")
    logger.info(f"CORS origines autorisées : {ALLOWED_ORIGINS}")
    yield


# ━━━ Création de l'app ━━━
app = FastAPI(
    title="Corrector AI",
    description="API de correction de copies manuscrites par IA (OCR + LLM)",
    version="1.0.0",
    lifespan=lifespan,
)

# Attacher le limiter à l'app
app.state.limiter = limiter


# Handler personnalisé pour les 429
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Return a French 429 error message."""
    logger.warning(f"Rate limit atteint pour {get_remote_address(request)}")
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Trop de requêtes. Veuillez patienter avant de réessayer.",
            "retry_after": str(exc.detail),
        },
    )


# ━━━ CORS — origines restreintes ━━━
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ━━━ Auth routes (pas de JWT requis) ━━━

class RegisterRequest(BaseModel):
    nom: str
    prenom: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register", tags=["Auth"])
@limiter.limit(RATE_LIMIT_AUTH)
async def register(request: Request, data: RegisterRequest):
    """Register a new professor account."""
    # Vérifier si l'email existe déjà
    existing = get_professor_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")

    password_hash = hash_password(data.password)
    prof_id = create_professor(data.nom, data.prenom, data.email, password_hash)
    token = create_token(prof_id, data.email)
    logger.info(f"Nouveau professeur inscrit : {data.email} (id={prof_id})")

    return {
        "id": prof_id,
        "token": token,
        "message": "Compte créé avec succès",
    }


@app.post("/api/auth/login", tags=["Auth"])
@limiter.limit(RATE_LIMIT_AUTH)
async def login(request: Request, data: LoginRequest):
    """Login and get a JWT token."""
    prof = get_professor_by_email(data.email)
    if not prof or not verify_password(data.password, prof["password_hash"]):
        logger.warning(f"Tentative de connexion échouée : {data.email}")
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    token = create_token(prof["id"], prof["email"])
    logger.info(f"Connexion réussie : {data.email} (id={prof['id']})")
    return {
        "id": prof["id"],
        "token": token,
        "nom": prof["nom"],
        "prenom": prof["prenom"],
        "message": "Connexion réussie",
    }


# ━━━ Stats dashboard ━━━

@app.get("/api/stats/dashboard", tags=["Stats"])
@limiter.limit(RATE_LIMIT_DEFAULT)
async def dashboard_stats(request: Request, prof: dict = Depends(get_current_professor)):
    """Get dashboard metrics for the connected professor."""
    logger.info(f"Dashboard consulté par prof={prof['id']}")
    return get_professor_stats(prof["id"])


# ━━━ Historique copies (filtres) ━━━

@app.get("/api/exams", tags=["Copies"])
@limiter.limit(RATE_LIMIT_DEFAULT)
async def list_exams(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    prof: dict = Depends(get_current_professor),
):
    """List all exams for the connected professor with pagination."""
    exams = get_exams_by_professor(prof["id"], limit=limit, offset=offset)
    return {"exams": exams}


# ━━━ Enregistrement des routers ━━━
app.include_router(students_router)
app.include_router(ocr_router)
app.include_router(grading_router)
app.include_router(reports_router)

# Charger le router subjects seulement s'il existe
try:
    from backend.routes.subjects import router as subjects_router
    app.include_router(subjects_router)
except ImportError:
    pass


# ━━━ Frontend statique ━━━

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend():
    """Serve the main frontend page."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Corrector AI — Frontend non trouvé</h1>")

# Servir les fichiers statiques (CSS, JS)
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")


# ━━━ Point d'entrée ━━━
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host=HOST, port=PORT, reload=DEBUG)
