import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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

    # Encryption key for Apple App Passwords stored in the DB
    # Generate once: poetry run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    SECRET_ENCRYPTION_KEY: str | None = Field(default=None)

    # Microsoft / Outlook OAuth (Azure App Registration)
    # Register at https://portal.azure.com → App registrations → New registration
    # Required scopes: Calendars.ReadWrite Tasks.ReadWrite offline_access User.Read
    MICROSOFT_CLIENT_ID: str | None = Field(default=None)
    MICROSOFT_CLIENT_SECRET: str | None = Field(default=None)
    MICROSOFT_TENANT_ID: str = Field(default="common")
    # "common" allows any Microsoft/Outlook account; set a specific tenant ID for org-only
    MICROSOFT_REDIRECT_URI: str = Field(default="http://localhost:8000/api/v1/auth/microsoft/callback")

settings = Settings()

