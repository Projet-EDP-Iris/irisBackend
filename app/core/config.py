from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    #API Settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Iris"

    #Database Settings (Placeholder)
    DATABASE_URL: str
    SECRET_KEY: str

    #NLP Settings
    NLP_MODEL_PATH: str = "fr_core_news_sm" #default name

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

