#!/usr/bin/env python3
"""
Quality Gates System for Anime Production
Configurable validation pipeline with multiple tiers and flexible thresholds
"""

import os
import json
import sqlite3
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from PIL import Image, ImageStat
import numpy as np
from datetime import datetime

from clip_consistency import CLIPCharacterConsistency, analyze_character_consistency_clip

logger = logging.getLogger(__name__)

class QualityGateValidator:
    """Production-grade quality gate validation system"""

    def __init__(self, db_path: str = "/opt/tower-anime-production/database/anime_production.db"):
        self.db_path = db_path
        self.clip_checker = None  # Lazy initialization

    def _get_db_connection(self):
        """Get database connection with proper configuration"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_clip_checker(self, clip_model: str = "ViT-B/32"):
        """Initialize CLIP checker if not already done"""
        if self.clip_checker is None:
            self.clip_checker = CLIPCharacterConsistency(
                db_path=self.db_path,
                clip_model=clip_model
            )

    def get_quality_gate_config(self, config_name: str = "default_production") -> Dict:
        """Get quality gate configuration from database"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT * FROM quality_gate_configs
                    WHERE config_name = ? AND is_active = 1
                """, (config_name,))

                config = cursor.fetchone()
                if not config:
                    logger.warning(f"Config {config_name} not found, using defaults")
                    return self._get_default_config()

                # Parse JSON fields
                result = dict(config)
                for json_field in ['min_resolution', 'allowed_formats']:
                    if result[json_field]:
                        result[json_field] = json.loads(result[json_field])

                return result

        except Exception as e:
            logger.error(f"Failed to get quality gate config: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Get default quality gate configuration"""
        return {
            "config_name": "default_fallback",
            "min_resolution": {"width": 512, "height": 512},
            "max_file_size": 10485760,  # 10MB
            "allowed_formats": ["png", "jpg", "jpeg", "webp"],
            "min_technical_quality": 0.7,
            "min_visual_quality": 0.6,
            "min_character_consistency": 0.75,
            "min_style_consistency": 0.65,
            "clip_model": "ViT-B/32",
            "character_similarity_threshold": 0.8,
            "require_manual_review": False,
            "auto_fail_on_threshold": True
        }

    async def validate_technical_quality(self, image_path: str, config: Dict) -> Dict:
        """Tier 1: Basic technical validation (file format, resolution, corruption)"""
        try:
            result = {
                "gate_name": "technical_quality",
                "passed": True,
                "score": 1.0,
                "threshold": config.get("min_technical_quality", 0.7),
                "details": {}
            }

            # Check file exists and is readable
            if not os.path.exists(image_path):
                result.update({
                    "passed": False,
                    "score": 0.0,
                    "details": {"error": "File does not exist"}
                })
                return result

            # Check file size
            file_size = os.path.getsize(image_path)
            max_size = config.get("max_file_size", 10485760)

            if file_size > max_size:
                result.update({
                    "passed": False,
                    "score": 0.0,
                    "details": {"error": f"File too large: {file_size} > {max_size}"}
                })
                return result

            result["details"]["file_size"] = file_size

            # Check file format and process image
            with Image.open(image_path) as img:
                format_ext = img.format.lower() if img.format else "unknown"
                allowed_formats = config.get("allowed_formats", ["png", "jpg", "jpeg"])

                if format_ext not in [fmt.lower() for fmt in allowed_formats]:
                    result.update({
                        "passed": False,
                        "score": 0.0,
                        "details": {"error": f"Invalid format: {format_ext}"}
                    })
                    return result

                # Check resolution
                min_res = config.get("min_resolution", {"width": 512, "height": 512})
                if img.width < min_res["width"] or img.height < min_res["height"]:
                    result.update({
                        "passed": False,
                        "score": 0.0,
                        "details": {
                            "error": f"Resolution too low: {img.width}x{img.height} < {min_res['width']}x{min_res['height']}"
                        }
                    })
                    return result

                result["details"].update({
                    "format": format_ext,
                    "resolution": {"width": img.width, "height": img.height},
                    "mode": img.mode,
                    "has_transparency": img.mode in ("RGBA", "LA") or "transparency" in img.info
                })

                # Basic corruption check - try to load image data
                try:
                    _ = np.array(img)
                    result["details"]["corruption_check"] = "passed"
                except Exception as e:
                    result.update({
                        "passed": False,
                        "score": 0.0,
                        "details": {"error": f"Image corruption detected: {e}"}
                    })
                    return result

                # Calculate technical quality score
                tech_score = 1.0

                # Penalize very large files
                if file_size > max_size * 0.8:
                    tech_score *= 0.9

                # Bonus for high resolution
                if img.width >= 1024 and img.height >= 1024:
                    tech_score *= 1.1

                result["score"] = min(1.0, tech_score)
                result["passed"] = result["score"] >= result["threshold"]

            return result

        except Exception as e:
            logger.error(f"Technical quality validation failed: {e}")
            return {
                "gate_name": "technical_quality",
                "passed": False,
                "score": 0.0,
                "details": {"error": str(e)}
            }

    async def validate_visual_quality(self, image_path: str, config: Dict) -> Dict:
        """Tier 2: Visual quality assessment (composition, clarity, aesthetics)"""
        try:
            result = {
                "gate_name": "visual_quality",
                "passed": True,
                "score": 0.0,
                "threshold": config.get("min_visual_quality", 0.6),
                "details": {}
            }

            with Image.open(image_path) as img:
                # Convert to RGB for analysis
                if img.mode != "RGB":
                    img = img.convert("RGB")

                img_array = np.array(img)

                # 1. Brightness and contrast analysis
                brightness = np.mean(img_array) / 255.0
                contrast = np.std(img_array) / 255.0

                # 2. Color distribution
                color_variance = np.var(img_array, axis=(0, 1)).mean() / (255.0 ** 2)

                # 3. Edge sharpness (simple gradient-based)
                gray = np.dot(img_array[..., :3], [0.2989, 0.5870, 0.1140])
                grad_x = np.gradient(gray, axis=1)
                grad_y = np.gradient(gray, axis=0)
                sharpness = np.mean(np.sqrt(grad_x**2 + grad_y**2))

                # 4. Saturation analysis
                hsv_img = img.convert("HSV")
                hsv_array = np.array(hsv_img)
                saturation = np.mean(hsv_array[:, :, 1]) / 255.0

                # Calculate composite visual quality score
                scores = {
                    "brightness": self._score_brightness(brightness),
                    "contrast": self._score_contrast(contrast),
                    "color_variance": self._score_color_variance(color_variance),
                    "sharpness": self._score_sharpness(sharpness),
                    "saturation": self._score_saturation(saturation)
                }

                # Weighted average
                weights = {
                    "brightness": 0.15,
                    "contrast": 0.25,
                    "color_variance": 0.20,
                    "sharpness": 0.25,
                    "saturation": 0.15
                }

                visual_score = sum(scores[key] * weights[key] for key in scores)

                result.update({
                    "score": visual_score,
                    "passed": visual_score >= result["threshold"],
                    "details": {
                        "brightness": brightness,
                        "contrast": contrast,
                        "color_variance": color_variance,
                        "sharpness": sharpness,
                        "saturation": saturation,
                        "component_scores": scores,
                        "weights": weights
                    }
                })

            return result

        except Exception as e:
            logger.error(f"Visual quality validation failed: {e}")
            return {
                "gate_name": "visual_quality",
                "passed": False,
                "score": 0.0,
                "details": {"error": str(e)}
            }

    def _score_brightness(self, brightness: float) -> float:
        """Score brightness (0-1, optimal around 0.3-0.7)"""
        if 0.3 <= brightness <= 0.7:
            return 1.0
        elif 0.1 <= brightness < 0.3:
            return 0.5 + (brightness - 0.1) * 2.5
        elif 0.7 < brightness <= 0.9:
            return 1.0 - (brightness - 0.7) * 2.5
        else:
            return 0.1

    def _score_contrast(self, contrast: float) -> float:
        """Score contrast (0-1, higher contrast generally better for anime)"""
        if contrast >= 0.3:
            return 1.0
        elif contrast >= 0.15:
            return contrast / 0.3
        else:
            return 0.1

    def _score_color_variance(self, variance: float) -> float:
        """Score color variance (0-1, moderate variance preferred)"""
        if 0.1 <= variance <= 0.4:
            return 1.0
        elif variance < 0.1:
            return variance * 10
        else:
            return max(0.1, 1.0 - (variance - 0.4) * 2)

    def _score_sharpness(self, sharpness: float) -> float:
        """Score sharpness based on gradient magnitude"""
        if sharpness >= 50:
            return 1.0
        elif sharpness >= 10:
            return 0.3 + (sharpness / 50) * 0.7
        else:
            return 0.1

    def _score_saturation(self, saturation: float) -> float:
        """Score saturation (anime typically has good saturation)"""
        if 0.4 <= saturation <= 0.8:
            return 1.0
        elif 0.2 <= saturation < 0.4:
            return saturation / 0.4
        elif 0.8 < saturation <= 1.0:
            return 1.0 - (saturation - 0.8) * 2.5
        else:
            return 0.1

    async def validate_character_consistency(self, image_path: str, character_name: str, config: Dict) -> Dict:
        """Tier 3: CLIP-based character consistency validation"""
        try:
            # Initialize CLIP checker
            self._init_clip_checker(config.get("clip_model", "ViT-B/32"))

            # Run CLIP consistency analysis
            clip_result = await analyze_character_consistency_clip(
                image_path,
                character_name,
                clip_model=config.get("clip_model", "ViT-B/32"),
                consistency_threshold=config.get("character_similarity_threshold", 0.8),
                auto_add_reference=True
            )

            consistency_score = clip_result.get("consistency_score", 0.0)
            threshold = config.get("min_character_consistency", 0.75)

            result = {
                "gate_name": "character_consistency",
                "passed": consistency_score >= threshold,
                "score": consistency_score,
                "threshold": threshold,
                "details": {
                    "reference_count": clip_result.get("reference_count", 0),
                    "method": clip_result.get("method", "unknown"),
                    "is_first_reference": clip_result.get("is_first_reference", False),
                    "added_as_reference": clip_result.get("added_as_reference", False),
                    "best_match_score": clip_result.get("best_match", {}).get("similarity", None),
                    "clip_model": config.get("clip_model", "ViT-B/32")
                }
            }

            if "error" in clip_result:
                result.update({
                    "passed": False,
                    "score": 0.0,
                    "details": {"error": clip_result["error"]}
                })

            return result

        except Exception as e:
            logger.error(f"Character consistency validation failed: {e}")
            return {
                "gate_name": "character_consistency",
                "passed": False,
                "score": 0.0,
                "details": {"error": str(e)}
            }

    async def validate_style_consistency(self, image_path: str, config: Dict) -> Dict:
        """Tier 4: Style consistency validation (placeholder for future enhancement)"""
        return {
            "gate_name": "style_consistency",
            "passed": True,
            "score": 0.8,
            "threshold": config.get("min_style_consistency", 0.65),
            "details": {"implementation": "placeholder"}
        }

    async def run_quality_gates(self, image_path: str, character_name: str,
                              config_name: str = "default_production") -> Dict:
        """Run complete quality gate pipeline"""
        start_time = datetime.now()

        try:
            config = self.get_quality_gate_config(config_name)

            # Store initial asset metadata
            asset_id = -1
            try:
                self._init_clip_checker(config.get("clip_model", "ViT-B/32"))
                asset_id = self.clip_checker.store_asset_metadata(image_path, character_name)
            except Exception as e:
                logger.warning(f"Failed to store asset metadata: {e}")

            # Run validation gates
            gate_results = []

            # Tier 1: Technical Quality
            tech_result = await self.validate_technical_quality(image_path, config)
            gate_results.append(tech_result)

            # Tier 2: Visual Quality (only if technical passes)
            if tech_result["passed"]:
                visual_result = await self.validate_visual_quality(image_path, config)
                gate_results.append(visual_result)

                # Tier 3: Character Consistency (only if visual passes)
                if visual_result["passed"]:
                    char_result = await self.validate_character_consistency(
                        image_path, character_name, config
                    )
                    gate_results.append(char_result)

                    # Tier 4: Style Consistency (only if character passes)
                    if char_result["passed"]:
                        style_result = await self.validate_style_consistency(image_path, config)
                        gate_results.append(style_result)

            # Calculate overall results
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            overall_passed = all(result["passed"] for result in gate_results)
            overall_score = np.mean([result["score"] for result in gate_results])

            # Determine final status
            if config.get("require_manual_review", False) and overall_passed:
                final_status = "manual_review"
            elif overall_passed:
                final_status = "passed"
            else:
                final_status = "failed"

            pipeline_result = {
                "asset_id": asset_id,
                "image_path": image_path,
                "character_name": character_name,
                "config_name": config_name,
                "overall_status": final_status,
                "overall_passed": overall_passed,
                "overall_score": float(overall_score),
                "gate_results": gate_results,
                "gates_executed": len(gate_results),
                "execution_time_ms": int(execution_time),
                "timestamp": start_time.isoformat(),
                "config_used": config
            }

            # Store results in database
            await self._store_quality_gate_results(pipeline_result, config)

            return pipeline_result

        except Exception as e:
            logger.error(f"Quality gate pipeline failed: {e}")
            return {
                "error": str(e),
                "execution_time_ms": int((datetime.now() - start_time).total_seconds() * 1000)
            }

    async def _store_quality_gate_results(self, pipeline_result: Dict, config: Dict):
        """Store quality gate results in database"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                # Get or create config ID
                cursor.execute("""
                    SELECT id FROM quality_gate_configs WHERE config_name = ?
                """, (pipeline_result["config_name"],))

                config_row = cursor.fetchone()
                config_id = config_row["id"] if config_row else 1

                # Store individual gate results
                for gate_result in pipeline_result.get("gate_results", []):
                    cursor.execute("""
                        INSERT INTO quality_gate_results (
                            asset_id, config_id, gate_name, passed, score,
                            threshold, details, execution_time_ms
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        pipeline_result.get("asset_id"),
                        config_id,
                        gate_result["gate_name"],
                        int(gate_result["passed"]),  # Convert bool to int
                        gate_result["score"],
                        gate_result.get("threshold"),
                        json.dumps(gate_result.get("details", {}), default=str),  # Handle any non-serializable objects
                        pipeline_result.get("execution_time_ms", 0)
                    ))

                # Update asset metadata with final status
                if pipeline_result.get("asset_id", -1) != -1:
                    cursor.execute("""
                        UPDATE asset_metadata
                        SET quality_gate_status = ?,
                            character_consistency_score = ?,
                            technical_quality_score = ?,
                            visual_quality_score = ?,
                            quality_gate_results = ?,
                            last_validated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (
                        pipeline_result["overall_status"],
                        self._get_gate_score(pipeline_result, "character_consistency"),
                        self._get_gate_score(pipeline_result, "technical_quality"),
                        self._get_gate_score(pipeline_result, "visual_quality"),
                        json.dumps(pipeline_result, default=str),
                        pipeline_result["asset_id"]
                    ))

        except Exception as e:
            logger.error(f"Failed to store quality gate results: {e}")

    def _get_gate_score(self, pipeline_result: Dict, gate_name: str) -> Optional[float]:
        """Extract score for specific gate from pipeline results"""
        for gate in pipeline_result.get("gate_results", []):
            if gate.get("gate_name") == gate_name:
                return gate.get("score")
        return None


# Convenience functions for API integration
async def validate_anime_asset(
    image_path: str,
    character_name: str,
    config_name: str = "default_production"
) -> Dict:
    """Validate anime asset through complete quality gate pipeline"""
    validator = QualityGateValidator()
    return await validator.run_quality_gates(image_path, character_name, config_name)


async def quick_character_check(image_path: str, character_name: str,
                              threshold: float = 0.8) -> bool:
    """Quick character consistency check"""
    validator = QualityGateValidator()
    config = validator.get_quality_gate_config()
    config["min_character_consistency"] = threshold
    result = await validator.validate_character_consistency(image_path, character_name, config)
    return result.get("passed", False)


# Test function
async def test_quality_gates():
    """Test quality gates with existing images"""
    import glob

    test_images = glob.glob("/mnt/1TB-storage/ComfyUI/output/anime_*.png")[:3]

    if not test_images:
        print("No test images found")
        return

    print(f"Testing quality gates with {len(test_images)} images")

    for i, image_path in enumerate(test_images):
        print(f"\n--- Testing image {i+1}: {Path(image_path).name} ---")

        result = await validate_anime_asset(
            image_path,
            "test_character",
            "default_production"
        )

        print(f"Overall Status: {result.get('overall_status', 'N/A')}")
        print(f"Overall Score: {result.get('overall_score', 0):.3f}")
        print(f"Gates Executed: {result.get('gates_executed', 0)}")
        print(f"Execution Time: {result.get('execution_time_ms', 0)}ms")

        for gate in result.get("gate_results", []):
            print(f"  {gate['gate_name']}: {gate['passed']} (score: {gate['score']:.3f})")


if __name__ == "__main__":
    asyncio.run(test_quality_gates())