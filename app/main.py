import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Imports des routers
from app.api.endpoints.calendar import router as calendar_router
from app.api.endpoints.emails import router as email_router
from app.api.endpoints.prediction import router as prediction_router
from app.api.endpoints.suggestion import router as suggestion_router
from app.api.endpoints.email_classifier_router import router as email_router
from app.api.endpoints.emails import router as email_router
from app.api.routes.auth_google import router as google_auth_router
from app.api.routes.auth_microsoft import router as microsoft_auth_router
from app.api.routes.detection import router as detection_router
from app.api.routes.users import router as user_router
from app.core.config import settings
from app.db.database import engine, init_db
from app.models import Base

# 1. Création des tables
Base.metadata.create_all(bind=engine)

# 2. Configuration de l'application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Backend API for Iris — an AI-powered email-to-calendar assistant.\n\n"
        "**Auth:** Register at `POST /api/v1/users/` then log in at `POST /api/v1/users/login` to get a Bearer token. "
        "Pass it as `Authorization: Bearer <token>` on all protected endpoints.\n\n"
        "**Pipeline:** Fetch Gmail → detect meeting intent (NLP) → predict slots → confirm to calendar.\n\n"
        "**Calendar integrations:** Google Calendar (via Gmail OAuth), Apple Calendar (CalDAV App Password), "
        "Outlook/Office 365 (Microsoft OAuth — start at `GET /api/v1/auth/microsoft`).\n\n"
        "**AI suggestions:** Generate 3 reply variants inline via `POST /api/v1/suggest-inline`, "
        "or from a stored email via `POST /api/v1/suggest/{email_id}`.\n\n"
        "**One-click confirm:** `POST /api/v1/calendar/confirm/{email_id}` creates events in all connected calendars at once."
    ),
    version="0.1.0",
    openapi_tags=[
        {"name": "users", "description": "User registration, login, and profile."},
        {"name": "detection", "description": "Extract intent, times, participants from emails."},
        {"name": "emails", "description": "Gmail fetch and pipeline management."},
        {"name": "prediction", "description": "Suggested meeting slots output."},
        {"name": "suggestion", "description": "AI-generated email response suggestions."},
        {"name": "calendar", "description": "One-click calendar event creation (Google, Apple, Outlook)."},
        {"name": "auth", "description": "OAuth flows — Microsoft/Outlook account connection."},
    ],
)

# 3. Middleware CORS
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",
    "https://one-page-site-nine.vercel.app",
    "null",  # Packaged Electron .exe loads from file://, which sends Origin: null
]

if os.getenv("ENVIRONMENT") != "production":
    ALLOWED_ORIGINS.extend([
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Événement de démarrage
@app.on_event("startup")
def startup_event():
    init_db()

# 5. Inclusion des Routes
app.include_router(user_router, prefix="/api/v1", tags=["users"])
app.include_router(detection_router, prefix="/api/v1", tags=["detection"])
app.include_router(email_router, prefix="/api/v1", tags=["emails"])
app.include_router(prediction_router, prefix="/api/v1", tags=["predictions"])
app.include_router(suggestion_router, prefix="/api/v1", tags=["suggestions"])
app.include_router(calendar_router, prefix="/api/v1", tags=["calendar"])
app.include_router(google_auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(microsoft_auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(email_router, prefix="/api/v1", tags=["emails"])

# 6. Fichiers statiques
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
