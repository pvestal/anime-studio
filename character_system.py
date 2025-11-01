#!/usr/bin/env python3
"""
Character System for Anime Production
Handles character definitions, lookups, and prompt generation
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, Optional, List, Any

logger = logging.getLogger(__name__)

class CharacterSystem:
    """Manages character definitions and generation prompts"""

    def __init__(self, characters_dir: str = "/opt/tower-anime-production/characters"):
        self.characters_dir = Path(characters_dir)
        self.characters_cache = {}
        self.load_characters()

    def load_characters(self):
        """Load all character definitions from JSON files"""
        try:
            if not self.characters_dir.exists():
                logger.warning(f"Characters directory {self.characters_dir} does not exist")
                return

            for character_file in self.characters_dir.glob("*.json"):
                try:
                    with open(character_file, 'r', encoding='utf-8') as f:
                        character_data = json.load(f)
                        character_name = character_data.get('name', character_file.stem)
                        self.characters_cache[character_name.lower()] = character_data
                        logger.info(f"Loaded character: {character_name}")
                except Exception as e:
                    logger.error(f"Error loading character file {character_file}: {e}")
        except Exception as e:
            logger.error(f"Error loading characters: {e}")

    def get_character(self, character_name: str) -> Optional[Dict[str, Any]]:
        """Get character definition by name"""
        normalized_name = character_name.lower().strip()
        return self.characters_cache.get(normalized_name)

    def get_character_visual_prompt(self, character_name: str) -> Optional[str]:
        """Get visual description prompt for character generation"""
        character = self.get_character(character_name)
        if not character:
            logger.warning(f"Character '{character_name}' not found")
            return None

        generation_prompts = character.get('generation_prompts', {})
        return generation_prompts.get('visual_description', '')

    def get_character_style_tags(self, character_name: str) -> List[str]:
        """Get style tags for character generation"""
        character = self.get_character(character_name)
        if not character:
            return []

        generation_prompts = character.get('generation_prompts', {})
        return generation_prompts.get('style_tags', [])

    def get_character_negative_prompts(self, character_name: str) -> List[str]:
        """Get negative prompts to avoid incorrect generation"""
        character = self.get_character(character_name)
        if not character:
            return []

        generation_prompts = character.get('generation_prompts', {})
        return generation_prompts.get('negative_prompts', [])

    def build_generation_prompt(self, character_name: str, scene_context: str = "",
                              style_override: str = None) -> Dict[str, Any]:
        """Build complete generation prompt for character"""
        character = self.get_character(character_name)
        if not character:
            return {
                'prompt': f"anime character {character_name}",
                'negative_prompt': "",
                'style_tags': [],
                'used_project_reference': False,
                'character_found': False
            }

        # Build main prompt
        visual_desc = self.get_character_visual_prompt(character_name)
        style_tags = self.get_character_style_tags(character_name)
        negative_prompts = self.get_character_negative_prompts(character_name)

        # Combine with scene context
        if scene_context:
            main_prompt = f"{visual_desc}, {scene_context}"
        else:
            main_prompt = visual_desc

        # Add style tags
        if style_tags:
            style_text = ", ".join(style_tags)
            main_prompt = f"{main_prompt}, {style_text}"

        return {
            'prompt': main_prompt,
            'negative_prompt': ", ".join(negative_prompts),
            'style_tags': style_tags,
            'character_data': character,
            'used_project_reference': True,
            'character_found': True,
            'source': f"character_system:{character_name}"
        }

    def list_available_characters(self) -> List[str]:
        """List all available character names"""
        return list(self.characters_cache.keys())

    def verify_character_integrity(self, character_name: str) -> Dict[str, Any]:
        """Verify character definition has all required fields"""
        character = self.get_character(character_name)
        if not character:
            return {
                'valid': False,
                'errors': [f"Character '{character_name}' not found"],
                'warnings': []
            }

        errors = []
        warnings = []

        # Required fields
        required_fields = ['name', 'gender', 'generation_prompts']
        for field in required_fields:
            if field not in character:
                errors.append(f"Missing required field: {field}")

        # Check generation prompts
        if 'generation_prompts' in character:
            gen_prompts = character['generation_prompts']
            if 'visual_description' not in gen_prompts:
                errors.append("Missing 'visual_description' in generation_prompts")
            if 'negative_prompts' not in gen_prompts:
                warnings.append("Missing 'negative_prompts' - may generate incorrect gender/features")

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'character_data': character
        }

# Global instance
character_system = CharacterSystem()

def get_character_prompt(character_name: str, scene_context: str = "") -> Dict[str, Any]:
    """Main function for getting character generation prompts"""
    return character_system.build_generation_prompt(character_name, scene_context)

def verify_character_system() -> Dict[str, Any]:
    """Verify the character system is working correctly"""
    characters = character_system.list_available_characters()

    results = {
        'system_working': len(characters) > 0,
        'characters_loaded': len(characters),
        'character_list': characters,
        'verification_results': {}
    }

    # Verify each character
    for char_name in characters:
        verification = character_system.verify_character_integrity(char_name)
        results['verification_results'][char_name] = verification

    return results

if __name__ == "__main__":
    # Test the character system
    import pprint

    print("=== Character System Test ===")

    # Test verification
    print("\n1. System Verification:")
    verification = verify_character_system()
    pprint.pprint(verification)

    # Test Kai Nakamura specifically
    print("\n2. Kai Nakamura Test:")
    kai_prompt = get_character_prompt("Kai Nakamura", "standing confidently in neon-lit alley")
    pprint.pprint(kai_prompt)

    # Test non-existent character
    print("\n3. Non-existent Character Test:")
    missing_prompt = get_character_prompt("Non Existent Character")
    pprint.pprint(missing_prompt)