import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Only load .env if DATABASE_URL is not already set in environment
        env_file=".env" if not os.getenv("DATABASE_URL") else None,
        case_sensitive=True,
    )

    # API Settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Iris"

    # Database Settings
    DATABASE_URL: str = Field(default="sqlite:///./test.db")
    SECRET_KEY: str = Field(default="test-secret")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # NLP Settings
    NLP_MODEL_PATH: str = "fr_core_news_sm"
    OPENAI_API_KEY: str | None = Field(default=None)
    LLM_CONFIDENCE_THRESHOLD: float = Field(default=0.6)

    # Gmail OAuth (optional; for OAuth callback flow)
    GOOGLE_CLIENT_ID: str | None = Field(default=None)
    GOOGLE_CLIENT_SECRET: str | None = Field(default=None)
    GMAIL_REDIRECT_URI: str | None = Field(default=None)
    GMAIL_CREDENTIALS_PATH: str = Field(default="credentials.json")

settings = Settings()

