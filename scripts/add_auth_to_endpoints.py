#!/usr/bin/env python3
"""
Script to systematically add authentication to all API endpoints
"""
import re

def add_auth_to_endpoints():
    """Add authentication to all endpoints that need it"""

    # Read the current main.py
    with open('/opt/anime-studio/api/main.py', 'r') as f:
        content = f.read()

    # Pattern to find endpoint functions without authentication
    endpoint_patterns = [
        # POST, PUT, DELETE, PATCH operations - require auth
        (r'(@app\.(post|put|delete|patch)\([^)]+\)\s*\n)(async def \w+\([^)]*)(db: Session = Depends\(get_db\)\))',
         r'\1\2current_user: dict = Depends(require_auth), \3)'),

        # GET operations for sensitive data - require auth
        (r'(@app\.get\("/api/anime/(?:projects|characters|scenes|episodes|images|budget)[^"]*"\)[^\n]*\n)(async def \w+\([^)]*)(db: Session = Depends\(get_db\)\))',
         r'\1\2current_user: dict = Depends(require_auth), \3)'),

        # Generation endpoints - require auth
        (r'(@app\.(post|get)\("/[^"]*generate[^"]*"[^)]*\)\s*\n)(async def \w+\([^)]*)(db: Session = Depends\(get_db\)\))',
         r'\1\2current_user: dict = Depends(require_auth), \3)'),

        # Admin operations - require admin
        (r'(@app\.(post|delete)\("/api/anime/(?:projects/clear-stuck|git/)[^"]*"[^)]*\)\s*\n)(async def \w+\([^)]*)(db: Session = Depends\(get_db\)\))',
         r'\1\2current_user: dict = Depends(require_admin), \3)'),
    ]

    # Apply patterns
    modified = content
    changes_made = 0

    for pattern, replacement in endpoint_patterns:
        new_content = re.sub(pattern, replacement, modified, flags=re.MULTILINE)
        if new_content != modified:
            changes_made += re.subn(pattern, replacement, modified, flags=re.MULTILINE)[1]
            modified = new_content

    # Special cases - functions that already have parameters but need auth
    special_cases = [
        # Functions with existing parameters
        (r'(async def \w+\([^)]+)(, db: Session = Depends\(get_db\))',
         r'\1, current_user: dict = Depends(require_auth)\2'),
    ]

    # Apply to endpoints that don't already have current_user and are not health/auth endpoints
    lines = modified.split('\n')
    result_lines = []

    for i, line in enumerate(lines):
        if ('@app.' in line and
            'current_user:' not in line and
            '/health' not in line and
            '/auth/' not in line and
            ('post' in line.lower() or 'put' in line.lower() or 'delete' in line.lower() or 'patch' in line.lower())):

            # Look at next line for function definition
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if ('async def' in next_line and
                    'current_user:' not in next_line):

                    # Add auth to function parameters
                    if 'db: Session = Depends(get_db)' in next_line:
                        next_line = next_line.replace(
                            'db: Session = Depends(get_db)',
                            'current_user: dict = Depends(require_auth), db: Session = Depends(get_db)'
                        )
                        changes_made += 1

                    result_lines.append(line)
                    result_lines.append(next_line)
                    i += 1  # Skip the next line since we processed it
                    continue

        result_lines.append(line)

    final_content = '\n'.join(result_lines)

    # Write back the modified content
    with open('/opt/anime-studio/api/main.py', 'w') as f:
        f.write(final_content)

    print(f"✅ Added authentication to {changes_made} endpoints")
    return changes_made

if __name__ == "__main__":
    add_auth_to_endpoints()