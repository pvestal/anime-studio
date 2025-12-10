#!/usr/bin/env python3
"""
Fix spacing issues (E302, E305, E303)
"""
import os
import re
from pathlib import Path

def fix_spacing_issues(filepath):
    """Fix common spacing issues"""
    with open(filepath, 'r') as f:
        lines = f.readlines()

    new_lines = []
    modified = False

    for i, line in enumerate(lines):
        new_lines.append(line)

        # Check if this is a class or function definition
        if re.match(r'^(class |def |async def )', line.strip()):
            # Check if we need 2 blank lines before
            if i > 0:
                blank_count = 0
                j = i - 1
                while j >= 0 and lines[j].strip() == '':
                    blank_count += 1
                    j -= 1

                # If not enough blank lines, add them (only if previous line isn't import)
                if blank_count < 2 and j >= 0 and not lines[j].strip().startswith('import') and not lines[j].strip().startswith('from'):
                    # Remove current blank lines
                    while new_lines and new_lines[-2].strip() == '':
                        new_lines.pop(-2)

                    # Add exactly 2 blank lines
                    new_lines.insert(-1, '\n')
                    new_lines.insert(-1, '\n')
                    modified = True

    # Fix E305 (2 blank lines after class/function definitions)
    final_lines = []
    for i, line in enumerate(new_lines):
        final_lines.append(line)

        # If this line ends a class or function, ensure 2 blank lines after if followed by class/function
        if i < len(new_lines) - 3:
            next_non_blank = None
            for j in range(i + 1, min(len(new_lines), i + 5)):
                if new_lines[j].strip():
                    next_non_blank = new_lines[j]
                    break

            if (next_non_blank and
                re.match(r'^(class |def |async def )', next_non_blank.strip()) and
                not re.match(r'^\s', line)):  # Current line is not indented (end of class/function)

                # Check blank lines between
                blank_count = 0
                for j in range(i + 1, len(new_lines)):
                    if new_lines[j].strip() == '':
                        blank_count += 1
                    else:
                        break

                if blank_count < 2:
                    # Add missing blank line
                    final_lines.append('\n')
                    modified = True

    # Fix E303 (too many blank lines)
    result_lines = []
    blank_count = 0
    for line in final_lines:
        if line.strip() == '':
            blank_count += 1
            if blank_count <= 2:  # Max 2 blank lines
                result_lines.append(line)
        else:
            blank_count = 0
            result_lines.append(line)

    if modified or len(result_lines) != len(lines):
        with open(filepath, 'w') as f:
            f.writelines(result_lines)
        return True
    return False

def main():
    # Get all Python files
    api_files = list(Path('api').glob('*.py'))
    test_files = list(Path('tests').glob('**/*.py'))

    all_files = api_files + test_files

    fixed_count = 0
    for filepath in all_files:
        if fix_spacing_issues(filepath):
            fixed_count += 1
            print(f"Fixed spacing: {filepath}")

    print(f"\nFixed spacing in {fixed_count} files")

if __name__ == '__main__':
    main()