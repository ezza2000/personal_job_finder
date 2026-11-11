"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.logging_config import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Report that the API process is responding."""
    return {"status": "ok"}
