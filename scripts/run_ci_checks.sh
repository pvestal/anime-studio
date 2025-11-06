#!/bin/bash
# CI Checks for Anime Production System
# Run this before committing changes

set -e  # Exit on any error

echo "🧪 Anime Production CI Checks"
echo "=============================="

# Change to project directory
cd "$(dirname "$0")/.."

# Create logs directory if it doesn't exist
mkdir -p logs

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ $2${NC}"
    else
        echo -e "${RED}❌ $2${NC}"
    fi
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

echo
echo "📋 1. Checking critical files..."
if [ -f "workflows/comfyui/anime_30sec_standard.json" ]; then
    print_status 0 "Main workflow file exists"
else
    print_status 1 "Main workflow file missing"
    exit 1
fi

if [ -f "anime_api.py" ]; then
    print_status 0 "Main API file exists"
else
    print_status 1 "Main API file missing"
    exit 1
fi

echo
echo "🐍 2. Python syntax validation..."
syntax_errors=0

for py_file in $(find . -name "*.py" -not -path "./venv/*" -not -path "./.git/*"); do
    if ! python3 -m py_compile "$py_file" 2>/dev/null; then
        print_status 1 "Syntax error in $py_file"
        syntax_errors=$((syntax_errors + 1))
    fi
done

if [ $syntax_errors -eq 0 ]; then
    print_status 0 "All Python files have valid syntax"
else
    print_status 1 "$syntax_errors Python files have syntax errors"
    exit 1
fi

echo
echo "📋 3. JSON workflow validation..."
json_errors=0

for json_file in $(find workflows/ -name "*.json" 2>/dev/null || true); do
    if [ -f "$json_file" ]; then
        if ! python3 -m json.tool "$json_file" > /dev/null 2>&1; then
            print_status 1 "Invalid JSON: $json_file"
            json_errors=$((json_errors + 1))
        fi
    fi
done

if [ $json_errors -eq 0 ]; then
    print_status 0 "All JSON files are valid"
else
    print_status 1 "$json_errors JSON files have errors"
    exit 1
fi

echo
echo "🏥 4. Service health checks..."

# Check ComfyUI
if curl -s http://127.0.0.1:8188/system_stats > /dev/null 2>&1; then
    print_status 0 "ComfyUI service is running"
else
    print_warning "ComfyUI service not accessible (may be expected in CI)"
fi

# Check Anime API
if curl -s http://127.0.0.1:8328/api/anime/health > /dev/null 2>&1; then
    print_status 0 "Anime API service is running"
else
    print_warning "Anime API service not accessible (may be expected in CI)"
fi

echo
echo "🧪 5. Running system tests..."

# Run the comprehensive test suite if services are available
if curl -s http://127.0.0.1:8188/system_stats > /dev/null 2>&1 && curl -s http://127.0.0.1:8328/health > /dev/null 2>&1; then
    echo "Running full test suite..."
    if python3 tests/test_complete_system.py; then
        print_status 0 "Comprehensive tests passed"
    else
        print_status 1 "Comprehensive tests failed"
        exit 1
    fi
else
    echo "Services not available - running basic tests only..."

    # Basic import tests
    if python3 -c "
import sys
sys.path.insert(0, '.')
try:
    import anime_api
    import comfyui_connector
    print('✅ Basic imports successful')
except ImportError as e:
    print(f'❌ Import error: {e}')
    sys.exit(1)
"; then
        print_status 0 "Basic import tests passed"
    else
        print_status 1 "Basic import tests failed"
        exit 1
    fi
fi

echo
echo "🎯 6. Git status check..."
if git diff --cached --quiet; then
    print_warning "No files staged for commit"
else
    staged_files=$(git diff --cached --name-only | wc -l)
    print_status 0 "$staged_files files staged for commit"
fi

echo
echo "=============================="
echo -e "${GREEN}🎉 All CI checks passed!${NC}"
echo "Ready to commit changes."