#!/usr/bin/env python3
"""
Fix f-strings without placeholders (F541)
"""
import os
import re
from pathlib import Path

def fix_fstring_placeholders(filepath):
    """Fix f-strings that don't have placeholders"""
    with open(filepath, 'r') as f:
        content = f.read()

    original_content = content

    # Pattern to find f-strings without placeholders
    # Look for f"text" or f'text' without any {variables}
    pattern = r'f(["\'])((?:(?!\1)[^{}])*)\1'

    def replace_fstring(match):
        quote = match.group(1)
        text = match.group(2)
        # If no placeholders, convert to regular string
        if '{' not in text:
            return f'{quote}{text}{quote}'
        return match.group(0)

    content = re.sub(pattern, replace_fstring, content)

    if content != original_content:
        with open(filepath, 'w') as f:
            f.write(content)
        return True
    return False

def main():
    # Get all Python files
    api_files = list(Path('api').glob('*.py'))
    test_files = list(Path('tests').glob('**/*.py'))

    all_files = api_files + test_files

    fixed_count = 0
    for filepath in all_files:
        if fix_fstring_placeholders(filepath):
            fixed_count += 1
            print(f"Fixed f-strings: {filepath}")

    print(f"\nFixed f-strings in {fixed_count} files")

if __name__ == '__main__':
    main()