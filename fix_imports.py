#!/usr/bin/env python3
"""Fix import statements in API files"""

import os
import re

def fix_imports(filepath):
    """Fix imports in a single file"""
    with open(filepath, 'r') as f:
        content = f.read()

    original = content

    # Fix imports that need api. prefix
    replacements = [
        (r'^from core\.', 'from api.core.'),
        (r'^from models', 'from api.models'),
        (r'^from schemas', 'from api.schemas'),
        (r'^from services', 'from api.services'),
        (r'^import core\.', 'import api.core.'),
        (r'^import models', 'import api.models'),
        (r'^import schemas', 'import api.schemas'),
        (r'^import services', 'import api.services'),
    ]

    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Fixed imports in {filepath}")
        return True
    return False

# Fix all Python files in api directory
api_dir = '/opt/anime-studio/api'
fixed_count = 0

for root, dirs, files in os.walk(api_dir):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            if fix_imports(filepath):
                fixed_count += 1

print(f"\nFixed imports in {fixed_count} files")