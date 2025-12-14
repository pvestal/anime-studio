#!/usr/bin/env python3
"""
Fix ALL remaining Flake8 violations
"""
import os
import re
from pathlib import Path

def fix_all_spacing_issues(filepath):
    """Fix all spacing and formatting issues"""
    with open(filepath, 'r') as f:
        lines = f.readlines()

    new_lines = []
    i = 0
    modified = False

    while i < len(lines):
        line = lines[i]

        # Fix E304: blank lines found after function decorator
        if line.strip().startswith('@') and i + 1 < len(lines):
            # Add decorator line
            new_lines.append(line)
            i += 1

            # Remove any blank lines immediately after decorator
            while i < len(lines) and lines[i].strip() == '':
                i += 1
                modified = True

            # Add the function definition if we haven't reached end
            if i < len(lines):
                new_lines.append(lines[i])
            i += 1
            continue

        # Fix E303: too many blank lines (max 2)
        if line.strip() == '':
            blank_count = 1
            j = i + 1

            # Count consecutive blank lines
            while j < len(lines) and lines[j].strip() == '':
                blank_count += 1
                j += 1

            # Keep at most 2 blank lines
            if blank_count > 2:
                new_lines.append(line)  # First blank line
                new_lines.append('\n')  # Second blank line
                i = j
                modified = True
                continue

        new_lines.append(line)
        i += 1

    # Fix E305: expected 2 blank lines after class or function definition
    final_lines = []
    for i, line in enumerate(new_lines):
        final_lines.append(line)

        # Check if this line ends a top-level class or function
        if (i < len(new_lines) - 1 and
            not line.startswith(' ') and
            not line.startswith('\t') and
            line.strip() and
            not line.strip().startswith('#') and
            not line.strip().startswith('@')):

            # Look ahead to see if next non-blank line is a class/function
            j = i + 1
            blank_lines_after = 0
            while j < len(new_lines) and new_lines[j].strip() == '':
                blank_lines_after += 1
                j += 1

            if (j < len(new_lines) and
                (new_lines[j].strip().startswith('class ') or
                 new_lines[j].strip().startswith('def ') or
                 new_lines[j].strip().startswith('async def '))):

                if blank_lines_after < 2:
                    # Add missing blank lines
                    for _ in range(2 - blank_lines_after):
                        final_lines.append('\n')
                    modified = True

    if modified:
        with open(filepath, 'w') as f:
            f.writelines(final_lines)
        return True
    return False

def fix_line_length(filepath):
    """Fix lines that are too long"""
    with open(filepath, 'r') as f:
        lines = f.readlines()

    new_lines = []
    modified = False

    for line in lines:
        if len(line.rstrip()) > 100:
            # Try to break long lines at logical points
            stripped = line.rstrip()
            indent = len(line) - len(line.lstrip())
            indent_str = ' ' * indent

            # Break at function parameters
            if '(' in stripped and ')' in stripped and 'def ' in stripped:
                # Function definition - break at parameters
                func_part = stripped.split('(')[0] + '('
                params_part = '('.join(stripped.split('(')[1:])

                if len(func_part) <= 100:
                    new_lines.append(func_part + '\n')
                    new_lines.append(indent_str + '    ' + params_part + '\n')
                    modified = True
                    continue

            # Break at commas for long parameter lists
            elif ',' in stripped and ('(' in stripped or '[' in stripped):
                parts = stripped.split(',')
                if len(parts) > 1:
                    current_line = parts[0] + ','
                    for part in parts[1:-1]:
                        if len(current_line + part) > 90:
                            new_lines.append(current_line + '\n')
                            current_line = indent_str + '    ' + part.strip() + ','
                        else:
                            current_line += part + ','

                    # Add the last part
                    last_part = parts[-1]
                    if len(current_line + last_part) > 90:
                        new_lines.append(current_line + '\n')
                        new_lines.append(indent_str + '    ' + last_part + '\n')
                    else:
                        new_lines.append(current_line + last_part + '\n')
                    modified = True
                    continue

            # Break at operators
            elif any(op in stripped for op in [' and ', ' or ', ' + ', ' == ', ' != ']):
                for op in [' and ', ' or ', ' + ', ' == ', ' != ']:
                    if op in stripped:
                        parts = stripped.split(op)
                        if len(parts) == 2 and len(parts[0]) <= 90:
                            new_lines.append(parts[0] + ' \\' + '\n')
                            new_lines.append(indent_str + '    ' + op.strip() + ' ' + parts[1] + '\n')
                            modified = True
                            break
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    if modified:
        with open(filepath, 'w') as f:
            f.writelines(new_lines)
        return True
    return False

def fix_imports(filepath):
    """Fix E402 module level import not at top"""
    with open(filepath, 'r') as f:
        lines = f.readlines()

    # Find all imports
    imports = []
    other_lines = []
    found_first_non_import = False

    for line in lines:
        stripped = line.strip()
        if (stripped.startswith('import ') or stripped.startswith('from ')) and not found_first_non_import:
            imports.append(line)
        elif stripped.startswith('#') or stripped == '' or stripped.startswith('"""') or stripped.startswith("'''"):
            # Comments, docstrings, and blank lines can come before imports
            other_lines.append(line)
        else:
            found_first_non_import = True
            other_lines.append(line)

    # If we found imports mixed with code, reorganize
    if found_first_non_import and imports:
        # Find the end of the module docstring/comments
        insert_point = 0
        in_docstring = False
        for i, line in enumerate(other_lines):
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                if not in_docstring:
                    in_docstring = True
                elif stripped.endswith('"""') or stripped.endswith("'''"):
                    in_docstring = False
                    insert_point = i + 1
            elif not in_docstring and stripped and not stripped.startswith('#'):
                insert_point = i
                break

        # Insert imports at the right place
        new_lines = other_lines[:insert_point] + ['\n'] + imports + ['\n'] + other_lines[insert_point:]

        with open(filepath, 'w') as f:
            f.writelines(new_lines)
        return True

    return False

def main():
    """Fix all Flake8 issues"""
    # Get all Python files
    api_files = list(Path('api').glob('*.py'))
    test_files = list(Path('tests').glob('**/*.py'))
    all_files = api_files + test_files

    fixed_count = 0

    for filepath in all_files:
        fixed = False

        # Fix spacing issues
        if fix_all_spacing_issues(filepath):
            fixed = True

        # Fix line length
        if fix_line_length(filepath):
            fixed = True

        # Fix imports
        if fix_imports(filepath):
            fixed = True

        if fixed:
            fixed_count += 1
            print(f"Fixed: {filepath}")

    print(f"\nFixed {fixed_count} files")

if __name__ == '__main__':
    main()