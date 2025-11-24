from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import uvicorn
from app.core.config import settings
from app.api.routes import users
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
app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], #might have to adjust for prod
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
