"""
Application principale Corrector AI.
FastAPI app avec tous les middlewares et routers enregistrés.
Sert aussi le frontend statique.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import HOST, PORT, DEBUG
from backend.auth import hash_password, verify_password, create_token, get_current_professor
from backend.models.database import init_db, create_professor, get_professor_by_email
from backend.routes.students import router as students_router
from backend.routes.ocr import router as ocr_router
from backend.routes.grading import router as grading_router
from backend.routes.reports import router as reports_router
from backend.routes.subjects import router as subjects_router
from backend.models.database import get_professor_stats, get_exams_by_professor
from backend.services.exceptions import AIServiceError
from fastapi import Depends


# ━━━ Lifespan — init DB au démarrage ━━━
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    init_db()
    yield


# ━━━ Création de l'app ━━━
app = FastAPI(
    title="Corrector AI",
    description="API de correction de copies manuscrites par IA (OCR + LLM)",
    version="1.0.0",
    lifespan=lifespan,
)

@app.exception_handler(AIServiceError)
async def ai_service_error_handler(request: Request, exc: AIServiceError):
    """Exposer les échecs IA attendus sans fuite de détails fournisseurs."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.to_detail()})


# ━━━ CORS ━━━
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
async def register(data: RegisterRequest):
    """Register a new professor account."""
    # Vérifier si l'email existe déjà
    existing = get_professor_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")

    password_hash = hash_password(data.password)
    prof_id = create_professor(data.nom, data.prenom, data.email, password_hash)
    token = create_token(prof_id, data.email)

    return {
        "id": prof_id,
        "token": token,
        "message": "Compte créé avec succès",
    }


@app.post("/api/auth/login", tags=["Auth"])
async def login(data: LoginRequest):
    """Login and get a JWT token."""
    prof = get_professor_by_email(data.email)
    if not prof or not verify_password(data.password, prof["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    token = create_token(prof["id"], prof["email"])
    return {
        "id": prof["id"],
        "token": token,
        "nom": prof["nom"],
        "prenom": prof["prenom"],
        "message": "Connexion réussie",
    }


# ━━━ Stats dashboard ━━━

@app.get("/api/stats/dashboard", tags=["Stats"])
async def dashboard_stats(prof: dict = Depends(get_current_professor)):
    """Get dashboard metrics for the connected professor."""
    return get_professor_stats(prof["id"])


# ━━━ Historique copies (filtres) ━━━

@app.get("/api/exams", tags=["Copies"])
async def list_exams(
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
app.include_router(subjects_router)


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
