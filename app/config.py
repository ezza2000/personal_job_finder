"""Environment-based application settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Personal Job Finder"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./job_finder.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings so configuration is consistent per process."""
    return Settings()
