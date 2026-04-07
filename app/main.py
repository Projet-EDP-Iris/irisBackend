import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Imports des routers
from app.api.endpoints.emails import router as email_router
from app.api.endpoints.prediction import router as prediction_router
from app.api.endpoints.suggestion import router as suggestion_router
from app.api.routes import router as user_router
from app.core.config import settings
from app.db.database import init_db, engine
from app.models import Base

# 1. Création des tables (synchrone au chargement du module)
Base.metadata.create_all(bind=engine)

# 2. Configuration de l'application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Backend API for Iris: user authentication (JWT), email detection (NLP extraction from raw emails), "
        "Gmail integration, and slot prediction. "
        "Most endpoints require Authorization: Bearer <token>."
    ),
    version="0.1.0",
    openapi_tags=[
        {"name": "users", "description": "User registration, login, and profile."},
        {"name": "detection", "description": "Extract intent, times, participants from emails."},
        {"name": "emails", "description": "Gmail fetch and pipeline management."},
        {"name": "prediction", "description": "Suggested meeting slots output."},
        {"name": "suggestion", "description": "AI-generated email response suggestions."},
    ],
)

# 3. Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # On garde "*" pour tes tests, tu pourras restreindre plus tard
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Événement de démarrage
@app.on_event("startup")
def startup_event():
    init_db()

# 5. Inclusion des Routes (Une seule fois par router !)
# Routes avec préfixes v1
app.include_router(user_router, prefix="/api/v1/user", tags=["users"])
app.include_router(email_router, prefix="/emails", tags=["emails"])
app.include_router(prediction_router, prefix="/predictions", tags=["predictions"])
app.include_router(suggestion_router, prefix="/suggestions", tags=["suggestions"])

# 6. Fichiers statiques
# Assure-toi que le dossier 'app/static' existe bien
if os.path.exists("app/static"):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 7. Endpoints de base
@app.get("/", tags=["system"])
async def root():
    return {"message": "Bienvenue sur l'API Iris - Le pipeline est opérationnel !"}

@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)