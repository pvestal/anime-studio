"""Environment-based configuration for Tower Anime Production.

All configuration is loaded from Vault with environment variable fallbacks.
Vault path: secret/anime/database
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from config.vault_client import get_database_config


def _load_db_config():
    """Load database config from Vault (or env var fallback) once."""
    return get_database_config()


# Resolve at import time so all dataclass instances share the same credentials
_db = _load_db_config()


@dataclass
class DatabaseConfig:
    """PostgreSQL database configuration loaded from Vault."""

    host: str = field(default_factory=lambda: _db["host"])
    port: int = field(default_factory=lambda: _db["port"])
    name: str = field(default_factory=lambda: _db["database"])
    user: str = field(default_factory=lambda: _db["user"])
    password: str = field(default_factory=lambda: _db["password"])

    @property
    def url(self) -> str:
        """Get database connection URL."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def async_url(self) -> str:
        """Get async database connection URL for asyncpg."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class RedisConfig:
    """Redis configuration for job queue."""

    host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))

    @property
    def url(self) -> str:
        """Get Redis connection URL."""
        return f"redis://{self.host}:{self.port}/{self.db}"


@dataclass
class ComfyUIConfig:
    """ComfyUI configuration."""

    host: str = field(default_factory=lambda: os.getenv("COMFYUI_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("COMFYUI_PORT", "8188")))
    output_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("COMFYUI_OUTPUT_DIR", "/opt/ComfyUI/output")
        )
    )
    models_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("COMFYUI_MODELS_DIR", "/mnt/1TB-storage/models")
        )
    )

    @property
    def base_url(self) -> str:
        """Get ComfyUI base URL."""
        return f"http://{self.host}:{self.port}"

    @property
    def prompt_url(self) -> str:
        """Get ComfyUI prompt submission URL."""
        return f"{self.base_url}/prompt"

    @property
    def queue_url(self) -> str:
        """Get ComfyUI queue URL."""
        return f"{self.base_url}/queue"


@dataclass
class EchoBrainConfig:
    """Echo Brain AI orchestration configuration."""

    host: str = field(default_factory=lambda: os.getenv("ECHO_BRAIN_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("ECHO_BRAIN_PORT", "8309")))

    @property
    def base_url(self) -> str:
        """Get Echo Brain base URL."""
        return f"http://{self.host}:{self.port}"


@dataclass
class LoraStudioConfig:
    """LoRA Studio service configuration."""

    host: str = field(default_factory=lambda: os.getenv("LORA_STUDIO_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("LORA_STUDIO_PORT", "8401")))

    @property
    def base_url(self) -> str:
        """Get LoRA Studio base URL."""
        return f"http://{self.host}:{self.port}"

    @property
    def approval_url(self) -> str:
        """Get dataset approval endpoint."""
        return f"{self.base_url}/api/approval"

    @property
    def characters_url(self) -> str:
        """Get characters endpoint."""
        return f"{self.base_url}/api/approval/characters"


class FramePackConfig:
    """FramePack video generation configuration."""

    # Model paths (relative to models_dir)
    diffusion_model: str = "diffusion_models/FramePackI2V_HY_fp8_e4m3fn.safetensors"
    clip_l_model: str = "text_encoders/clip_l.safetensors"
    llava_model: str = "text_encoders/llava_llama3_fp16.safetensors"
    sigclip_model: str = "clip_vision/sigclip_vision_patch14_384.safetensors"
    vae_model: str = "vae/hunyuan_video_vae_bf16.safetensors"

    # Generation defaults
    default_segment_duration: int = 30  # seconds
    max_segment_duration: int = 60  # seconds
    default_fps: int = 30
    default_width: int = 1280
    default_height: int = 720

    # Quality thresholds
    quality_success_threshold: float = 0.7  # Score above this = successful
    quality_failure_threshold: float = 0.4  # Score below this = failed

    # VRAM management (RTX 3060 12GB)
    required_vram_mb: int = 6000  # FramePack needs ~6GB


@dataclass
class APIConfig:
    """API server configuration."""

    host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8328")))
    debug: bool = field(
        default_factory=lambda: os.getenv("API_DEBUG", "false").lower() == "true"
    )
    allowed_origins: List[str] = field(
        default_factory=lambda: os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000,http://localhost:5173,https://tower.local",
        ).split(",")
    )


@dataclass
class Settings:
    """Application settings container."""

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    comfyui: ComfyUIConfig = field(default_factory=ComfyUIConfig)
    echo_brain: EchoBrainConfig = field(default_factory=EchoBrainConfig)
    lora_studio: LoraStudioConfig = field(default_factory=LoraStudioConfig)
    framepack: FramePackConfig = field(default_factory=FramePackConfig)
    api: APIConfig = field(default_factory=APIConfig)

    # Environment
    environment: str = field(
        default_factory=lambda: os.getenv("ENVIRONMENT", "development")
    )
    testing: bool = field(
        default_factory=lambda: os.getenv("TESTING", "false").lower() == "true"
    )


# Global settings instance
settings = Settings()
