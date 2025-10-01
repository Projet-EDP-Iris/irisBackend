from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    #API Settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Iris"

    #Database Settings (Placeholder)
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_SERVER: Optional[str] = None
    POSTGRES_PORT: Optional[str] = None
    POSTGRES_DB: Optional[str] = None

    #NLP Settings
    NLP_MODEL_PATH: str = "fr_core_news_sm" #default name

    class Config:
        env_file = ".env"
        case_sensitive = True

    #Singleton
    settings = Settings()


