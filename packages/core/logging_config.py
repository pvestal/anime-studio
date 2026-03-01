"""Centralized logging — rotating file handler + console output.

Call setup_logging() once at app startup (replaces logging.basicConfig).
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import APP_ENV

_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "anime-studio.log"
_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging():
    """Configure root logger with rotating file + console handlers."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if APP_ENV == "dev" else logging.INFO

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid adding duplicate handlers on reload
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return

    formatter = logging.Formatter(_FORMAT)

    # Rotating file handler: 10 MB, 5 backups
    file_handler = RotatingFileHandler(
        _LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root.addHandler(file_handler)

    # Console handler (uvicorn already has one, so only add if none exist)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in root.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root.addHandler(console_handler)
