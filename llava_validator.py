#!/usr/bin/env python3
"""
LLaVA-based image validator for anime production quality control.
Validates anatomical correctness and subject count using vision models.
"""

import base64
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLaVAValidator:
    """Validates generated images using LLaVA vision model."""

    def __init__(self):
        self.model = "llava:13b"
        self.ollama_url = "http://localhost:11434"

    def encode_image(self, image_path: str) -> str:
        """Encode image to base64 for LLaVA analysis."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def analyze_image(self, image_path: str, expected_subject_count: int = 1) -> Dict:
        """
        Analyze image for quality issues using LLaVA.

        Returns:
            Dict with validation results including:
            - valid: bool (whether image passes QC)
            - subject_count: int (detected number of people)
            - anatomical_issues: List[str] (any detected issues)
            - confidence: float (0-1 confidence score)
            - details: str (full analysis)
        """
        if not Path(image_path).exists():
            return {
                "valid": False,
                "error": f"Image not found: {image_path}",
                "subject_count": 0,
                "anatomical_issues": ["Image file missing"],
                "confidence": 0.0
            }

        # Critical validation prompt focusing on anatomical correctness
        validation_prompt = f"""You are a quality control specialist for anime/manga artwork. Analyze this image and answer these specific questions:

1. How many distinct human figures/characters are visible in this image? (Count carefully)
2. Does each character have the correct number of body parts? Check for:
   - Head count (should be 1 per character)
   - Arm count (should be 2 per character)
   - Leg/feet count (should be 2 per character)
   - Hand count (should be 2 per character)
3. Are there any anatomical abnormalities like extra limbs, merged bodies, or missing parts?
4. Rate your confidence in this analysis from 0.0 to 1.0

Expected: {expected_subject_count} character(s)

Respond in JSON format:
{{
  "subject_count": <number>,
  "expected_count_match": <true/false>,
  "anatomical_issues": [<list any issues found>],
  "body_part_count": {{
    "heads": <number>,
    "arms": <number>,
    "legs": <number>,
    "hands": <number>
  }},
  "confidence": <0.0-1.0>,
  "analysis": "<brief description>"
}}"""

        try:
            # Prepare the request for Ollama's LLaVA
            image_b64 = self.encode_image(image_path)

            payload = {
                "model": self.model,
                "prompt": validation_prompt,
                "images": [image_b64],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1,  # Low temperature for consistent analysis
                    "num_predict": 500
                }
            }

            logger.info(f"🔍 Analyzing image with LLaVA: {image_path}")

            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"LLaVA request failed: {response.status_code}")
                return {
                    "valid": False,
                    "error": f"LLaVA analysis failed: {response.status_code}",
                    "subject_count": 0,
                    "anatomical_issues": ["Analysis failed"],
                    "confidence": 0.0
                }

            result = response.json()

            # Parse the JSON response from LLaVA
            try:
                analysis = json.loads(result.get('response', '{}'))
            except json.JSONDecodeError:
                # Fallback parsing if response isn't valid JSON
                analysis = {
                    "subject_count": 0,
                    "anatomical_issues": ["Failed to parse analysis"],
                    "confidence": 0.0,
                    "analysis": result.get('response', 'No response')
                }

            # Determine if image is valid based on analysis
            is_valid = (
                analysis.get('subject_count', 0) == expected_subject_count and
                len(analysis.get('anatomical_issues', [])) == 0 and
                analysis.get('confidence', 0) >= 0.7
            )

            # Check body part counts if provided
            if 'body_part_count' in analysis:
                parts = analysis['body_part_count']
                expected_parts = expected_subject_count * 2  # For arms, legs, hands
                expected_heads = expected_subject_count

                if parts.get('heads', 0) != expected_heads:
                    is_valid = False
                    analysis['anatomical_issues'].append(f"Head count mismatch: {parts.get('heads', 0)} found, {expected_heads} expected")

                for part in ['arms', 'legs', 'hands']:
                    if parts.get(part, 0) != expected_parts:
                        is_valid = False
                        analysis['anatomical_issues'].append(f"{part.capitalize()} count mismatch: {parts.get(part, 0)} found, {expected_parts} expected")

            return {
                "valid": is_valid,
                "subject_count": analysis.get('subject_count', 0),
                "anatomical_issues": analysis.get('anatomical_issues', []),
                "confidence": analysis.get('confidence', 0.0),
                "details": analysis.get('analysis', ''),
                "body_parts": analysis.get('body_part_count', {}),
                "expected_match": analysis.get('expected_count_match', False)
            }

        except Exception as e:
            logger.error(f"LLaVA validation error: {e}")
            return {
                "valid": False,
                "error": str(e),
                "subject_count": 0,
                "anatomical_issues": [f"Validation error: {str(e)}"],
                "confidence": 0.0
            }

    def validate_portrait(self, image_path: str) -> Dict:
        """Validate a portrait (should have exactly 1 subject)."""
        return self.analyze_image(image_path, expected_subject_count=1)

    def validate_group(self, image_path: str, expected_count: int) -> Dict:
        """Validate a group image with specific subject count."""
        return self.analyze_image(image_path, expected_subject_count=expected_count)


def test_validator():
    """Test the validator with recent generated images."""
    validator = LLaVAValidator()

    # Find recent generated images to test
    output_dir = Path("/mnt/1TB-storage/ComfyUI/output/")
    recent_images = sorted(
        [f for f in output_dir.glob("style_enhanced_*.png")],
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )[:3]  # Get 3 most recent

    if not recent_images:
        logger.warning("No recent images found to validate")
        return

    print("\n🔍 Testing LLaVA Validator on Recent Images")
    print("=" * 60)

    for img_path in recent_images:
        print(f"\n📸 Analyzing: {img_path.name}")
        result = validator.validate_portrait(str(img_path))

        print(f"  Valid: {'✅' if result['valid'] else '❌'}")
        print(f"  Subject Count: {result['subject_count']} (expected: 1)")
        print(f"  Confidence: {result.get('confidence', 0):.2%}")

        if result.get('anatomical_issues'):
            print(f"  Issues Found:")
            for issue in result['anatomical_issues']:
                print(f"    - {issue}")

        if result.get('body_parts'):
            print(f"  Body Part Counts:")
            for part, count in result['body_parts'].items():
                expected = 1 if part == 'heads' else 2
                status = "✓" if count == expected else "✗"
                print(f"    - {part}: {count} {status}")

        if result.get('details'):
            print(f"  Analysis: {result['details']}")

        print("-" * 40)


if __name__ == "__main__":
    test_validator()