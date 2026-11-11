"""Environment-based application settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Personal Job Finder"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./job_finder.db"
    prosple_rss_url: str = ""
    prosple_rss_allowed_hosts: str = "prosple.com,gradaustralia.com.au"
    gmail_oauth_client_file: str = "secrets/gmail-oauth-client.json"
    gmail_token_file: str = "secrets/gmail-token.json"
    gmail_seek_label: str = "SEEK Job Alerts"
    gmail_seek_query: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings so configuration is consistent per process."""
    return Settings()
