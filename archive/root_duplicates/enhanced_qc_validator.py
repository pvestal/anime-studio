#!/usr/bin/env python3
"""
Enhanced QC validator that checks both anatomy AND attribute matching.
"""

import base64
import json
import logging
import requests
from typing import Dict, List
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnhancedQCValidator:
    """Comprehensive quality control for generated images."""

    def __init__(self):
        self.model = "llava:13b"
        self.ollama_url = "http://localhost:11434"

    def encode_image(self, image_path: str) -> str:
        """Encode image to base64."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def comprehensive_check(self, image_path: str, expected_attributes: Dict) -> Dict:
        """
        Perform comprehensive quality check including:
        - Anatomical correctness
        - Attribute matching
        - Style consistency
        - Technical quality
        """

        if not Path(image_path).exists():
            return {
                "valid": False,
                "error": f"Image not found: {image_path}",
                "score": 0
            }

        # Build comprehensive check prompt
        prompt = f"""You are a strict quality control inspector for anime art. Analyze this image and check:

EXPECTED ATTRIBUTES:
- Character: {expected_attributes.get('character', 'Unknown')}
- Gender: {expected_attributes.get('gender', 'Unknown')}
- Hair Color: {expected_attributes.get('hair_color', 'Unknown')}
- Hair Style: {expected_attributes.get('hair_style', 'Unknown')}
- Eye Color: {expected_attributes.get('eye_color', 'Unknown')}
- Outfit: {expected_attributes.get('outfit', 'Unknown')}
- Expression: {expected_attributes.get('expression', 'Unknown')}

CRITICAL CHECKS:
1. Subject Count: How many people/characters are visible?
2. Gender Match: Does the character's gender match the expected?
3. Hair Match: Is the hair color and style correct?
4. Anatomical Issues: Any extra/missing body parts, deformities?
5. Outfit Match: Does the clothing match the description?
6. Overall Quality: Is the image clear, properly rendered?

Respond in JSON format:
{{
  "subject_count": <number>,
  "gender_detected": "<detected gender>",
  "gender_match": <true/false>,
  "hair_color_detected": "<detected color>",
  "hair_color_match": <true/false>,
  "hair_style_detected": "<detected style>",
  "hair_style_match": <true/false>,
  "outfit_detected": "<detected outfit>",
  "outfit_match": <true/false>,
  "anatomical_issues": ["<list any issues>"],
  "quality_issues": ["<list any rendering issues>"],
  "overall_score": <0-100>,
  "recommendation": "<pass/fail/regenerate>",
  "detailed_analysis": "<detailed description>"
}}"""

        try:
            image_b64 = self.encode_image(image_path)

            payload = {
                "model": self.model,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1,
                    "num_predict": 1000
                }
            }

            logger.info(f"🔍 Performing comprehensive QC on: {image_path}")

            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=45
            )

            if response.status_code != 200:
                return {
                    "valid": False,
                    "error": f"LLaVA request failed: {response.status_code}",
                    "score": 0
                }

            result = response.json()

            try:
                analysis = json.loads(result.get('response', '{}'))
            except json.JSONDecodeError:
                # Fallback if response isn't valid JSON
                analysis = {
                    "overall_score": 0,
                    "recommendation": "fail",
                    "detailed_analysis": result.get('response', 'Parse error')
                }

            # Determine validity based on comprehensive criteria
            is_valid = (
                analysis.get('subject_count', 0) == expected_attributes.get('expected_count', 1) and
                analysis.get('gender_match', False) and
                analysis.get('hair_color_match', False) and
                len(analysis.get('anatomical_issues', [])) == 0 and
                analysis.get('overall_score', 0) >= 70
            )

            return {
                "valid": is_valid,
                "score": analysis.get('overall_score', 0),
                "analysis": analysis,
                "recommendation": analysis.get('recommendation', 'unknown'),
                "issues": {
                    "anatomical": analysis.get('anatomical_issues', []),
                    "quality": analysis.get('quality_issues', []),
                    "attribute_mismatches": self._get_mismatches(analysis)
                }
            }

        except Exception as e:
            logger.error(f"Enhanced QC error: {e}")
            return {
                "valid": False,
                "error": str(e),
                "score": 0
            }

    def _get_mismatches(self, analysis: Dict) -> List[str]:
        """Extract attribute mismatches from analysis."""
        mismatches = []

        if not analysis.get('gender_match', True):
            mismatches.append(f"Gender: expected vs {analysis.get('gender_detected', 'unknown')}")

        if not analysis.get('hair_color_match', True):
            mismatches.append(f"Hair color: expected vs {analysis.get('hair_color_detected', 'unknown')}")

        if not analysis.get('hair_style_match', True):
            mismatches.append(f"Hair style: expected vs {analysis.get('hair_style_detected', 'unknown')}")

        if not analysis.get('outfit_match', True):
            mismatches.append(f"Outfit: expected vs {analysis.get('outfit_detected', 'unknown')}")

        return mismatches


def test_enhanced_qc():
    """Test the enhanced QC on recent generations."""

    validator = EnhancedQCValidator()

    # Define expected attributes for each character
    test_cases = [
        {
            "image": "/mnt/1TB-storage/ComfyUI/output/female_kai_1764634362_00001_.png",
            "attributes": {
                "character": "Kai Nakamura",
                "gender": "female",
                "hair_color": "dark/black",
                "hair_style": "long flowing",
                "eye_color": "dark",
                "outfit": "military uniform with red accents",
                "expression": "serious",
                "expected_count": 1
            }
        },
        {
            "image": "/mnt/1TB-storage/ComfyUI/output/sakura_1764634397_00001_.png",
            "attributes": {
                "character": "Sakura Tanaka",
                "gender": "female",
                "hair_color": "pink",
                "hair_style": "twin tails",
                "eye_color": "bright",
                "outfit": "school uniform",
                "expression": "cheerful",
                "expected_count": 1
            }
        },
        {
            "image": "/mnt/1TB-storage/ComfyUI/output/hiroshi_1764634381_00001_.png",
            "attributes": {
                "character": "Hiroshi Yamamoto",
                "gender": "male",
                "hair_color": "silver/white",
                "hair_style": "neat",
                "eye_color": "behind glasses",
                "outfit": "lab coat over dark clothes",
                "expression": "calm/intelligent",
                "expected_count": 1
            }
        }
    ]

    print("\n🔍 Enhanced Quality Control Testing")
    print("=" * 70)

    all_passed = True

    for test in test_cases:
        if not Path(test["image"]).exists():
            print(f"\n❌ Image not found: {test['image']}")
            continue

        print(f"\n📸 Checking: {test['attributes']['character']}")
        print(f"   File: {Path(test['image']).name}")
        print("-" * 50)

        result = validator.comprehensive_check(test["image"], test["attributes"])

        # Display results
        status = "✅ PASS" if result["valid"] else "❌ FAIL"
        print(f"   Status: {status}")
        print(f"   Score: {result.get('score', 0)}/100")
        print(f"   Recommendation: {result.get('recommendation', 'unknown')}")

        if result.get("analysis"):
            analysis = result["analysis"]
            print(f"\n   Detected Attributes:")
            print(f"   - Gender: {analysis.get('gender_detected', 'unknown')}", end="")
            print(f" {'✓' if analysis.get('gender_match') else '✗'}")
            print(f"   - Hair Color: {analysis.get('hair_color_detected', 'unknown')}", end="")
            print(f" {'✓' if analysis.get('hair_color_match') else '✗'}")
            print(f"   - Hair Style: {analysis.get('hair_style_detected', 'unknown')}", end="")
            print(f" {'✓' if analysis.get('hair_style_match') else '✗'}")
            print(f"   - Outfit: {analysis.get('outfit_detected', 'unknown')}", end="")
            print(f" {'✓' if analysis.get('outfit_match') else '✗'}")
            print(f"   - Subject Count: {analysis.get('subject_count', 'unknown')}")

        if result.get("issues"):
            issues = result["issues"]
            if issues.get("attribute_mismatches"):
                print(f"\n   ⚠️ Attribute Mismatches:")
                for mismatch in issues["attribute_mismatches"]:
                    print(f"      - {mismatch}")

            if issues.get("anatomical"):
                print(f"\n   ⚠️ Anatomical Issues:")
                for issue in issues["anatomical"]:
                    print(f"      - {issue}")

            if issues.get("quality"):
                print(f"\n   ⚠️ Quality Issues:")
                for issue in issues["quality"]:
                    print(f"      - {issue}")

        if not result["valid"]:
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("✅ All characters passed enhanced QC")
    else:
        print("❌ Some characters failed enhanced QC - regeneration needed")

    return all_passed


if __name__ == "__main__":
    test_enhanced_qc()