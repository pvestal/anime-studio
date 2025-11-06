"""
Dynamic Model Manager for ComfyUI
Scans available models and selects optimal models based on generation parameters
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class ModelInfo:
    filename: str
    style: str  # anime, realistic, artistic, general
    quality: str  # fast, standard, high, ultra
    description: str
    file_size_gb: float = 0.0

class ModelCatalog:
    """Maintains catalog of available ComfyUI models with metadata"""
    
    COMFYUI_BASE = Path("/mnt/1TB-storage/ComfyUI")
    
    # Model metadata database
    CHECKPOINT_METADATA = {
        "AOM3A1B.safetensors": ModelInfo(
            filename="AOM3A1B.safetensors",
            style="anime",
            quality="high",
            description="High-quality anime checkpoint, detailed characters"
        ),
        "counterfeit_v3.safetensors": ModelInfo(
            filename="counterfeit_v3.safetensors",
            style="anime",
            quality="standard",
            description="Fast anime generation, good balance"
        ),
        "Counterfeit-V2.5.safetensors": ModelInfo(
            filename="Counterfeit-V2.5.safetensors",
            style="anime",
            quality="standard",
            description="Previous version of Counterfeit"
        ),
        "flux1-schnell.safetensors": ModelInfo(
            filename="flux1-schnell.safetensors",
            style="general",
            quality="fast",
            description="Fast general-purpose schnell model"
        ),
        "juggernautXL_v9.safetensors": ModelInfo(
            filename="juggernautXL_v9.safetensors",
            style="realistic",
            quality="high",
            description="High-quality realistic SDXL model"
        ),
    }
    
    MOTION_MODEL_METADATA = {
        "mm-Stabilized_high.pth": {
            "quality": "high",
            "description": "High-quality motion model for smooth animation"
        },
        "mm-Stabilized_mid.pth": {
            "quality": "standard",
            "description": "Standard motion model, faster generation"
        }
    }
    
    VAE_METADATA = {
        "vae-ft-mse-840000-ema-pruned.safetensors": {
            "quality": "standard",
            "description": "Standard VAE, well-tested"
        },
        "vae-ft-mse.safetensors": {
            "quality": "high",
            "description": "Full VAE for higher quality"
        }
    }
    
    def __init__(self):
        self.scan_models()
    
    def scan_models(self) -> Dict:
        """Scan ComfyUI directories for available models"""
        available = {
            "checkpoints": [],
            "motion_models": [],
            "vaes": []
        }
        
        # Scan checkpoints
        checkpoint_dir = self.COMFYUI_BASE / "models" / "checkpoints"
        if checkpoint_dir.exists():
            for f in checkpoint_dir.glob("*.safetensors"):
                if f.name in self.CHECKPOINT_METADATA:
                    available["checkpoints"].append(f.name)
        
        # Scan motion models
        motion_dir = self.COMFYUI_BASE / "models" / "animatediff_models"
        if motion_dir.exists():
            for f in motion_dir.glob("*.pth"):
                if f.name in self.MOTION_MODEL_METADATA:
                    available["motion_models"].append(f.name)
        
        # Scan VAEs
        vae_dir = self.COMFYUI_BASE / "models" / "vae"
        if vae_dir.exists():
            for f in vae_dir.glob("*.safetensors"):
                if f.name in self.VAE_METADATA:
                    available["vaes"].append(f.name)
        
        logger.info(f"Scanned models: {len(available['checkpoints'])} checkpoints, "
                   f"{len(available['motion_models'])} motion, {len(available['vaes'])} VAEs")
        
        return available

class DynamicModelManager:
    """Intelligently selects models based on generation parameters"""
    
    def __init__(self):
        self.catalog = ModelCatalog()
        self.available = self.catalog.scan_models()
    
    def select_checkpoint(self, style: str, quality: str) -> str:
        """
        Select optimal checkpoint model
        
        Args:
            style: anime, realistic, artistic, general
            quality: fast, standard, high, ultra
        
        Returns:
            Checkpoint filename
        """
        candidates = []
        
        for ckpt_name in self.available["checkpoints"]:
            metadata = self.catalog.CHECKPOINT_METADATA.get(ckpt_name)
            if not metadata:
                continue
            
            # Match style
            if metadata.style == style:
                # Prioritize exact quality match
                if metadata.quality == quality:
                    return ckpt_name
                candidates.append(ckpt_name)
        
        # Fallback: return first candidate or default
        if candidates:
            return candidates[0]
        
        # Default anime checkpoint
        if "counterfeit_v3.safetensors" in self.available["checkpoints"]:
            return "counterfeit_v3.safetensors"
        
        # Last resort: first available
        return self.available["checkpoints"][0] if self.available["checkpoints"] else None
    
    def select_motion_model(self, quality: str) -> str:
        """
        Select AnimateDiff motion model based on quality
        
        Args:
            quality: fast, standard, high, ultra
        
        Returns:
            Motion model filename
        """
        if quality in ["high", "ultra"]:
            if "mm-Stabilized_high.pth" in self.available["motion_models"]:
                return "mm-Stabilized_high.pth"
        
        # Standard/fast fallback
        if "mm-Stabilized_mid.pth" in self.available["motion_models"]:
            return "mm-Stabilized_mid.pth"
        
        # Last resort
        return self.available["motion_models"][0] if self.available["motion_models"] else None
    
    def select_vae(self, quality: str) -> str:
        """
        Select VAE model based on quality
        
        Args:
            quality: fast, standard, high, ultra
        
        Returns:
            VAE filename
        """
        if quality in ["high", "ultra"]:
            if "vae-ft-mse.safetensors" in self.available["vaes"]:
                return "vae-ft-mse.safetensors"
        
        # Standard fallback
        if "vae-ft-mse-840000-ema-pruned.safetensors" in self.available["vaes"]:
            return "vae-ft-mse-840000-ema-pruned.safetensors"
        
        # Last resort
        return self.available["vaes"][0] if self.available["vaes"] else None
    
    def select_models(self, style: str = "anime", quality: str = "standard", 
                      character: Optional[str] = None) -> Dict[str, str]:
        """
        Select all models for a generation task
        
        Args:
            style: anime, realistic, artistic, general
            quality: fast, standard, high, ultra
            character: Optional character name (for character-specific preferences)
        
        Returns:
            Dict with checkpoint, motion_model, vae keys
        """
        # Future: Check character database for preferred checkpoint
        # if character:
        #     char_prefs = self.get_character_preferences(character)
        #     if char_prefs and "checkpoint" in char_prefs:
        #         checkpoint = char_prefs["checkpoint"]
        
        models = {
            "checkpoint": self.select_checkpoint(style, quality),
            "motion_model": self.select_motion_model(quality),
            "vae": self.select_vae(quality)
        }
        
        # Validate all models found
        if not all(models.values()):
            missing = [k for k, v in models.items() if not v]
            logger.warning(f"Missing models: {missing}")
        
        logger.info(f"Selected models for {style}/{quality}: {models}")
        return models
    
    def validate_models(self, models: Dict[str, str]) -> bool:
        """Validate that all specified models exist"""
        base = self.catalog.COMFYUI_BASE
        
        checks = [
            (base / "models" / "checkpoints" / models["checkpoint"], "checkpoint"),
            (base / "models" / "animatediff_models" / models["motion_model"], "motion_model"),
            (base / "models" / "vae" / models["vae"], "vae")
        ]
        
        for path, model_type in checks:
            if not path.exists():
                logger.error(f"Model not found: {model_type} at {path}")
                return False
        
        return True
    
    def get_model_info(self, checkpoint: str) -> Optional[ModelInfo]:
        """Get metadata for a checkpoint model"""
        return self.catalog.CHECKPOINT_METADATA.get(checkpoint)


# Test/CLI interface
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    manager = DynamicModelManager()
    
    print("\n=== Available Models ===")
    print(f"Checkpoints: {manager.available['checkpoints']}")
    print(f"Motion: {manager.available['motion_models']}")
    print(f"VAEs: {manager.available['vaes']}")
    
    print("\n=== Model Selection Tests ===")
    
    tests = [
        {"style": "anime", "quality": "standard"},
        {"style": "anime", "quality": "high"},
        {"style": "anime", "quality": "ultra"},
        {"style": "realistic", "quality": "high"},
    ]
    
    for test in tests:
        models = manager.select_models(**test)
        valid = manager.validate_models(models)
        print(f"\n{test['style']}/{test['quality']}: {models}")
        print(f"  Validated: {valid}")
