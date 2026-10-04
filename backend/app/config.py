from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Environment & Server
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Security & Tokens
    SECRET_KEY: str = Field(default="dev-secret-key-change-in-production-cafe-ai-waiter-32chars-min", description="JWT & session secret key")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 hours
    CUSTOMER_SESSION_EXPIRE_MINUTES: int = 60 * 4  # 4 hours
    WS_TICKET_EXPIRE_SECONDS: int = 60

    # MongoDB
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "cafe_ai_waiter"

    # Redis (Optional in local dev / fallback)
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = False

    # AI Provider Settings (OpenAI-compatible endpoint)
    AI_BASE_URL: Optional[str] = "https://generativelanguage.googleapis.com/v1beta/openai/"
    AI_API_KEY: Optional[str] = None
    AI_MODEL: str = "gemini-2.0-flash"
    AI_FALLBACK_BASE_URL: Optional[str] = None
    AI_FALLBACK_API_KEY: Optional[str] = None
    AI_FALLBACK_MODEL: Optional[str] = None

    # Storage (Cloudflare R2)
    R2_ENDPOINT_URL: Optional[str] = None
    R2_ACCESS_KEY_ID: Optional[str] = None
    R2_SECRET_ACCESS_KEY: Optional[str] = None
    R2_PRIVATE_BUCKET: str = "cafe-private-uploads"
    R2_PUBLIC_BUCKET: str = "cafe-public-assets"
    R2_PUBLIC_URL_BASE: Optional[str] = None


settings = Settings()
