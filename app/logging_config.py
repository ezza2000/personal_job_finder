"""Consistent application logging setup."""

import logging


def configure_logging(level: str) -> None:
    """Configure a concise log format and fall back safely for invalid levels."""
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=resolved_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
