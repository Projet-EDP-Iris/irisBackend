
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )

    # API Settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Iris"
    ENVIRONMENT: str = Field(default="development")

    # Database Settings
    DATABASE_URL: str = Field(default="sqlite:///./test.db")
    SECRET_KEY: str = Field(default="test-secret")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # NLP Settings
    NLP_MODEL_PATH: str = "fr_core_news_sm"
    # Accepts both OPENAI_API_KEY and OPEN_AI_KEY from the environment
    OPENAI_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "OPEN_AI_KEY"),
    )
    LLM_CONFIDENCE_THRESHOLD: float = Field(default=0.75)
    TEXTCAT_MODEL_PATH: str = Field(default="app/ML/models/iris_textcat")
    TEXTCAT_CONFIDENCE_THRESHOLD: float = Field(default=0.65)

    # Resend (transactional email)
    RESEND_API_KEY: str | None = Field(default=None)
    RESEND_FROM_EMAIL: str = Field(default="noreply@iris-app.com")

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

    # Frontend URL — used in email links
    FRONTEND_URL: str = Field(default="http://localhost:5173")

    # Email (SMTP) — set EMAIL_ENABLED=true and configure SMTP to send real emails
    EMAIL_ENABLED: bool = Field(default=False)
    SMTP_HOST: str = Field(default="smtp.gmail.com")
    SMTP_PORT: int = Field(default=587)
    SMTP_USE_TLS: bool = Field(default=True)
    SMTP_USERNAME: str | None = Field(default=None)
    SMTP_PASSWORD: str | None = Field(default=None)
    SMTP_FROM_EMAIL: str = Field(default="noreply@iris-app.com")

    # Token expiry
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = Field(default=24)

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.ENVIRONMENT.lower() == "production":
            if self.SECRET_KEY == "test-secret" or len(self.SECRET_KEY) < 32:
                raise ValueError("SECRET_KEY must be a strong, non-default value in production")
            if not self.FRONTEND_URL.startswith("https://"):
                raise ValueError("FRONTEND_URL must use HTTPS in production")
        return self


settings = Settings()

