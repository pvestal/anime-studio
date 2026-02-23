"""Configuration — Vault integration, path constants, ComfyUI settings."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve paths relative to the project root (two levels up from this file)
_PACKAGE_DIR = Path(__file__).resolve().parent          # packages/core/
_PACKAGES_DIR = _PACKAGE_DIR.parent                     # packages/
_PROJECT_DIR = _PACKAGES_DIR.parent                     # /opt/anime-studio/
_SCRIPT_DIR = _PROJECT_DIR / "server"                    # server/
BASE_PATH = _PROJECT_DIR / "datasets"
MOVIES_DIR = BASE_PATH / "_movies"
MOVIES_DIR.mkdir(parents=True, exist_ok=True)

# ComfyUI endpoints & paths
COMFYUI_URL = "http://127.0.0.1:8188"
COMFYUI_OUTPUT_DIR = Path("/opt/ComfyUI/output")
COMFYUI_INPUT_DIR = Path("/opt/ComfyUI/input")

# Default vision model for all VLM tasks
VISION_MODEL = "gemma3:12b"

# Ollama endpoint
OLLAMA_URL = "http://localhost:11434"

# Sampler name mapping: human-readable → ComfyUI internal (sampler_name, scheduler)
SAMPLER_MAP = {
    "DPM++ 2M Karras": ("dpmpp_2m", "karras"),
    "DPM++ 2M SDE Karras": ("dpmpp_2m_sde", "karras"),
    "DPM++ 2S a Karras": ("dpmpp_2s_ancestral", "karras"),
    "DPM++ SDE Karras": ("dpmpp_sde", "karras"),
    "DPM++ 2M": ("dpmpp_2m", "normal"),
    "Euler a": ("euler_ancestral", "normal"),
    "Euler": ("euler", "normal"),
    "DDIM": ("ddim", "ddim_uniform"),
}


def normalize_sampler(sampler: str | None, scheduler: str | None) -> tuple[str, str]:
    """Convert human-readable sampler names to ComfyUI internal names."""
    if sampler and sampler in SAMPLER_MAP:
        return SAMPLER_MAP[sampler]
    return (sampler or "dpmpp_2m", scheduler or "karras")


def _load_db_config() -> dict:
    """Load database config from Vault, falling back to env vars."""
    vault_addr = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
    vault_token = os.getenv("VAULT_TOKEN")

    if not vault_token:
        token_file = os.path.expanduser("~/.vault-token")
        if os.path.exists(token_file):
            with open(token_file) as f:
                vault_token = f.read().strip()

    if vault_token:
        try:
            import hvac
            client = hvac.Client(url=vault_addr, token=vault_token)
            if client.is_authenticated():
                response = client.secrets.kv.v2.read_secret_version(
                    path="anime/database", mount_point="secret",
                    raise_on_deleted_version=True,
                )
                data = response["data"]["data"]
                logger.info("Loaded database credentials from Vault: anime/database")
                return {
                    "host": data.get("host", "localhost"),
                    "database": data.get("database", "anime_production"),
                    "user": data.get("user", "patrick"),
                    "password": data["password"],
                }
        except Exception as e:
            logger.warning(f"Vault unavailable ({e}), falling back to env vars")

    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "database": os.getenv("DB_NAME", "anime_production"),
        "user": os.getenv("DB_USER", "patrick"),
        "password": os.getenv("DB_PASSWORD", ""),
    }


DB_CONFIG = _load_db_config()


async def load_config():
    """Async config initialization hook for app startup."""
    logger.info(f"Config loaded: DB={DB_CONFIG['database']}@{DB_CONFIG['host']}")
    logger.info(f"Datasets: {BASE_PATH}")
    logger.info(f"ComfyUI: {COMFYUI_URL}")
