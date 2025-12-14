#!/usr/bin/env python3
"""
Comprehensive Flake8 violation fixer for clean modular architecture.
Fixes ALL remaining violations systematically.
"""

import re
import os
import subprocess
import glob
from pathlib import Path

class ComprehensiveFlake8Fixer:
    def __init__(self):
        self.base_dir = "/opt/tower-anime-production"
        self.max_line_length = 88

    def run_autoflake(self):
        """Remove unused imports and variables"""
        print("Running autoflake...")
        try:
            subprocess.run([
                "venv/bin/autoflake",
                "--remove-all-unused-imports",
                "--remove-unused-variables",
                "--in-place",
                "--recursive",
                "api/",
                "tests/"
            ], cwd=self.base_dir, check=False)
        except FileNotFoundError:
            print("autoflake not found, installing...")
            subprocess.run([
                "venv/bin/pip", "install", "autoflake"
            ], cwd=self.base_dir)
            subprocess.run([
                "venv/bin/autoflake",
                "--remove-all-unused-imports",
                "--remove-unused-variables",
                "--in-place",
                "--recursive",
                "api/",
                "tests/"
            ], cwd=self.base_dir, check=False)

    def run_isort(self):
        """Sort imports properly"""
        print("Running isort...")
        try:
            subprocess.run([
                "venv/bin/isort",
                "--line-length", str(self.max_line_length),
                "api/",
                "tests/"
            ], cwd=self.base_dir, check=False)
        except FileNotFoundError:
            print("isort not found, installing...")
            subprocess.run([
                "venv/bin/pip", "install", "isort"
            ], cwd=self.base_dir)
            subprocess.run([
                "venv/bin/isort",
                "--line-length", str(self.max_line_length),
                "api/",
                "tests/"
            ], cwd=self.base_dir, check=False)

    def fix_line_length(self, content):
        """Aggressively fix long lines"""
        lines = content.split('\n')
        fixed_lines = []

        for line in lines:
            if len(line) <= self.max_line_length:
                fixed_lines.append(line)
                continue

            # Handle f-strings
            if 'f"' in line or "f'" in line:
                line = self._break_fstring(line)

            # Handle function calls with many parameters
            elif '(' in line and ')' in line and '=' in line:
                line = self._break_function_call(line)

            # Handle dictionary/list operations
            elif '{' in line or '[' in line:
                line = self._break_data_structure(line)

            # Handle string concatenation
            elif '+' in line and '"' in line:
                line = self._break_string_concat(line)

            # Handle logging statements
            elif 'logger.' in line or 'print(' in line:
                line = self._break_logging_statement(line)

            # Handle return statements
            elif line.strip().startswith('return '):
                line = self._break_return_statement(line)

            # Handle conditional statements
            elif ' and ' in line or ' or ' in line:
                line = self._break_conditional(line)

            # Last resort - break at appropriate points
            else:
                line = self._break_at_operators(line)

            fixed_lines.extend(line.split('\n') if '\n' in line else [line])

        return '\n'.join(fixed_lines)

    def _break_fstring(self, line):
        """Break f-strings at logical points"""
        if len(line) <= self.max_line_length:
            return line

        indent = len(line) - len(line.lstrip())
        indent_str = ' ' * (indent + 4)

        # Find f-string start
        if 'f"' in line:
            parts = line.split('f"')
            if len(parts) >= 2:
                prefix = parts[0]
                fstring_part = 'f"' + 'f"'.join(parts[1:])

                # Break at comma or space if possible
                if ',' in fstring_part and len(prefix + fstring_part[:40]) < self.max_line_length:
                    comma_pos = fstring_part.find(',', 20)
                    if comma_pos > 0:
                        part1 = prefix + fstring_part[:comma_pos+1]
                        part2 = indent_str + fstring_part[comma_pos+1:].lstrip()
                        return part1 + '\n' + part2

        return line

    def _break_function_call(self, line):
        """Break function calls with many parameters"""
        if len(line) <= self.max_line_length:
            return line

        indent = len(line) - len(line.lstrip())

        # Find function call pattern
        paren_pos = line.find('(')
        if paren_pos > 0:
            func_name = line[:paren_pos+1]
            params = line[paren_pos+1:].rstrip(')')

            if ',' in params:
                param_list = [p.strip() for p in params.split(',')]
                if len(param_list) > 1:
                    result = func_name + '\n'
                    for i, param in enumerate(param_list):
                        if param:
                            prefix = ' ' * (indent + 4)
                            suffix = ',' if i < len(param_list) - 1 else ''
                            result += prefix + param + suffix + '\n'
                    result += ' ' * indent + ')'
                    return result

        return line

    def _break_data_structure(self, line):
        """Break dictionaries and lists"""
        if len(line) <= self.max_line_length:
            return line

        indent = len(line) - len(line.lstrip())

        # Handle dictionary assignments
        if '= {' in line:
            parts = line.split('= {', 1)
            if len(parts) == 2:
                prefix = parts[0] + '= {'
                content = parts[1].rstrip('}')

                if ',' in content:
                    items = [item.strip() for item in content.split(',')]
                    result = prefix + '\n'
                    for i, item in enumerate(items):
                        if item:
                            item_prefix = ' ' * (indent + 4)
                            suffix = ',' if i < len(items) - 1 else ''
                            result += item_prefix + item + suffix + '\n'
                    result += ' ' * indent + '}'
                    return result

        return line

    def _break_string_concat(self, line):
        """Break string concatenation"""
        if len(line) <= self.max_line_length:
            return line

        if ' + ' in line and '"' in line:
            indent = len(line) - len(line.lstrip())
            parts = line.split(' + ')
            if len(parts) > 1:
                result = parts[0] + ' +\n'
                for i, part in enumerate(parts[1:], 1):
                    prefix = ' ' * (indent + 4)
                    suffix = ' +' if i < len(parts) - 1 else ''
                    result += prefix + part + suffix
                    if i < len(parts) - 1:
                        result += '\n'
                return result

        return line

    def _break_logging_statement(self, line):
        """Break logging statements"""
        if len(line) <= self.max_line_length:
            return line

        indent = len(line) - len(line.lstrip())

        # Handle logger.xxx(f"...") patterns
        if 'logger.' in line and '(f"' in line:
            log_start = line.find('logger.')
            paren_start = line.find('(', log_start)
            if paren_start > 0:
                prefix = line[:paren_start+1]
                message = line[paren_start+1:].rstrip(')')

                if len(prefix) + 20 < self.max_line_length:
                    return prefix + '\n' + ' ' * (indent + 4) + message + '\n' + ' ' * indent + ')'

        return line

    def _break_return_statement(self, line):
        """Break return statements"""
        if len(line) <= self.max_line_length:
            return line

        if line.strip().startswith('return '):
            indent = len(line) - len(line.lstrip())
            return_part = line[line.find('return '):line.find('return ') + 7]
            rest = line[line.find('return ') + 7:]

            if len(return_part + rest[:20]) < self.max_line_length:
                return return_part + '(\n' + ' ' * (indent + 4) + rest + '\n' + ' ' * indent + ')'

        return line

    def _break_conditional(self, line):
        """Break conditional statements"""
        if len(line) <= self.max_line_length:
            return line

        indent = len(line) - len(line.lstrip())

        if ' and ' in line:
            parts = line.split(' and ')
            if len(parts) > 1:
                result = parts[0] + ' and\n'
                for i, part in enumerate(parts[1:], 1):
                    prefix = ' ' * (indent + 4)
                    suffix = ' and' if i < len(parts) - 1 else ''
                    result += prefix + part + suffix
                    if i < len(parts) - 1:
                        result += '\n'
                return result

        elif ' or ' in line:
            parts = line.split(' or ')
            if len(parts) > 1:
                result = parts[0] + ' or\n'
                for i, part in enumerate(parts[1:], 1):
                    prefix = ' ' * (indent + 4)
                    suffix = ' or' if i < len(parts) - 1 else ''
                    result += prefix + part + suffix
                    if i < len(parts) - 1:
                        result += '\n'
                return result

        return line

    def _break_at_operators(self, line):
        """Last resort - break at operators"""
        if len(line) <= self.max_line_length:
            return line

        indent = len(line) - len(line.lstrip())

        # Try to break at various operators
        operators = [', ', ' = ', ' == ', ' != ', ' + ', ' - ', ' * ']

        for op in operators:
            if op in line:
                pos = line.rfind(op, 0, self.max_line_length - 10)
                if pos > 20:  # Don't break too early
                    part1 = line[:pos + len(op)]
                    part2 = ' ' * (indent + 4) + line[pos + len(op):].lstrip()
                    return part1 + '\n' + part2

        # If all else fails, break at a reasonable point
        pos = self.max_line_length - 10
        while pos > 20 and line[pos] not in ' ,(':
            pos -= 1

        if pos > 20:
            part1 = line[:pos].rstrip()
            part2 = ' ' * (indent + 4) + line[pos:].lstrip()
            return part1 + '\n' + part2

        return line

    def fix_spacing_issues(self, content):
        """Fix E303, E304, E305 spacing issues"""
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
                # Look at what comes after the blank lines
                next_line = lines[j] if j < len(lines) else ""

                # Look at what comes before
                prev_line = ""
                k = i - 1
                while k >= 0 and not lines[k].strip():
                    k -= 1
                if k >= 0:
                    prev_line = lines[k]

                # Determine appropriate number of blank lines
                if (next_line.startswith('class ') or
                    next_line.startswith('def ') or
                    next_line.startswith('async def ')):
                    # Before class/function definitions
                    if prev_line and not prev_line.startswith(('@', 'class ', 'def ', 'async def ')):
                        fixed_lines.extend(['', ''])  # 2 blank lines
                    else:
                        fixed_lines.append('')  # 1 blank line
                elif (prev_line.startswith('class ') or
                      (prev_line.startswith('def ') and not prev_line.strip().endswith(':')) or
                      (prev_line.startswith('async def ') and not prev_line.strip().endswith(':'))):
                    # After class/function definitions
                    fixed_lines.extend(['', ''])  # 2 blank lines
                elif '@' in prev_line:
                    # After decorators, no blank line
                    pass
                else:
                    # Regular blank line
                    if blank_count > 2:
                        fixed_lines.append('')  # Max 1 blank line for regular code
                    elif blank_count == 2 and not (next_line.startswith('class ') or next_line.startswith('def ')):
                        fixed_lines.append('')  # Reduce to 1
                    elif blank_count == 1:
                        fixed_lines.append('')  # Keep 1

                i = j
            else:
                fixed_lines.append(line)
                i += 1

        return '\n'.join(fixed_lines)

    def fix_imports(self, content):
        """Fix import placement issues (E402)"""
        lines = content.split('\n')

        # Separate docstrings, imports, and code
        docstring_lines = []
        import_lines = []
        code_lines = []

        in_docstring = False
        docstring_done = False
        imports_done = False

        for line in lines:
            stripped = line.strip()

            # Handle docstrings at the beginning
            if not docstring_done:
                if (stripped.startswith('"""') or stripped.startswith("'''")) and not in_docstring:
                    in_docstring = True
                    docstring_lines.append(line)
                elif in_docstring:
                    docstring_lines.append(line)
                    if (stripped.endswith('"""') or stripped.endswith("'''")) and len(stripped) > 3:
                        in_docstring = False
                        docstring_done = True
                elif stripped.startswith('#') or not stripped:
                    docstring_lines.append(line)
                else:
                    docstring_done = True
                    # Fall through to handle this line

            if docstring_done and not imports_done:
                if (stripped.startswith('import ') or
                    stripped.startswith('from ') or
                    not stripped or
                    stripped.startswith('#')):
                    import_lines.append(line)
                    if stripped and not stripped.startswith('#') and not stripped.startswith(('import ', 'from ')):
                        imports_done = True
                else:
                    imports_done = True
                    # Fall through to handle this line

            if imports_done or (docstring_done and not (stripped.startswith(('import ', 'from ')) or not stripped or stripped.startswith('#'))):
                code_lines.append(line)

        # Combine back together
        result = []
        result.extend(docstring_lines)
        if import_lines:
            if docstring_lines and docstring_lines[-1].strip():
                result.append('')
            result.extend(import_lines)
        if code_lines:
            if import_lines and import_lines[-1].strip():
                result.append('')
            result.extend(code_lines)

        return '\n'.join(result)

    def fix_bare_except(self, content):
        """Fix bare except statements (E722)"""
        return re.sub(
            r'except\s*:',
            'except Exception:',
            content
        )

    def fix_indentation(self, content):
        """Fix indentation issues (E128)"""
        lines = content.split('\n')
        fixed_lines = []

        for line in lines:
            if line.strip() and line.startswith(' '):
                # Check for continuation lines that need proper indentation
                if ('(' in line and
                    not line.strip().startswith(('def ', 'class ', 'if ', 'elif ', 'else:', 'for ', 'while ', 'with ', 'try:', 'except', 'finally:'))):
                    # This might be a continuation line
                    stripped = line.lstrip()
                    indent = len(line) - len(stripped)
                    # Ensure continuation lines are indented properly
                    if indent % 4 != 0:
                        new_indent = ((indent // 4) + 1) * 4
                        line = ' ' * new_indent + stripped

            fixed_lines.append(line)

        return '\n'.join(fixed_lines)

    def process_file(self, filepath):
        """Process a single file to fix all Flake8 violations"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Apply fixes in order
            content = self.fix_imports(content)
            content = self.fix_bare_except(content)
            content = self.fix_line_length(content)
            content = self.fix_spacing_issues(content)
            content = self.fix_indentation(content)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            print(f"Fixed: {filepath}")

        except Exception as e:
            print(f"Error processing {filepath}: {e}")

    def run(self):
        """Run the comprehensive fixer"""
        print("Starting comprehensive Flake8 violation fixes...")

        # Step 1: Run autoflake and isort
        self.run_autoflake()
        self.run_isort()

        # Step 2: Process all Python files
        for pattern in ['api/*.py', 'tests/*.py', 'tests/*/*.py']:
            for filepath in glob.glob(os.path.join(self.base_dir, pattern)):
                if os.path.isfile(filepath):
                    self.process_file(filepath)

        print("Comprehensive fixes complete!")

if __name__ == "__main__":
    fixer = ComprehensiveFlake8Fixer()
    fixer.run()