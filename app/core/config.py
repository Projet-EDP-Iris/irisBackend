from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os

class Settings(BaseSettings):
    #API Settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Iris"

    #Database Settings
    DATABASE_URL: str = Field(default="sqlite:///./test.db", env="DATABASE_URL")
    SECRET_KEY: str = Field(default="test-secret", env="SECRET_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    #NLP Settings
    NLP_MODEL_PATH: str = "fr_core_news_sm" #default name

    class Config:
        # Only load .env file if not in production
        env_file = ".env" if os.getenv("ENVIRONMENT") != "production" else None
        case_sensitive = True

settings = Settings()

