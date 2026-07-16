"""Runtime configuration.

Single source of truth for env-driven settings. Modules import `settings` rather
than reading `os.environ` directly so tests can override via pydantic-settings
and so a missing variable fails at import time with a clear message.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_hours: int = Field(default=8, alias="JWT_EXPIRE_HOURS")

    admin_email: str = Field(default="admin@welyne.local", alias="ADMIN_EMAIL")
    admin_password: str = Field(default="", alias="ADMIN_PASSWORD")

    app_env: str = Field(default="dev", alias="APP_ENV")

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3001"], alias="CORS_ORIGINS"
    )

    # WhatsApp Cloud API (A5/A6 transport). Empty = stub mode (no real send;
    # the webhook verify handshake is disabled).
    whatsapp_token: str = Field(default="", alias="WHATSAPP_TOKEN")
    whatsapp_phone_id: str = Field(default="", alias="WHATSAPP_PHONE_ID")
    whatsapp_verify_token: str = Field(default="", alias="WHATSAPP_VERIFY_TOKEN")
    whatsapp_app_secret: str = Field(default="", alias="WHATSAPP_APP_SECRET")
    whatsapp_api_version: str = Field(default="v23.0", alias="WHATSAPP_API_VERSION")


settings = Settings()  # type: ignore[call-arg]
