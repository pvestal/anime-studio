#!/usr/bin/env python3
"""
Security utilities for Anime Production System
Provides secure credential management and input validation
"""

import os
import re
import hvac
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class SecureCredentialManager:
    """Centralized secure credential management for anime production system"""

    def __init__(self):
        self.vault_client = self._init_vault_client()

    def _init_vault_client(self) -> Optional[hvac.Client]:
        """Initialize HashiCorp Vault client for secure credential retrieval"""
        try:
            vault_url = os.getenv('VAULT_ADDR', 'http://127.0.0.1:8200')
            client = hvac.Client(url=vault_url)

            # Try to get token from file first, then environment
            token_paths = [
                Path('/opt/vault/.vault-token'),
                Path('/opt/vault/data/vault-token'),
                Path('/home/patrick/.vault-token')
            ]

            vault_token = os.getenv('VAULT_TOKEN')
            if not vault_token:
                for token_path in token_paths:
                    if token_path.exists():
                        vault_token = token_path.read_text().strip()
                        break

            if vault_token:
                client.token = vault_token
                if client.is_authenticated():
                    logger.info("Successfully authenticated with Vault")
                    return client
                else:
                    logger.warning("Vault token invalid or expired")
            else:
                logger.warning("No Vault token found")

        except Exception as e:
            logger.error(f"Failed to initialize Vault client: {e}")

        return None

    def get_database_config(self) -> Dict[str, str]:
        """Get secure database configuration"""
        config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'database': os.getenv('DB_NAME', 'anime_production'),
            'user': os.getenv('DB_USER', 'patrick'),
            'password': self._get_db_password()
        }
        return config

    def _get_db_password(self) -> str:
        """Securely retrieve database password from Vault or environment"""
        # Try Vault first
        if self.vault_client:
            try:
                # Try different secret paths
                secret_paths = [
                    'secret/tower/database',
                    'secret/anime_production/database',
                    'secret/echo_brain/database'
                ]

                for path in secret_paths:
                    try:
                        response = self.vault_client.secrets.kv.v2.read_secret_version(path=path)
                        if response and 'data' in response and 'data' in response['data']:
                            password = response['data']['data'].get('password')
                            if password:
                                logger.info(f"Retrieved database password from Vault path: {path}")
                                return password
                    except Exception:
                        continue

            except Exception as e:
                logger.warning(f"Failed to retrieve password from Vault: {e}")

        # Fallback to environment variable
        env_password = os.getenv('DB_PASSWORD')
        if env_password:
            logger.info("Using database password from environment variable")
            return env_password

        # Last resort - log security warning
        logger.critical("SECURITY WARNING: No secure database password found, using empty password")
        return ''


class InputValidator:
    """Input validation utilities to prevent injection attacks"""

    @staticmethod
    def validate_character_name(name: str) -> bool:
        """Validate character name to prevent injection attacks"""
        if not name or not isinstance(name, str):
            return False

        # Only allow alphanumeric, spaces, hyphens, and periods
        return bool(re.match(r'^[a-zA-Z0-9\s\-\.]+$', name)) and len(name) <= 100

    @staticmethod
    def validate_project_name(name: str) -> bool:
        """Validate project name"""
        if not name or not isinstance(name, str):
            return False

        return bool(re.match(r'^[a-zA-Z0-9\s\-\_\.]+$', name)) and len(name) <= 200

    @staticmethod
    def validate_file_path(file_path: str, allowed_base_path: str) -> bool:
        """Validate file path to prevent directory traversal attacks"""
        if not file_path or not isinstance(file_path, str):
            return False

        try:
            # Resolve both paths to absolute paths
            resolved_file_path = Path(file_path).resolve()
            resolved_base_path = Path(allowed_base_path).resolve()

            # Check if the file path is within the allowed directory
            resolved_file_path.relative_to(resolved_base_path)
            return True
        except (ValueError, OSError):
            return False

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename to prevent path traversal"""
        if not filename or not isinstance(filename, str):
            return ""

        # Remove any path separators and dangerous characters
        sanitized = re.sub(r'[/\\:*?"<>|]', '', filename)
        sanitized = re.sub(r'\.\.', '', sanitized)  # Remove ..

        return sanitized[:255]  # Limit length

    @staticmethod
    def validate_prompt_text(prompt: str) -> bool:
        """Validate prompt text for generation requests"""
        if not prompt or not isinstance(prompt, str):
            return False

        # Check for reasonable length and no script injection patterns
        if len(prompt) > 5000:  # Reasonable limit for prompts
            return False

        # Check for potential script injection patterns
        dangerous_patterns = [
            r'<script',
            r'javascript:',
            r'onload=',
            r'onerror=',
            r'eval\(',
            r'exec\(',
            r'import\s+os',
            r'subprocess\.',
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, prompt, re.IGNORECASE):
                return False

        return True


# Global instances for easy access
credential_manager = SecureCredentialManager()
input_validator = InputValidator()