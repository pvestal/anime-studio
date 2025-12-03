#!/usr/bin/env python3
"""
Echo Brain orchestrator for anime production with proper QC.
Manages character generation, validation, and versioning.
"""

import json
import logging
import time
import requests
from typing import Dict, List, Optional
from pathlib import Path

from character_version_manager import CharacterVersionManager
from unbiased_qc_validator import UnbiasedQCValidator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ECHO_URL = "http://localhost:8309"
COMFYUI_URL = "http://localhost:8188"


class EchoAnimeOrchestrator:
    """Echo Brain integration for anime character management."""

    def __init__(self):
        self.character_manager = CharacterVersionManager()
        self.qc_validator = UnbiasedQCValidator()
        self.echo_conversation_id = f"anime_orchestration_{int(time.time())}"

    def ask_echo_for_decision(self, context: Dict) -> Dict:
        """Ask Echo Brain to make a decision about character generation."""

        query = f"""You are managing anime character generation. Based on this context, decide what to do:

Context:
- Character: {context.get('character_name', 'Unknown')}
- Current version: {context.get('current_version', 'None')}
- Last validation: {context.get('last_validation', 'None')}
- Request: {context.get('user_request', 'None')}

Respond with a JSON decision:
{{
    "action": "generate|update|validate|skip",
    "character_updates": {{}},
    "generation_params": {{}},
    "reasoning": "why this decision"
}}"""

        try:
            response = requests.post(
                f"{ECHO_URL}/api/echo/query",
                json={
                    "query": query,
                    "conversation_id": self.echo_conversation_id,
                    "context": context
                },
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                # Parse Echo's response
                try:
                    decision = json.loads(result.get('response', '{}'))
                    return decision
                except:
                    return {"action": "generate", "reasoning": "Default action"}
            else:
                logger.warning(f"Echo Brain unavailable: {response.status_code}")
                return {"action": "generate", "reasoning": "Echo unavailable, using default"}

        except Exception as e:
            logger.error(f"Echo communication error: {e}")
            return {"action": "generate", "reasoning": "Error contacting Echo"}

    def generate_with_echo_guidance(self, character_name: str, user_request: str) -> Dict:
        """Generate character with Echo Brain guidance and proper QC."""

        logger.info(f"🧠 Consulting Echo Brain for {character_name}")

        # Get current character state
        current_char = self.character_manager.get_character(character_name)

        context = {
            "character_name": character_name,
            "current_version": current_char['version'][:8] if current_char else "None",
            "user_request": user_request,
            "last_validation": "Unknown"
        }

        # Ask Echo for decision
        echo_decision = self.ask_echo_for_decision(context)
        logger.info(f"Echo decision: {echo_decision.get('action', 'unknown')}")

        if echo_decision.get('action') == 'skip':
            return {
                "status": "skipped",
                "reason": echo_decision.get('reasoning', 'Echo said skip')
            }

        # Update character if Echo suggests changes
        if echo_decision.get('character_updates'):
            logger.info("📝 Applying Echo's character updates")
            self.character_manager.update_character(
                character_name,
                echo_decision['character_updates'],
                f"Echo Brain update: {echo_decision.get('reasoning', 'Automated update')}"
            )
            current_char = self.character_manager.get_character(character_name)

        if not current_char:
            return {
                "status": "error",
                "reason": f"Character {character_name} not found"
            }

        # Build generation requirements
        definition = current_char['definition']
        requirements = {
            "people_count": 1,
            "gender": definition.get('gender', 'unknown'),
            "hair_color": self._extract_hair_color(definition),
            "outfit": self._extract_outfit(definition)
        }

        # Generate image
        prompt = definition.get('prompt_template', f"{character_name}, anime character")

        logger.info(f"🎨 Generating {character_name} with requirements: {requirements}")

        for attempt in range(3):
            # Generate via ComfyUI
            image_path = self._generate_image(prompt, character_name, attempt)

            if not image_path:
                continue

            # Validate with unbiased QC
            logger.info(f"🔍 Validating generation attempt {attempt + 1}")
            validation = self.qc_validator.validate_image(str(image_path), requirements)

            if validation['valid']:
                logger.info(f"✅ Passed validation on attempt {attempt + 1}")

                # Report success to Echo
                self._report_to_echo(character_name, "success", validation)

                return {
                    "status": "success",
                    "image_path": str(image_path),
                    "validation": validation,
                    "attempts": attempt + 1,
                    "character_version": current_char['version'][:8]
                }
            else:
                logger.warning(f"❌ Failed validation: {validation.get('mismatches', [])}")

                # Ask Echo if we should adjust prompt
                adjustment_context = {
                    "character_name": character_name,
                    "attempt": attempt + 1,
                    "mismatches": validation.get('mismatches', []),
                    "observations": validation.get('observations', {})
                }

                echo_adjustment = self.ask_echo_for_decision(adjustment_context)

                if echo_adjustment.get('generation_params'):
                    # Apply Echo's suggested adjustments
                    prompt = echo_adjustment['generation_params'].get('prompt', prompt)

        # Report failure to Echo
        self._report_to_echo(character_name, "failed", validation)

        return {
            "status": "failed",
            "reason": "Failed validation after 3 attempts",
            "last_validation": validation
        }

    def _generate_image(self, prompt: str, character_name: str, attempt: int) -> Optional[Path]:
        """Generate image via ComfyUI."""

        # Strong negative prompt to ensure quality
        negative = (
            "multiple people, crowd, extra person, "
            "bad anatomy, deformed, extra limbs, "
            "wrong colors, incorrect features"
        )

        workflow = {
            "3": {
                "inputs": {
                    "seed": int(time.time() * 1000 + attempt) % 2147483647,
                    "steps": 30,
                    "cfg": 8.0,
                    "sampler_name": "dpmpp_2m_sde",
                    "scheduler": "karras",
                    "denoise": 1,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler"
            },
            "4": {
                "inputs": {"ckpt_name": "Counterfeit-V2.5.safetensors"},
                "class_type": "CheckpointLoaderSimple"
            },
            "5": {
                "inputs": {"width": 512, "height": 768, "batch_size": 1},
                "class_type": "EmptyLatentImage"
            },
            "6": {
                "inputs": {"text": f"solo, single person only, {prompt}", "clip": ["4", 1]},
                "class_type": "CLIPTextEncode"
            },
            "7": {
                "inputs": {"text": negative, "clip": ["4", 1]},
                "class_type": "CLIPTextEncode"
            },
            "8": {
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
                "class_type": "VAEDecode"
            },
            "9": {
                "inputs": {
                    "filename_prefix": f"echo_{character_name.replace(' ', '_')}_{int(time.time())}",
                    "images": ["8", 0]
                },
                "class_type": "SaveImage"
            }
        }

        try:
            response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
            if response.status_code != 200:
                return None

            prompt_id = response.json().get("prompt_id")
            time.sleep(10)  # Wait for generation

            history = requests.get(f"{COMFYUI_URL}/history/{prompt_id}").json()

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_output in outputs.values():
                    if "images" in node_output:
                        for img in node_output["images"]:
                            return Path("/mnt/1TB-storage/ComfyUI/output") / img["filename"]
        except Exception as e:
            logger.error(f"Generation error: {e}")

        return None

    def _extract_hair_color(self, definition: Dict) -> str:
        """Extract hair color from character definition."""
        appearance = definition.get('appearance', {})
        hair = appearance.get('hair', '')

        # Look for color keywords
        if 'black' in hair.lower() or 'dark' in hair.lower():
            return 'dark black'
        elif 'pink' in hair.lower():
            return 'pink'
        elif 'silver' in hair.lower() or 'white' in hair.lower():
            return 'silver white'
        elif 'red' in hair.lower():
            return 'red'
        elif 'blue' in hair.lower():
            return 'blue'

        return hair

    def _extract_outfit(self, definition: Dict) -> str:
        """Extract outfit description from character definition."""
        outfit = definition.get('outfit', {})
        return outfit.get('default', 'anime outfit')

    def _report_to_echo(self, character_name: str, status: str, validation: Dict):
        """Report generation results back to Echo Brain."""

        report = {
            "character": character_name,
            "status": status,
            "validation_score": validation.get('score', 0),
            "issues": validation.get('mismatches', []),
            "timestamp": time.time()
        }

        try:
            requests.post(
                f"{ECHO_URL}/api/echo/query",
                json={
                    "query": f"Character generation {status}: {character_name}",
                    "context": report,
                    "conversation_id": self.echo_conversation_id
                },
                timeout=5
            )
        except:
            pass  # Don't fail if Echo is unavailable


def test_echo_orchestration():
    """Test Echo orchestration with character generation."""

    orchestrator = EchoAnimeOrchestrator()

    print("\n🧠 ECHO BRAIN ANIME ORCHESTRATION TEST")
    print("=" * 70)

    # Test with Kai
    print("\n📝 Testing with Female Kai Nakamura")
    result = orchestrator.generate_with_echo_guidance(
        "Kai Nakamura",
        "Generate female Kai with dark black hair and military uniform"
    )

    print(f"\nResult:")
    print(f"  Status: {result.get('status', 'unknown')}")

    if result.get('status') == 'success':
        print(f"  Image: {Path(result['image_path']).name}")
        print(f"  Score: {result['validation'].get('score', 0)}/100")
        print(f"  Version: {result.get('character_version', 'unknown')}")
        print(f"  Attempts: {result.get('attempts', 'unknown')}")
    else:
        print(f"  Reason: {result.get('reason', 'unknown')}")

    print("=" * 70)


if __name__ == "__main__":
    test_echo_orchestration()