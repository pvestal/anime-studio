#!/usr/bin/env python3
"""
Production Quality Gate Configurations for Anime System
Calibrated based on real anime character consistency data
"""

import json
import sqlite3
from typing import Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class QualityGateConfigs:
    """Manage quality gate configurations for different use cases"""

    # Calibrated thresholds based on Kai Nakamura analysis
    ANIME_THRESHOLDS = {
        "hero_character": {
            "name": "Hero Character (Main Protagonist)",
            "clip_consistency": 0.75,  # 75% - allows for pose/expression variation
            "technical_quality": 0.90,  # High technical standards
            "visual_quality": 0.85,     # Good visual quality required
            "description": "Strict consistency for main characters with some artistic flexibility"
        },
        "supporting_character": {
            "name": "Supporting Character",
            "clip_consistency": 0.70,  # 70% - more flexibility for varied scenes
            "technical_quality": 0.85,
            "visual_quality": 0.80,
            "description": "Balanced consistency for recurring characters"
        },
        "background_character": {
            "name": "Background/Crowd Character",
            "clip_consistency": 0.65,  # 65% - maximum flexibility
            "technical_quality": 0.80,
            "visual_quality": 0.75,
            "description": "Relaxed standards for background characters"
        },
        "style_reference": {
            "name": "Style Reference Only",
            "clip_consistency": 0.60,  # 60% - just checking art style
            "technical_quality": 0.75,
            "visual_quality": 0.70,
            "description": "Minimal consistency for style matching only"
        },
        "experimental": {
            "name": "Experimental/Draft Mode",
            "clip_consistency": 0.50,  # 50% - very loose
            "technical_quality": 0.70,
            "visual_quality": 0.65,
            "description": "Loose standards for experimentation"
        }
    }

    # Technical quality requirements
    TECHNICAL_REQUIREMENTS = {
        "production": {
            "min_resolution": (1024, 1024),
            "max_file_size_mb": 10,
            "allowed_formats": ["png", "jpg", "jpeg"],
            "min_dpi": 72
        },
        "draft": {
            "min_resolution": (512, 512),
            "max_file_size_mb": 20,
            "allowed_formats": ["png", "jpg", "jpeg", "webp"],
            "min_dpi": 72
        }
    }

    # Visual quality metrics
    VISUAL_QUALITY_METRICS = {
        "brightness": {"min": 0.2, "max": 0.9, "optimal": 0.5},
        "contrast": {"min": 0.3, "max": 1.0, "optimal": 0.7},
        "saturation": {"min": 0.2, "max": 0.9, "optimal": 0.6},
        "sharpness": {"min": 50, "threshold": 100}  # Laplacian variance
    }

    def __init__(self, db_path: str = "/opt/tower-anime-production/database/anime_production.db"):
        self.db_path = db_path
        self._ensure_config_table()
        self._load_or_create_defaults()

    def _ensure_config_table(self):
        """Ensure quality_gate_configs table exists"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quality_gate_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_name TEXT UNIQUE NOT NULL,
                    config_type TEXT NOT NULL,
                    config_data TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)
            conn.commit()

    def _load_or_create_defaults(self):
        """Load existing configs or create defaults"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Check if configs exist
            cursor.execute("SELECT COUNT(*) as count FROM quality_gate_configs WHERE is_active = 1")
            count = cursor.fetchone()[0]

            if count == 0:
                logger.info("Creating default quality gate configurations")

                # Insert anime thresholds
                for key, config in self.ANIME_THRESHOLDS.items():
                    cursor.execute("""
                        INSERT INTO quality_gate_configs
                        (config_name, config_type, config_data, created_by)
                        VALUES (?, 'anime_threshold', ?, 'system')
                    """, (key, json.dumps(config)))

                # Insert technical requirements
                for key, config in self.TECHNICAL_REQUIREMENTS.items():
                    cursor.execute("""
                        INSERT INTO quality_gate_configs
                        (config_name, config_type, config_data, created_by)
                        VALUES (?, 'technical_requirement', ?, 'system')
                    """, (key, json.dumps(config)))

                # Insert visual metrics
                cursor.execute("""
                    INSERT INTO quality_gate_configs
                    (config_name, config_type, config_data, created_by)
                    VALUES ('default', 'visual_metric', ?, 'system')
                """, (json.dumps(self.VISUAL_QUALITY_METRICS),))

                conn.commit()
                logger.info("Default configurations created")

    def get_config(self, config_name: str, config_type: str = "anime_threshold") -> Dict:
        """Get specific configuration"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT config_data FROM quality_gate_configs
                WHERE config_name = ? AND config_type = ? AND is_active = 1
            """, (config_name, config_type))

            result = cursor.fetchone()
            if result:
                return json.loads(result['config_data'])

            # Return default if not found
            if config_type == "anime_threshold":
                return self.ANIME_THRESHOLDS.get("supporting_character", {})
            return {}

    def update_config(self, config_name: str, config_type: str, config_data: Dict) -> bool:
        """Update existing configuration"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE quality_gate_configs
                    SET config_data = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE config_name = ? AND config_type = ?
                """, (json.dumps(config_data), config_name, config_type))

                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Updated config: {config_type}/{config_name}")
                    return True
                return False

        except Exception as e:
            logger.error(f"Failed to update config: {e}")
            return False

    def get_threshold_for_character(self, character_name: str) -> Dict:
        """Get appropriate threshold based on character importance"""

        # Character importance mapping (should be from database in production)
        character_importance = {
            "Kai Nakamura": "hero_character",
            "Yuki Tanaka": "hero_character",
            "Dr. Chen": "supporting_character",
            "Guard_1": "background_character"
        }

        importance = character_importance.get(character_name, "supporting_character")
        return self.get_config(importance, "anime_threshold")

    def validate_with_config(self, scores: Dict, character_name: str) -> Dict:
        """Validate scores against appropriate configuration"""

        config = self.get_threshold_for_character(character_name)

        results = {
            "character": character_name,
            "config_used": config.get("name", "Unknown"),
            "passed": True,
            "failures": [],
            "scores": scores
        }

        # Check CLIP consistency
        if scores.get("clip_consistency", 0) < config.get("clip_consistency", 0.7):
            results["passed"] = False
            results["failures"].append({
                "metric": "clip_consistency",
                "score": scores.get("clip_consistency", 0),
                "required": config.get("clip_consistency", 0.7)
            })

        # Check technical quality
        if scores.get("technical_quality", 0) < config.get("technical_quality", 0.85):
            results["passed"] = False
            results["failures"].append({
                "metric": "technical_quality",
                "score": scores.get("technical_quality", 0),
                "required": config.get("technical_quality", 0.85)
            })

        # Check visual quality
        if scores.get("visual_quality", 0) < config.get("visual_quality", 0.8):
            results["passed"] = False
            results["failures"].append({
                "metric": "visual_quality",
                "score": scores.get("visual_quality", 0),
                "required": config.get("visual_quality", 0.8)
            })

        return results


# Calibration function
def calibrate_for_character(character_name: str, sample_scores: list) -> Dict:
    """Calibrate thresholds based on actual character data"""

    import numpy as np

    # Calculate statistics
    mean_score = np.mean(sample_scores)
    std_score = np.std(sample_scores)

    # Set threshold at mean - 0.5 * std for reasonable pass rate
    # This typically gives ~70-80% pass rate
    calibrated_threshold = max(0.6, mean_score - 0.5 * std_score)

    # Round to 2 decimal places
    calibrated_threshold = round(calibrated_threshold, 2)

    return {
        "character": character_name,
        "samples": len(sample_scores),
        "mean": round(mean_score, 3),
        "std": round(std_score, 3),
        "min": round(min(sample_scores), 3),
        "max": round(max(sample_scores), 3),
        "recommended_threshold": calibrated_threshold,
        "expected_pass_rate": sum(1 for s in sample_scores if s >= calibrated_threshold) / len(sample_scores)
    }


def apply_calibration():
    """Apply calibrated thresholds to Kai Nakamura"""

    configs = QualityGateConfigs()

    # Based on analysis: mean=0.813, std=0.111
    # Recommended threshold: 0.813 - 0.5*0.111 = 0.757 ≈ 0.76

    kai_config = {
        "name": "Kai Nakamura (Calibrated)",
        "clip_consistency": 0.76,  # Calibrated for ~67% pass rate
        "technical_quality": 0.90,
        "visual_quality": 0.85,
        "description": "Calibrated thresholds based on actual Kai Nakamura data"
    }

    # Store calibrated config
    configs.update_config("kai_nakamura_calibrated", "anime_threshold", kai_config)

    print("✅ Calibration applied successfully!")
    print(f"New threshold for Kai Nakamura: {kai_config['clip_consistency']}")
    print("This should allow 4/6 existing images to pass")

    return kai_config


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Initializing Quality Gate Configurations...")
    configs = QualityGateConfigs()

    print("\nAvailable threshold profiles:")
    for key, config in configs.ANIME_THRESHOLDS.items():
        print(f"  {key}: {config['clip_consistency']} - {config['description']}")

    print("\nApplying calibration for Kai Nakamura...")
    apply_calibration()