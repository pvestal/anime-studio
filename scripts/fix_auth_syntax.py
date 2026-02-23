#!/usr/bin/env python3
"""
Script to fix authentication syntax errors
"""
import re

def fix_auth_syntax():
    """Fix all authentication syntax errors"""

    with open('/opt/anime-studio/api/main.py', 'r') as f:
        content = f.read()

    # Fix double closing parentheses
    content = re.sub(r'db: Session = Depends\(get_db\)\)\):', r'db: Session = Depends(get_db)):', content)

    # Fix malformed postcurrent_user patterns
    content = re.sub(r'postcurrent_user: dict = Depends\(require_auth\), async def (\w+)\([^)]*\), \):',
                     r'async def \1(current_user: dict = Depends(require_auth)):', content)

    # Fix missing function parameters in malformed signatures
    content = re.sub(r'postcurrent_user: dict = Depends\(require_auth\), async def (\w+)\(([^)]*), \):',
                     r'async def \1(\2, current_user: dict = Depends(require_auth)):', content)

    # Fix functions with duplicate async def
    content = re.sub(r'async def (\w+)\(\s*async def \w+\(',
                     r'async def \1(', content)

    # Fix specific patterns that got mangled
    fixes = [
        # Fix generate_video_frontend_compat
        (r'postcurrent_user: dict = Depends\(require_auth\), async def generate_video_frontend_compat\(project_id: int, request: dict, \):',
         'async def generate_video_frontend_compat(project_id: int, request: dict, current_user: dict = Depends(require_auth), db: Session = Depends(get_db)):'),

        # Fix cancel_generation
        (r'postcurrent_user: dict = Depends\(require_auth\), async def cancel_generation\(request_id: str, \):',
         'async def cancel_generation(request_id: str, current_user: dict = Depends(require_auth)):'),

        # Fix clear_stuck_projects
        (r'postcurrent_user: dict = Depends\(require_auth\), async def clear_stuck_projects\(\):',
         'async def clear_stuck_projects(current_user: dict = Depends(require_admin)):'),

        # Fix generate_with_integrated_pipeline
        (r'postcurrent_user: dict = Depends\(require_auth\), async def generate_with_integrated_pipeline\(request: AnimeGenerationRequest, \):',
         'async def generate_with_integrated_pipeline(request: AnimeGenerationRequest, current_user: dict = Depends(require_auth), db: Session = Depends(get_db)):'),

        # Fix generate_professional_anime
        (r'postcurrent_user: dict = Depends\(require_auth\), async def generate_professional_anime\(request: AnimeGenerationRequest, \):',
         'async def generate_professional_anime(request: AnimeGenerationRequest, current_user: dict = Depends(require_auth), db: Session = Depends(get_db)):'),

        # Fix create_scene
        (r'postcurrent_user: dict = Depends\(require_auth\), async def create_scene\(data: dict, \):',
         'async def create_scene(data: dict, current_user: dict = Depends(require_auth), db: Session = Depends(get_db)):'),
    ]

    for pattern, replacement in fixes:
        content = re.sub(pattern, replacement, content)

    # Remove any duplicate async def statements on same line
    content = re.sub(r'async def \w+\(\s*async def (\w+)\(([^)]*)\):',
                     r'async def \1(\2):', content)

    # Fix Echo Brain functions that need database sessions
    echo_fixes = [
        (r'async def configure_echo_brain\(config: dict\):\s*async def configure_echo_brain\(config: dict\):',
         'async def configure_echo_brain(config: dict, current_user: dict = Depends(require_admin)):'),
        (r'async def suggest_scene_details\(request: dict\):\s*async def suggest_scene_details\(request: dict\):',
         'async def suggest_scene_details(request: dict, current_user: dict = Depends(require_auth)):'),
        (r'async def generate_character_dialogue\(character_id: int, request: dict\):\s*async def generate_character_dialogue\(character_id: int, request: dict\):',
         'async def generate_character_dialogue(character_id: int, request: dict, current_user: dict = Depends(require_auth)):'),
        (r'async def continue_episode\(episode_id: str, request: dict\):\s*async def continue_episode\(episode_id: str, request: dict\):',
         'async def continue_episode(episode_id: str, request: dict, current_user: dict = Depends(require_auth)):'),
        (r'async def analyze_storyline\(request: dict\):\s*async def analyze_storyline\(request: dict\):',
         'async def analyze_storyline(request: dict, current_user: dict = Depends(require_auth)):'),
        (r'async def brainstorm_project\(project_id: int, request: dict\):\s*async def brainstorm_project\(project_id: int, request: dict\):',
         'async def brainstorm_project(project_id: int, request: dict, current_user: dict = Depends(require_auth)):'),
        (r'async def batch_suggest_scenes\(episode_id: str, request: dict\):\s*async def batch_suggest_scenes\(episode_id: str, request: dict\):',
         'async def batch_suggest_scenes(episode_id: str, request: dict, current_user: dict = Depends(require_auth)):'),
        (r'async def provide_feedback\(suggestion_id: int, feedback: dict\):\s*async def provide_feedback\(suggestion_id: int, feedback: dict\):',
         'async def provide_feedback(suggestion_id: int, feedback: dict, current_user: dict = Depends(require_auth)):'),
        (r'async def echo_brain_fallback_scenes\(request: dict\):\s*async def echo_brain_fallback_scenes\(request: dict\):',
         'async def echo_brain_fallback_scenes(request: dict, current_user: dict = Depends(require_auth)):'),
    ]

    for pattern, replacement in echo_fixes:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)

    # Fix git and scene functions without db dependency
    git_fixes = [
        (r'async def commit_scene\(commit_data: dict\):\s*async def commit_scene\(commit_data: dict\):',
         'async def commit_scene(commit_data: dict, current_user: dict = Depends(require_auth)):'),
        (r'async def create_branch\(branch_data: dict\):\s*async def create_branch\(branch_data: dict\):',
         'async def create_branch(branch_data: dict, current_user: dict = Depends(require_auth)):'),
        (r'async def generate_from_scene\(\s*scene_id: str,\s*generation_type: str = "image",\s*db: Session = Depends\(get_db\)\s*\):\s*async def generate_from_scene\(',
         'async def generate_from_scene(\n    scene_id: str,\n    generation_type: str = "image",\n    current_user: dict = Depends(require_auth),\n    db: Session = Depends(get_db)\n):'),
        (r'async def generate_character_action\(\s*character_id: int,\s*action: str = "portrait",\s*generation_type: str = "image",\s*db: Session = Depends\(get_db\)\s*\):\s*async def generate_character_action\(',
         'async def generate_character_action(\n    character_id: int,\n    action: str = "portrait",\n    generation_type: str = "image",\n    current_user: dict = Depends(require_auth),\n    db: Session = Depends(get_db)\n):'),
    ]

    for pattern, replacement in git_fixes:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)

    # Final cleanup: Fix any remaining duplicate function definitions
    content = re.sub(r'(async def \w+\([^)]*\):)\s*async def \w+\(([^)]*)\):', r'\1', content, flags=re.MULTILINE)

    with open('/opt/anime-studio/api/main.py', 'w') as f:
        f.write(content)

    print("✅ Fixed authentication syntax errors")

if __name__ == "__main__":
    fix_auth_syntax()