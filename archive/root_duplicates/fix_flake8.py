#!/usr/bin/env python3
"""
Fix common Flake8 violations automatically
"""
import os
import re
from pathlib import Path

def fix_file(filepath):
    """Fix common Flake8 issues in a file"""
    with open(filepath, 'r') as f:
        lines = f.readlines()

    modified = False
    new_lines = []

    for i, line in enumerate(lines):
        # Fix E712: comparison to True (change == True to is True or just remove)
        if "== True" in line:
            # For filter conditions, just use the boolean directly
            line = line.replace(" == True", "")
            modified = True

        # Fix E501: line too long (add line continuation)
        if len(line.rstrip()) > 100 and not line.strip().startswith('#'):
            # Only for simple cases, split at logical points
            if '# ' in line and len(line.split('# ')[0].rstrip()) <= 100:
                # Comment is making it long, move to next line
                code_part = line.split('# ')[0].rstrip()
                comment_part = '# ' + '# '.join(line.split('# ')[1:])
                line = code_part + '\n'
                new_lines.append(line)
                line = '    ' * (len(code_part) - len(code_part.lstrip()) // 4) + comment_part
                modified = True

        new_lines.append(line)

    # Fix W292: no newline at end of file
    if new_lines and not new_lines[-1].endswith('\n'):
        new_lines[-1] += '\n'
        modified = True

    if modified:
        with open(filepath, 'w') as f:
            f.writelines(new_lines)
        return True
    return False

def remove_unused_imports(filepath):
    """Remove unused imports based on flake8 output"""
    unused_imports = {
        'api/auth_middleware.py': ['fastapi.Depends'],
        'api/character_consistency_endpoints.py': ['os', 'typing.Optional'],
        'api/character_consistency_engine.py': ['asyncio', 'pathlib.Path', 'typing.Tuple', 'PIL.Image'],
        'api/character_consistency_patch.py': ['uuid'],
        'api/character_router.py': ['os'],
        'api/database.py': ['sqlalchemy.MetaData', 'sqlalchemy.ext.declarative.declarative_base', 'sqlalchemy.pool.StaticPool'],
        'api/enhanced_generation_api.py': ['fastapi.responses.JSONResponse', 'ux_enhancements.ProgressUpdate'],
        'api/enhanced_image_generation.py': ['asyncio', 'os'],
        'api/error_recovery_endpoints.py': ['typing.List', 'fastapi.BackgroundTasks'],
        'api/image_generation_fixed.py': ['json', 'datetime.datetime'],
        'api/integrate_consistency_system.py': ['os', 'sys'],
    }

    if str(filepath) not in unused_imports:
        return False

    with open(filepath, 'r') as f:
        lines = f.readlines()

    new_lines = []
    modified = False

    for line in lines:
        skip = False
        for unused in unused_imports[str(filepath)]:
            if '.' in unused:
                # Handle module.submodule imports
                parts = unused.rsplit(".", 1)
                if f'from {parts[0]} import {parts[1]}' in line:
                    skip = True
                    modified = True
                    break
            # Handle direct imports
            if f'import {unused}' in line:
                skip = True
                modified = True
                break

        if not skip:
            new_lines.append(line)

    if modified:
        with open(filepath, 'w') as f:
            f.writelines(new_lines)
        return True
    return False

def main():
    # Get all Python files
    api_files = list(Path('api').glob('*.py'))
    test_files = list(Path('tests').glob('**/*.py'))

    all_files = api_files + test_files

    fixed_count = 0
    for filepath in all_files:
        fixed = False
        if fix_file(filepath):
            fixed = True
        if remove_unused_imports(filepath):
            fixed = True

        if fixed:
            fixed_count += 1
            print(f"Fixed: {filepath}")

    print(f"\nFixed {fixed_count} files")

if __name__ == '__main__':
    main()