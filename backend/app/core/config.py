"""Centralized application configuration, loaded once from environment variables."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, EmailStr, model_validator
from urllib.parse import urlsplit


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True)

    # App
    environment: Literal['development', 'test', 'production'] = "development"
    debug: bool = True
    cors_origins: str = "http://localhost:5173"

    # Database
    database_url: str
    postgres_user: str | None = None
    postgres_password: str | None = None
    postgres_db: str | None = None

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Password recovery; configure an SMTP service or the optional local mailbox.
    password_reset_frontend_url: str = "http://localhost:5173"
    password_reset_expire_minutes: int = Field(default=30, ge=5, le=60)
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: EmailStr | None = None
    smtp_starttls: bool = True
    smtp_ssl: bool = False

    # Secrets encryption
    encryption_key: str

    # Rate limiting
    auth_rate_limit_max_attempts: int = 10
    auth_rate_limit_window_seconds: int = 60

    # Live trading kill switch (Phase 10)
    enable_live_trading: bool = False

    @model_validator(mode='after')
    def production_configuration(self):
        if self.environment != 'production':
            return self
        from cryptography.fernet import Fernet
        if self.debug or len(self.jwt_secret.encode()) < 32 or self.jwt_secret.lower().startswith(('change', 'test', 'dev')):
            raise ValueError('Production requires DEBUG=false and a dedicated random signing secret of at least 32 bytes.')
        try:
            Fernet(self.encryption_key.encode())
        except Exception:
            raise ValueError('Production requires a valid dedicated Fernet encryption key.') from None
        if not self.database_url.startswith('postgresql+asyncpg://'):
            raise ValueError('Production requires PostgreSQL with asyncpg.')
        origins = self.cors_origins_list
        if len(origins) != 1:
            raise ValueError('Production requires one same-origin HTTPS frontend.')
        parsed = urlsplit(origins[0])
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.hostname in {'localhost', '127.0.0.1', '::1'}
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or '*' in origins[0]):
            raise ValueError('Production requires an explicit public HTTPS origin without a path.')
        if self.access_token_expire_minutes > 60 or self.access_token_expire_minutes < 5:
            raise ValueError('Production browser sessions must expire in 5–60 minutes.')
        if not self.smtp_host or not self.smtp_from_email or not (self.smtp_starttls or self.smtp_ssl):
            raise ValueError('Production requires configured encrypted SMTP for account recovery and verification.')
        if self.password_reset_frontend_url.rstrip('/') != origins[0]:
            raise ValueError('Account emails must link to the configured frontend origin.')
        return self

    # Exchange credentials (placeholders — real usage starts Phase 5)
    binance_api_key: str | None = None
    binance_secret: str | None = None

    # Sentiment API credentials
    newsapi_api_key: str | None = None
    hf_token: str | None = None
    sentiment_inference_mode: Literal['local', 'hosted'] = 'local'
    sentiment_news_provider: Literal['rss', 'newsapi'] = 'rss'
    rss_news_window_hours: int = Field(default=72, ge=24, le=168)
    newsapi_delay_hours: int = Field(default=24, ge=0, le=168)
    cryptopanic_api_key: str | None = None
    twitter_api_key: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
