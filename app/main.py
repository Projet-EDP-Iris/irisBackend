import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import users
from app.core.config import settings
from app.db.database import init_db

#Initialization
app = FastAPI(
        title=settings.PROJECT_NAME,
        description="This is the Iris API",
        version="0.1.0",
)

# Event handler
@app.on_event("startup")
def startup_event():
    """
    Initialize database tables on application startup.
    Tables are created automatically from SQLAlchemy models if they don't exist.
    """
    init_db()

app.include_router(users.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

#CORS config
# CORS (configure allowed origins based on environment)
ALLOWED_ORIGINS = [
    "http://localhost:5173",      # Local website development (Vite default)
    "http://localhost:3000",      # Alternative local development port (React, Next.js)
    "http://localhost:8080",      # Alternative local development port
    "https://one-page-site-nine.vercel.app",  # Deployed website
    # Add your deployed Iris app frontend URL here when ready
    # "https://your-iris-app.vercel.app",
]

# For local development, also allow localhost on any port
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

#Endpoints/Routes
@app.get("/")
async def root():
    return{"message":"👋 Welcome to the Iris API", "status": "online"}

@app.get("/health")
async def health_check():
    return{"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
