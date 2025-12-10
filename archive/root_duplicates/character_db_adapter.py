#!/usr/bin/env python3
"""
Character Database Adapter
Transforms comprehensive character JSON files into API-compatible format
"""
import json
import requests
from pathlib import Path
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_URL = "http://***REMOVED***:8328"

class CharacterDBAdapter:
    """Adapts comprehensive character JSONs to API schema"""

    def transform_character(self, char_data: Dict) -> Dict:
        """Transform comprehensive character JSON to API format"""

        # Extract name (required)
        name = char_data.get('name', 'Unknown')

        # Create concise description from key fields
        description = self._create_description(char_data)

        # Map appearance to visual_traits
        visual_traits = {
            'appearance': char_data.get('appearance', {}),
            'clothing_style': char_data.get('clothing_style', {}),
            'generation_prompts': char_data.get('generation_prompts', {})
        }

        # Map personality and voice to personality_traits
        personality_traits = {
            'personality': char_data.get('personality', {}),
            'voice_profile': char_data.get('voice_profile', {}),
            'daily_routine': char_data.get('daily_routine', {})
        }

        # Map relationships and context
        relationships = {
            'interactions': char_data.get('interactions_with_takeshi', {}),
            'relationship_history': char_data.get('background', {}).get('relationship_with_takeshi', ''),
            'project_context': char_data.get('project_context', {})
        }

        # Create evolution arc from background and story progression
        evolution_arc = self._create_evolution_arc(char_data)

        return {
            'name': name,
            'description': description,
            'visual_traits': visual_traits,
            'personality_traits': personality_traits,
            'relationships': relationships,
            'evolution_arc': evolution_arc
        }

    def _create_description(self, char_data: Dict) -> str:
        """Create concise description from character data"""
        parts = []

        # Basic info
        if 'age' in char_data:
            parts.append(f"{char_data['age']} year old")
        if 'gender' in char_data:
            parts.append(char_data['gender'])
        if 'occupation' in char_data:
            parts.append(char_data['occupation'])

        # Character type
        if 'character_type' in char_data:
            parts.append(f"({char_data['character_type']})")

        # Key personality traits (first 3)
        personality = char_data.get('personality', {})
        traits = personality.get('traits', [])
        if traits:
            trait_str = ', '.join(traits[:3])
            parts.append(f"- {trait_str}")

        # Approach/role
        if 'approach_to_takeshi' in personality:
            parts.append(f"Role: {personality['approach_to_takeshi'][:100]}")

        return '. '.join(parts) + '.'

    def _create_evolution_arc(self, char_data: Dict) -> List[Dict]:
        """Create evolution arc from character progression"""
        arc = []

        # Starting point
        background = char_data.get('background', {})
        if 'why_lives_here' in background:
            arc.append({
                'stage': 'introduction',
                'description': background['why_lives_here'],
                'status': 'completed'
            })

        # Relationship progression
        project_context = char_data.get('project_context', {})
        if 'relationship_progression' in project_context:
            progression = project_context['relationship_progression'].split('→')
            for i, stage in enumerate(progression):
                arc.append({
                    'stage': f'progression_{i+1}',
                    'description': stage.strip(),
                    'status': 'pending' if i > 0 else 'in_progress'
                })

        # Story arc
        if 'story_arc' in project_context:
            arc.append({
                'stage': 'story_goal',
                'description': project_context['story_arc'],
                'status': 'planned'
            })

        return arc

    def save_character_to_db(self, char_file: Path, project_id: int, image_path: Optional[str] = None) -> Dict:
        """Load character JSON, transform, and save to database via project API"""

        # Load character JSON
        with open(char_file, 'r') as f:
            char_data = json.load(f)

        # Transform to API format
        transformed = self.transform_character(char_data)

        # Add image path if provided
        if image_path:
            transformed['visual_traits']['generated_image'] = image_path

        # Prepare payload (no bible_id needed, API handles it)
        payload = transformed

        logger.info(f"Saving character: {transformed['name']}")
        logger.info(f"Description: {transformed['description'][:100]}...")

        # POST to API
        try:
            response = requests.post(
                f"{API_URL}/api/anime/projects/{project_id}/bible/characters",
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"✅ Saved {transformed['name']} (ID: {result.get('id')})")
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to save {transformed['name']}: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise

def main():
    """Test adapter with Mei Kobayashi"""
    adapter = CharacterDBAdapter()

    # Test file
    mei_file = Path('/opt/tower-anime-production/workflows/projects/tokyo_debt_desire/characters/mei_kobayashi.json')

    if not mei_file.exists():
        logger.error(f"Character file not found: {mei_file}")
        return

    # Load and transform
    with open(mei_file, 'r') as f:
        char_data = json.load(f)

    transformed = adapter.transform_character(char_data)

    # Print result
    print("\n=== TRANSFORMED CHARACTER ===")
    print(json.dumps(transformed, indent=2))

if __name__ == '__main__':
    main()

def test_save_mei():
    """Test saving Mei Kobayashi to database"""
    adapter = CharacterDBAdapter()
    
    mei_file = Path('/opt/tower-anime-production/workflows/projects/tokyo_debt_desire/characters/mei_kobayashi.json')
    mei_image = '/mnt/1TB-storage/ComfyUI/output/mei_kobayashi_tokyo_debt_512p_00001_.png'
    project_id = 1  # Tokyo Debt Desire project
    
    try:
        result = adapter.save_character_to_db(mei_file, project_id, mei_image)
        print('\n✅ SUCCESS: Mei saved to database!')
        print(f'Character ID: {result.get("id")}')
        print(f'Project: Tokyo Debt Desire')
        print(f'Name: {result.get("name")}')
        return result
    except Exception as e:
        print(f'\n❌ FAILED: {e}')
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--save':
        test_save_mei()
    else:
        main()
