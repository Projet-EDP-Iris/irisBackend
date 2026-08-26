import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints.calendar import router as calendar_router
from app.api.endpoints.emails import router as email_router
from app.api.endpoints.prediction import router as prediction_router
from app.api.endpoints.processing_state import router as processing_state_router
from app.api.endpoints.suggestion import router as suggestion_router
from app.api.routes.auth import router as auth_router
from app.api.routes.auth_apple import router as apple_auth_router
from app.api.routes.auth_google import router as google_auth_router
from app.api.routes.auth_microsoft import router as microsoft_auth_router
from app.api.routes.detection import router as detection_router
from app.api.routes.users import router as user_router
from app.core.config import settings
from app.db.database import engine, init_db
from app.models import Base

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

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
        {"name": "processing-state", "description": "Persisted Iris on/off state and processing progress."},
        {"name": "auth", "description": "OAuth flows — Microsoft/Outlook account connection."},
    ],
)

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",
    "https://one-page-site-nine.vercel.app",
    "https://one-page-site-ten.vercel.app",
    "null",  # Packaged Electron .exe loads from file://, which sends Origin: null
]

if os.getenv("ENVIRONMENT", "development") != "production":
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


@app.on_event("startup")
def startup_event():
    init_db()
    # Pre-warm the spaCy NLP model so the first /emails/feed request doesn't pay
    # the 10-30s cold-start cost of loading the model under live traffic.
    try:
        from app.services.detection import _get_extractor
        _get_extractor()
    except Exception as exc:
        logger.warning("spaCy model failed to pre-warm: %s", exc)


app.include_router(user_router, prefix="/api/v1", tags=["users"])
app.include_router(detection_router, prefix="/api/v1", tags=["detection"])
app.include_router(email_router, prefix="/api/v1", tags=["emails"])
app.include_router(prediction_router, prefix="/api/v1", tags=["predictions"])
app.include_router(suggestion_router, prefix="/api/v1", tags=["suggestions"])
app.include_router(calendar_router, prefix="/api/v1", tags=["calendar"])
app.include_router(processing_state_router, prefix="/api/v1", tags=["processing-state"])
app.include_router(auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(apple_auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(google_auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(microsoft_auth_router, prefix="/api/v1", tags=["auth"])


@app.get("/", tags=["system"])
async def root():
    return {"message": "Iris API — pipeline is operational"}


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)  # nosec B104
