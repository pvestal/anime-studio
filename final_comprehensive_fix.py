#!/usr/bin/env python3
"""
Final comprehensive fix for all remaining Flake8 violations.
"""

import os
import re

def fix_imports_and_undefined_names(content):
    """Fix F401 and F821 violations by adding proper imports"""
    lines = content.split('\n')

    # Collect all undefined names and unused imports
    undefined_names = set()
    unused_imports = set()
    has_imports = False

    # Check for undefined names in content
    if 'BaseModel' in content:
        undefined_names.add('from pydantic import BaseModel')
    if 'Optional' in content or 'Dict' in content or 'Any' in content or 'List' in content:
        undefined_names.add('from typing import Any, Dict, List, Optional')
    if 'np.' in content:
        undefined_names.add('import numpy as np')
    if 'pytest.' in content:
        undefined_names.add('import pytest')
    if 'sys.' in content:
        undefined_names.add('import sys')
    if 'json.' in content:
        undefined_names.add('import json')
    if 'Path(' in content:
        undefined_names.add('from pathlib import Path')
    if 'time.' in content:
        undefined_names.add('import time')
    if 'patch(' in content:
        undefined_names.add('from unittest.mock import patch')

    # Find import section
    import_section_end = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and not stripped.startswith('"""'):
            if not (stripped.startswith('import ') or stripped.startswith('from ')):
                import_section_end = i
                break
            else:
                has_imports = True

    # Insert missing imports after docstring
    docstring_end = 0
    in_docstring = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if '"""' in stripped or "'''" in stripped:
            if not in_docstring:
                in_docstring = True
            elif in_docstring:
                in_docstring = False
                docstring_end = i + 1
                break
        elif not in_docstring and stripped and not stripped.startswith('#'):
            break

    # Build new content
    new_lines = []

    # Add docstring/header
    new_lines.extend(lines[:docstring_end])

    # Add blank line after docstring if needed
    if docstring_end > 0 and lines[docstring_end-1].strip():
        new_lines.append('')

    # Add imports
    for import_stmt in sorted(undefined_names):
        new_lines.append(import_stmt)

    # Add blank line after imports if we added any
    if undefined_names:
        new_lines.append('')

    # Add rest of content, skipping existing problematic imports
    rest_start = max(docstring_end, import_section_end)
    for line in lines[rest_start:]:
        # Skip unused imports
        if (line.strip().startswith('import hvac') or
            line.strip().startswith('from fastapi import HTTPException') or
            line.strip().startswith('from fastapi import Request')):
            continue
        new_lines.append(line)

    return '\n'.join(new_lines)

def fix_line_length_violations(content):
    """Fix E501 line length violations"""
    lines = content.split('\n')
    fixed_lines = []

    for line in lines:
        if len(line) <= 88:
            fixed_lines.append(line)
            continue

        # Break long lines
        indent = len(line) - len(line.lstrip())

        # Handle function definitions
        if 'def ' in line and '(' in line:
            paren_pos = line.find('(')
            if paren_pos > 0:
                func_part = line[:paren_pos+1]
                params_part = line[paren_pos+1:].rstrip('):')

                if ',' in params_part:
                    params = [p.strip() for p in params_part.split(',')]
                    if len(params) > 1:
                        fixed_lines.append(func_part)
                        for i, param in enumerate(params):
                            prefix = ' ' * (indent + 4)
                            suffix = ',' if i < len(params) - 1 else ''
                            fixed_lines.append(prefix + param + suffix)
                        fixed_lines.append(' ' * indent + '):')
                        continue

        # Handle assert statements
        if line.strip().startswith('assert'):
            parts = line.split(' and ')
            if len(parts) > 1:
                fixed_lines.append(parts[0] + ' and')
                for part in parts[1:]:
                    fixed_lines.append(' ' * (indent + 4) + part.strip())
                continue

        # Handle string literals
        if ' + ' in line and ('"' in line or "'" in line):
            # Break at concatenation
            plus_pos = line.rfind(' + ', 0, 85)
            if plus_pos > 0:
                part1 = line[:plus_pos + 3]
                part2 = ' ' * (indent + 4) + line[plus_pos + 3:].lstrip()
                fixed_lines.extend([part1, part2])
                continue

        # Default: keep as is
        fixed_lines.append(line)

    return '\n'.join(fixed_lines)

def fix_spacing_violations(content):
    """Fix E303, E304, E305 spacing violations"""
    lines = content.split('\n')
    fixed_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Count consecutive blank lines
        blank_count = 0
        j = i
        while j < len(lines) and not lines[j].strip():
            blank_count += 1
            j += 1

        if blank_count > 0:
            # Determine what comes after blanks
            next_line = lines[j] if j < len(lines) else ""
            prev_line_idx = i - 1
            while prev_line_idx >= 0 and not lines[prev_line_idx].strip():
                prev_line_idx -= 1
            prev_line = lines[prev_line_idx] if prev_line_idx >= 0 else ""

            # Apply spacing rules
            if (next_line.startswith('class ') or
                next_line.startswith('def ') or
                next_line.startswith('async def ')):
                # Before function/class: 2 blank lines
                if not prev_line.startswith('@'):
                    fixed_lines.extend(['', ''])
                else:
                    # After decorator: no blank line
                    pass
            elif prev_line.startswith('@'):
                # After decorator before function: no blank line (E304)
                pass
            elif (prev_line.startswith('def ') or
                  prev_line.startswith('class ') or
                  prev_line.startswith('async def ')):
                # After function/class: 2 blank lines (E305)
                if next_line and not next_line.startswith(('@', 'def ', 'class ', 'async def ')):
                    fixed_lines.extend(['', ''])
            else:
                # Regular spacing: max 1 blank line (E303)
                if blank_count > 2:
                    fixed_lines.append('')
                elif blank_count >= 1:
                    fixed_lines.append('')

            i = j
        else:
            fixed_lines.append(line)
            i += 1

    return '\n'.join(fixed_lines)

def fix_indentation_violations(content):
    """Fix E999 indentation violations"""
    lines = content.split('\n')
    fixed_lines = []

    for line in lines:
        if not line.strip():
            fixed_lines.append(line)
            continue

        # Fix indentation to multiples of 4
        leading_spaces = len(line) - len(line.lstrip())
        if leading_spaces % 4 != 0:
            correct_spaces = (leading_spaces // 4) * 4
            if leading_spaces % 4 >= 2:
                correct_spaces += 4
            line = ' ' * correct_spaces + line.lstrip()

        fixed_lines.append(line)

    return '\n'.join(fixed_lines)

def fix_file(filepath):
    """Fix all violations in a file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Apply fixes in order
        content = fix_imports_and_undefined_names(content)
        content = fix_line_length_violations(content)
        content = fix_spacing_violations(content)
        content = fix_indentation_violations(content)

        # Remove trailing whitespace
        lines = content.split('\n')
        lines = [line.rstrip() for line in lines]
        content = '\n'.join(lines)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"Fixed: {filepath}")
        return True

    except Exception as e:
        print(f"Error fixing {filepath}: {e}")
        return False

def main():
    os.chdir("/opt/tower-anime-production")

    # Get all Python files
    import glob
    files = []
    for pattern in ['api/*.py', 'tests/*.py', 'tests/*/*.py']:
        files.extend(glob.glob(pattern))

    print(f"Fixing {len(files)} Python files...")

    fixed_count = 0
    for filepath in files:
        if fix_file(filepath):
            fixed_count += 1

    print(f"Fixed {fixed_count} files successfully")

if __name__ == "__main__":
    main()