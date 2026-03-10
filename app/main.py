import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import emails, prediction
from app.api.routes import detection, users
from app.core.config import settings
from app.db.database import init_db


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Backend API for Iris: user authentication (JWT), email detection (NLP extraction from raw emails), "
        "Gmail integration (fetch, fetch-and-detect, fetch-detect-predict), and slot prediction from detection output. "
        "Most endpoints require Authorization: Bearer <token>; obtain a token via POST /users/login. "
        "Use the interactive docs below to try the API."
    ),
    version="0.1.0",
    openapi_tags=[
        {"name": "users", "description": "User registration, login, and profile (JWT)."},
        {"name": "detection", "description": "Extract intent, times, participants from emails (NLP)."},
        {"name": "emails", "description": "Gmail fetch and pipeline (fetch, fetch-and-detect, fetch-detect-predict)."},
        {"name": "prediction", "description": "Suggested meeting slots from detection output."},
    ],
)


app.include_router(prediction.router, prefix="/api/v1")
app.include_router(emails.router, prefix="/api/v1")


@app.on_event("startup")
def startup_event():
    """
    Initialize database tables on application startup.
    Tables are created automatically from SQLAlchemy models if they don't exist.
    """
    init_db()

app.include_router(users.router)
app.include_router(detection.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",
    "https://one-page-site-nine.vercel.app",
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


@app.get("/")
async def root():
    """API welcome and status."""
    return{"message":"👋 Welcome to the Iris API", "status": "online"}


@app.get("/health")
async def health_check():
    """Health check for load balancers or monitoring."""
    return{"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
