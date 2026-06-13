from pydantic_settings import BaseSettings, SettingsConfigDict

# Production URLs — used when .env still has localhost.
LIVE_FRONTEND_URL = "https://8.softsove.life"
LIVE_GOOGLE_REDIRECT_URI = "https://8.softsove.life/api/auth/callback"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://seosoft:seosoft@localhost:5432/seosoft"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = LIVE_GOOGLE_REDIRECT_URI
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"
    frontend_url: str = LIVE_FRONTEND_URL
    sync_hour: int = 6
    trend_threshold_percent: float = 5.0


settings = Settings()


def _is_local_url(url: str) -> bool:
    lower = url.lower()
    return not url or "localhost" in lower or "127.0.0.1" in lower


def resolved_frontend_url() -> str:
    url = settings.frontend_url.strip().rstrip("/")
    if _is_local_url(url):
        return LIVE_FRONTEND_URL
    return url


def resolved_google_redirect_uri() -> str:
    url = settings.google_redirect_uri.strip()
    if _is_local_url(url):
        return LIVE_GOOGLE_REDIRECT_URI
    return url
