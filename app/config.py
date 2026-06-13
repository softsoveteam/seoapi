from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://seosoft:seosoft@localhost:5432/seosoft"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "https://8.softsove.life/api/auth/callback"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"
    frontend_url: str = "https://8.softsove.life"
    sync_hour: int = 6
    trend_threshold_percent: float = 5.0


settings = Settings()
