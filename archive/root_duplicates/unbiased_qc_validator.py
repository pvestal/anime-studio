#!/usr/bin/env python3
"""
Unbiased QC validator that first describes what it sees,
THEN compares to requirements (avoiding confirmation bias).
"""

import base64
import json
import logging
import requests
from typing import Dict, List, Tuple
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UnbiasedQCValidator:
    """Two-stage validation to avoid LLaVA confirmation bias."""

    def __init__(self):
        self.model = "llava:13b"
        self.ollama_url = "http://localhost:11434"

    def encode_image(self, image_path: str) -> str:
        """Encode image to base64."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def stage1_objective_description(self, image_path: str) -> Dict:
        """
        Stage 1: Get objective description WITHOUT telling LLaVA what we expect.
        This avoids confirmation bias.
        """

        if not Path(image_path).exists():
            return {"error": f"Image not found: {image_path}"}

        # DO NOT mention what we expect - just ask for description
        objective_prompt = """Describe this anime/manga character image in detail. Be specific about:

1. How many people are in the image? Count carefully.
2. What is the character's apparent gender?
3. What color is their hair? Be specific about the actual color you see.
4. What is their hairstyle (long, short, tied up, etc)?
5. What color are their eyes?
6. What are they wearing? Describe the outfit.
7. What is their expression or mood?
8. Are there any anatomical problems (extra limbs, missing parts, deformities)?
9. Any other notable features?

Provide your observations in JSON format:
{
  "people_count": <number>,
  "gender_observed": "<what you see>",
  "hair_color_observed": "<actual color you see>",
  "hair_style_observed": "<what you see>",
  "eye_color_observed": "<what you see>",
  "outfit_observed": "<what you see>",
  "expression_observed": "<what you see>",
  "anatomical_problems": ["<list any issues>"],
  "other_features": "<any other observations>"
}

Be completely honest about what you actually see, not what might be intended."""

        try:
            image_b64 = self.encode_image(image_path)

            payload = {
                "model": self.model,
                "prompt": objective_prompt,
                "images": [image_b64],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1,
                    "num_predict": 800
                }
            }

            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=30
            )

            if response.status_code != 200:
                return {"error": f"LLaVA request failed: {response.status_code}"}

            result = response.json()

            try:
                observations = json.loads(result.get('response', '{}'))
                return observations
            except json.JSONDecodeError:
                # Try to extract key info from raw response
                raw = result.get('response', '')
                return {
                    "raw_response": raw,
                    "parse_error": True
                }

        except Exception as e:
            return {"error": str(e)}

    def stage2_compare_requirements(self, observations: Dict, requirements: Dict) -> Dict:
        """
        Stage 2: Compare objective observations to requirements.
        This is where we check if it matches what we wanted.
        """

        mismatches = []
        score = 100

        # Check people count
        expected_count = requirements.get('people_count', 1)
        observed_count = observations.get('people_count', 0)
        if observed_count != expected_count:
            mismatches.append(f"People count: wanted {expected_count}, got {observed_count}")
            score -= 30

        # Check gender
        expected_gender = requirements.get('gender', '').lower()
        observed_gender = observations.get('gender_observed', '').lower()
        if expected_gender and expected_gender not in observed_gender:
            mismatches.append(f"Gender: wanted {expected_gender}, got {observed_gender}")
            score -= 20

        # Check hair color (CRITICAL CHECK)
        expected_hair = requirements.get('hair_color', '').lower()
        observed_hair = observations.get('hair_color_observed', '').lower()

        # Be strict about color matching
        hair_match = False
        if expected_hair:
            # Check for specific color words
            if 'dark' in expected_hair or 'black' in expected_hair:
                hair_match = ('dark' in observed_hair or 'black' in observed_hair) and 'red' not in observed_hair
            elif 'pink' in expected_hair:
                hair_match = 'pink' in observed_hair
            elif 'silver' in expected_hair or 'white' in expected_hair:
                hair_match = 'silver' in observed_hair or 'white' in observed_hair
            else:
                hair_match = expected_hair in observed_hair

        if not hair_match and expected_hair:
            mismatches.append(f"Hair color: wanted {expected_hair}, got {observed_hair}")
            score -= 25

        # Check anatomical issues
        anatomical_problems = observations.get('anatomical_problems', [])
        if anatomical_problems and len(anatomical_problems) > 0:
            if anatomical_problems[0].lower() not in ['none', 'no issues', '']:
                mismatches.append(f"Anatomical issues: {', '.join(anatomical_problems)}")
                score -= 30

        # Check outfit if specified
        expected_outfit = requirements.get('outfit', '').lower()
        observed_outfit = observations.get('outfit_observed', '').lower()
        if expected_outfit:
            key_words = expected_outfit.split()
            matches = sum(1 for word in key_words if word in observed_outfit)
            if matches < len(key_words) / 2:
                mismatches.append(f"Outfit: wanted '{expected_outfit}', got '{observed_outfit}'")
                score -= 15

        return {
            "score": max(0, score),
            "passed": score >= 70 and len(mismatches) == 0,
            "mismatches": mismatches,
            "observations": observations,
            "requirements": requirements
        }

    def validate_image(self, image_path: str, requirements: Dict) -> Dict:
        """
        Full two-stage validation process.
        """

        logger.info(f"🔍 Stage 1: Getting objective description of {Path(image_path).name}")

        # Stage 1: Get unbiased description
        observations = self.stage1_objective_description(image_path)

        if "error" in observations:
            return {
                "valid": False,
                "error": observations["error"],
                "stage_failed": 1
            }

        logger.info(f"📊 Stage 2: Comparing observations to requirements")

        # Stage 2: Compare to requirements
        comparison = self.stage2_compare_requirements(observations, requirements)

        return {
            "valid": comparison["passed"],
            "score": comparison["score"],
            "observations": observations,
            "requirements": requirements,
            "mismatches": comparison["mismatches"],
            "recommendation": "PASS" if comparison["passed"] else "REGENERATE"
        }


def test_unbiased_validation():
    """Test the unbiased validator on generated images."""

    validator = UnbiasedQCValidator()

    print("\n🔬 UNBIASED QUALITY CONTROL TESTING")
    print("=" * 70)
    print("Two-stage validation to avoid confirmation bias")
    print("-" * 70)

    # Test cases with requirements
    test_cases = [
        {
            "name": "Female Kai Nakamura",
            "image": "/mnt/1TB-storage/ComfyUI/output/female_kai_1764634362_00001_.png",
            "requirements": {
                "people_count": 1,
                "gender": "female",
                "hair_color": "dark black",  # What we WANTED
                "outfit": "military uniform"
            }
        },
        {
            "name": "Sakura Tanaka",
            "image": "/mnt/1TB-storage/ComfyUI/output/sakura_1764634397_00001_.png",
            "requirements": {
                "people_count": 1,
                "gender": "female",
                "hair_color": "pink",
                "outfit": "school uniform"
            }
        },
        {
            "name": "Hiroshi Yamamoto",
            "image": "/mnt/1TB-storage/ComfyUI/output/hiroshi_1764634381_00001_.png",
            "requirements": {
                "people_count": 1,
                "gender": "male",
                "hair_color": "silver white",
                "outfit": "lab coat"
            }
        }
    ]

    results = []

    for test in test_cases:
        print(f"\n📸 Testing: {test['name']}")
        print(f"   File: {Path(test['image']).name}")

        if not Path(test['image']).exists():
            print("   ❌ File not found")
            continue

        result = validator.validate_image(test['image'], test['requirements'])

        print(f"\n   Stage 1 - Objective Observations:")
        obs = result.get('observations', {})
        print(f"   • People count: {obs.get('people_count', '?')}")
        print(f"   • Gender seen: {obs.get('gender_observed', '?')}")
        print(f"   • Hair color seen: {obs.get('hair_color_observed', '?')}")
        print(f"   • Outfit seen: {obs.get('outfit_observed', '?')}")

        print(f"\n   Stage 2 - Requirement Comparison:")
        print(f"   • Score: {result.get('score', 0)}/100")
        print(f"   • Valid: {'✅ YES' if result['valid'] else '❌ NO'}")

        if result.get('mismatches'):
            print(f"\n   ⚠️ MISMATCHES FOUND:")
            for mismatch in result['mismatches']:
                print(f"      - {mismatch}")

        print(f"\n   📋 Recommendation: {result.get('recommendation', '?')}")
        print("-" * 70)

        results.append({
            "name": test['name'],
            "valid": result['valid'],
            "score": result.get('score', 0)
        })

    # Summary
    print("\n📊 VALIDATION SUMMARY")
    print("=" * 70)

    for r in results:
        status = "✅" if r['valid'] else "❌"
        print(f"{status} {r['name']}: {r['score']}/100")

    passed = sum(1 for r in results if r['valid'])
    total = len(results)

    print(f"\n🎯 Overall: {passed}/{total} passed")
    print("=" * 70)


if __name__ == "__main__":
    test_unbiased_validation()