#!/usr/bin/env python3
"""
Fix the remaining Flake8 violations systematically
"""
import re
import os
import subprocess
from pathlib import Path

def fix_indentation_errors(filepath):
    """Fix indentation errors (E999)"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    fixed_lines = []
    for line in lines:
        # Fix mixed tabs/spaces - convert tabs to 4 spaces
        if '\t' in line:
            line = line.replace('\t', '    ')
        fixed_lines.append(line)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)

def fix_spacing_issues(filepath):
    """Fix spacing issues (E303, E302, E304, E305)"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix too many blank lines (E303) - max 2 blank lines
    content = re.sub(r'\n\s*\n\s*\n\s*\n+', '\n\n\n', content)

    # Fix missing blank lines before class/function (E302)
    content = re.sub(r'(\n)(class |def |async def )', r'\1\n\2', content)

    # Fix blank lines after decorators (E304)
    content = re.sub(r'(@\w+.*\n)\s*\n+(\s*def )', r'\1\2', content)

    # Fix blank lines after class/function (E305)
    content = re.sub(r'(\n\s*return.*\n)(\s*\n)?(\s*class |\s*def |\s*async def )', r'\1\n\n\3', content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def fix_line_length(filepath):
    """Fix long lines (E501)"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    fixed_lines = []
    for line in lines:
        if len(line.rstrip()) > 88:
            stripped = line.rstrip()
            indent = len(line) - len(line.lstrip())
            indent_str = ' ' * indent

            # Handle long function calls with parameters
            if '(' in stripped and ')' in stripped and '=' in stripped:
                # Break after commas
                if ', ' in stripped:
                    parts = stripped.split(', ')
                    if len(parts) > 1:
                        new_line = parts[0] + ',\n'
                        for i, part in enumerate(parts[1:], 1):
                            if i == len(parts) - 1:
                                new_line += indent_str + '    ' + part
                            else:
                                new_line += indent_str + '    ' + part + ',\n'
                        fixed_lines.append(new_line + '\n')
                        continue

            # Handle long import lines
            if stripped.startswith('from ') and 'import' in stripped:
                if ', ' in stripped:
                    import_part = stripped.split('import')[0] + 'import ('
                    imports = stripped.split('import')[1].strip().split(', ')
                    new_line = import_part + '\n'
                    for imp in imports:
                        new_line += indent_str + '    ' + imp.strip() + ',\n'
                    new_line += indent_str + ')'
                    fixed_lines.append(new_line + '\n')
                    continue

            # Handle long strings
            if '"' in stripped and len(stripped) > 88:
                # Break long strings at word boundaries
                if ' ' in stripped:
                    words = stripped.split(' ')
                    current_line = words[0]
                    for word in words[1:]:
                        if len(current_line + ' ' + word) <= 85:
                            current_line += ' ' + word
                        else:
                            fixed_lines.append(current_line + ' \\\n')
                            current_line = indent_str + '    ' + word
                    fixed_lines.append(current_line + '\n')
                    continue

        fixed_lines.append(line)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)

def fix_import_placement(filepath):
    """Fix import placement (E402)"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Separate imports and non-imports
    imports = []
    non_imports = []
    found_first_non_import = False

    for line in lines:
        stripped = line.strip()
        if (stripped.startswith('import ') or stripped.startswith('from ')) and not found_first_non_import:
            imports.append(line)
        else:
            if stripped and not stripped.startswith('#') and not stripped.startswith('"""'):
                found_first_non_import = True
            non_imports.append(line)

    # Only reorganize if we found misplaced imports
    if any(line.strip().startswith(('import ', 'from ')) for line in non_imports):
        # Extract any misplaced imports
        misplaced_imports = []
        cleaned_non_imports = []

        for line in non_imports:
            if line.strip().startswith(('import ', 'from ')):
                misplaced_imports.append(line)
            else:
                cleaned_non_imports.append(line)

        # Combine all imports at the top
        all_imports = imports + misplaced_imports

        # Write back reorganized content
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(all_imports)
            if all_imports and cleaned_non_imports:
                f.write('\n')
            f.writelines(cleaned_non_imports)

def fix_bare_except(filepath):
    """Fix bare except statements (E722)"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace bare except with Exception
    content = re.sub(r'except:', 'except Exception:', content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def fix_unused_variables(filepath):
    """Fix unused variable warnings (F841)"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Add underscore prefix to unused variables
    content = re.sub(r'test_query = ', '_test_query = ', content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def fix_continuation_indent(filepath):
    """Fix continuation line indentation (E128)"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    fixed_lines = []
    in_continuation = False

    for i, line in enumerate(lines):
        if i > 0 and lines[i-1].rstrip().endswith('\\'):
            # This is a continuation line
            stripped = line.lstrip()
            # Ensure proper indentation (8 spaces from base)
            if line.startswith('        '):  # Already properly indented
                fixed_lines.append(line)
            else:
                # Find base indentation from previous line
                prev_indent = len(lines[i-1]) - len(lines[i-1].lstrip())
                new_line = ' ' * (prev_indent + 8) + stripped
                fixed_lines.append(new_line)
        else:
            fixed_lines.append(line)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)

def process_file(filepath):
    """Process a single file to fix all violations"""
    print(f"Fixing {filepath}")

    # Apply fixes in order
    fix_indentation_errors(filepath)
    fix_import_placement(filepath)
    fix_spacing_issues(filepath)
    fix_line_length(filepath)
    fix_bare_except(filepath)
    fix_unused_variables(filepath)
    fix_continuation_indent(filepath)

def main():
    # Get list of Python files with violations
    result = subprocess.run([
        'venv/bin/flake8', 'api/', 'tests/', '--max-line-length=88', '--format=%(path)s'
    ], capture_output=True, text=True, cwd='/opt/tower-anime-production')

    files_with_violations = set()
    if result.stdout:
        for line in result.stdout.strip().split('\n'):
            if line and ':' in line:
                filepath = line.split(':')[0]
                files_with_violations.add(filepath)

    print(f"Found {len(files_with_violations)} files with violations")

    # Process each file
    for filepath in sorted(files_with_violations):
        if os.path.exists(filepath):
            process_file(filepath)

    # Run autoflake to remove unused imports
    print("Running autoflake...")
    subprocess.run([
        'venv/bin/autoflake', '--remove-all-unused-imports', '--remove-unused-variables',
        '--in-place', '--recursive', 'api/', 'tests/'
    ], cwd='/opt/tower-anime-production')

    # Run isort to organize imports
    print("Running isort...")
    subprocess.run([
        'venv/bin/isort', 'api/', 'tests/', '--profile=black', '--line-length=88'
    ], cwd='/opt/tower-anime-production')

    # Run black for final formatting
    print("Running black...")
    subprocess.run([
        'venv/bin/black', 'api/', 'tests/', '--line-length=88'
    ], cwd='/opt/tower-anime-production')

    print("Done! Checking final violation count...")
    result = subprocess.run([
        'venv/bin/flake8', 'api/', 'tests/', '--max-line-length=88', '--count'
    ], capture_output=True, text=True, cwd='/opt/tower-anime-production')

    print("Final flake8 output:")
    print(result.stdout)
    print(result.stderr)

if __name__ == '__main__':
    main()