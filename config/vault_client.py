"""Vault client for fetching secrets at runtime.

Connects to HashiCorp Vault to retrieve database credentials and other secrets.
Falls back to environment variables if Vault is unavailable.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_vault_secret(path: str, mount_point: str = "secret") -> Optional[dict]:
    """Fetch a secret from Vault's KV v2 engine.

    Args:
        path: Secret path (e.g. 'anime/database')
        mount_point: KV mount point (default: 'secret')

    Returns:
        Dict of secret data, or None if unavailable.
    """
    vault_addr = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
    vault_token = os.getenv("VAULT_TOKEN")

    if not vault_token:
        token_file = os.path.expanduser("~/.vault-token")
        if os.path.exists(token_file):
            with open(token_file) as f:
                vault_token = f.read().strip()

    if not vault_token:
        logger.warning("No VAULT_TOKEN found, falling back to environment variables")
        return None

    try:
        import hvac
        client = hvac.Client(url=vault_addr, token=vault_token)

        if not client.is_authenticated():
            logger.warning("Vault authentication failed, falling back to environment variables")
            return None

        response = client.secrets.kv.v2.read_secret_version(
            path=path, mount_point=mount_point, raise_on_deleted_version=True
        )
        data = response["data"]["data"]
        logger.info(f"Loaded secret from Vault: {path}")
        return data

    except Exception as e:
        logger.warning(f"Vault unavailable ({e}), falling back to environment variables")
        return None


def get_database_config() -> dict:
    """Get database configuration from Vault, falling back to env vars.

    Returns:
        Dict with keys: host, port, user, password, database
    """
    secret = get_vault_secret("anime/database")
    if secret:
        return {
            "host": secret.get("host", "localhost"),
            "port": int(secret.get("port", 5432)),
            "user": secret.get("user", "patrick"),
            "password": secret["password"],
            "database": secret.get("database", "anime_production"),
        }

    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "user": os.getenv("DB_USER", "patrick"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "anime_production"),
    }


def get_database_url() -> str:
    """Get a fully-formed PostgreSQL connection URL."""
    cfg = get_database_config()
    return f"postgresql://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['database']}"
