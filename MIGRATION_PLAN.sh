#!/bin/bash
# Tower Anime Production - Safe Migration Plan
# Date: December 5, 2025
# Purpose: Preserve valuable code while cleaning up the mess

set -e

echo "🎬 Tower Anime Production Migration Plan"
echo "========================================"
echo ""

# Configuration
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SOURCE_DIR="/opt/tower-anime-production"
ARCHIVE_DIR="/opt/anime-archives/archive_${TIMESTAMP}"
NEW_DIR="/opt/anime-v3"
PRESERVED_DIR="${NEW_DIR}/preserved"

# Step 1: Create archive for safety
echo "📦 Step 1: Creating safety archive..."
echo "This will take a while (9.5GB to compress)..."
mkdir -p /opt/anime-archives
tar -czf "/opt/anime-archives/anime_full_backup_${TIMESTAMP}.tar.gz" "$SOURCE_DIR" 2>/dev/null || true
echo "✅ Full backup created: /opt/anime-archives/anime_full_backup_${TIMESTAMP}.tar.gz"
echo ""

# Step 2: Create new structure
echo "🏗️ Step 2: Creating new v3 structure..."
mkdir -p "$NEW_DIR"/{api,character,quality,workflow,database,config,preserved}
mkdir -p "$NEW_DIR"/workflow/{templates,projects}
mkdir -p "$NEW_DIR"/config/workflows
echo "✅ New directory structure created"
echo ""

# Step 3: Preserve valuable components
echo "💎 Step 3: Preserving valuable components..."

# Core components to preserve
echo "  - Preserving character consistency system..."
cp -r "$SOURCE_DIR"/src/ "$PRESERVED_DIR"/ 2>/dev/null || true
cp "$SOURCE_DIR"/character_consistency_engine.py "$PRESERVED_DIR"/ 2>/dev/null || true
cp "$SOURCE_DIR"/v2_integration.py "$PRESERVED_DIR"/ 2>/dev/null || true

echo "  - Preserving workflows..."
cp -r "$SOURCE_DIR"/workflows/ "$PRESERVED_DIR"/ 2>/dev/null || true

echo "  - Preserving database schemas..."
mkdir -p "$PRESERVED_DIR"/database
PGPASSWORD=tower_echo_brain_secret_key_2025 pg_dump -h localhost -U patrick -d anime_production --schema-only > "$PRESERVED_DIR"/database/schema.sql

echo "  - Preserving running API..."
cp "$SOURCE_DIR"/api/secured_api.py "$PRESERVED_DIR"/ 2>/dev/null || true

echo "✅ Valuable components preserved"
echo ""

# Step 4: Extract and organize key files
echo "🔧 Step 4: Creating clean v3 implementation..."

# Create main API file combining secured_api + v2_integration
cat > "$NEW_DIR"/api/main.py << 'EOF'
#!/usr/bin/env python3
"""
Anime Production API v3.0
Unified, clean implementation with v2.0 tracking
"""

# This will be the merged implementation of:
# - /api/secured_api.py (currently running)
# - v2_integration.py (quality tracking)
# - Essential monitoring features
# Port: 8331
EOF

# Copy essential modules
echo "  - Setting up character module..."
cp "$SOURCE_DIR"/character_consistency_engine.py "$NEW_DIR"/character/engine.py 2>/dev/null || true
[ -f "$SOURCE_DIR"/src/character_bible_db.py ] && cp "$SOURCE_DIR"/src/character_bible_db.py "$NEW_DIR"/character/bible.py

echo "  - Setting up quality module..."
[ -f "$SOURCE_DIR"/src/quality_gates.py ] && cp "$SOURCE_DIR"/src/quality_gates.py "$NEW_DIR"/quality/gates.py
cp "$SOURCE_DIR"/v2_integration.py "$NEW_DIR"/quality/tracking.py 2>/dev/null || true

echo "  - Setting up workflow templates..."
cp -r "$SOURCE_DIR"/workflows/comfyui/*.json "$NEW_DIR"/workflow/templates/ 2>/dev/null || true

echo "✅ Clean v3 structure created"
echo ""

# Step 5: Create service file
echo "📝 Step 5: Creating systemd service..."
cat > "$NEW_DIR"/anime-production.service << 'EOF'
[Unit]
Description=Anime Production API v3
After=network.target postgresql.service

[Service]
Type=simple
User=patrick
WorkingDirectory=/opt/anime-v3
Environment="PYTHONPATH=/opt/anime-v3"
ExecStart=/opt/anime-v3/venv/bin/python /opt/anime-v3/api/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
echo "✅ Service file created"
echo ""

# Step 6: Create requirements.txt
echo "📦 Step 6: Creating clean requirements..."
cat > "$NEW_DIR"/requirements.txt << 'EOF'
# Core dependencies only
fastapi==0.104.1
uvicorn==0.24.0
httpx==0.25.0
psycopg2-binary==2.9.7
asyncpg==0.29.0
pydantic==2.5.0
python-dotenv==1.0.0
redis==5.0.1
pillow==10.1.0
numpy==1.26.0
websockets==12.0
EOF
echo "✅ Clean requirements file created"
echo ""

# Step 7: Summary report
echo "📊 Migration Summary"
echo "==================="
echo ""
echo "Original size: $(du -sh $SOURCE_DIR | cut -f1)"
echo "Preserved components: $(du -sh $PRESERVED_DIR 2>/dev/null | cut -f1 || echo '0')"
echo "New v3 size: $(du -sh $NEW_DIR | cut -f1)"
echo ""
echo "Files preserved:"
find "$PRESERVED_DIR" -type f -name "*.py" 2>/dev/null | wc -l | xargs echo "  - Python files:"
find "$PRESERVED_DIR" -type f -name "*.json" 2>/dev/null | wc -l | xargs echo "  - Workflow JSONs:"
echo ""
echo "Running services to stop:"
echo "  - file_organizer.py (PID: 2833799)"
echo "  - completion_tracking_fix.py (PID: 2833800)"
echo "  - worker.py (PID: 2833801)"
echo "  - postgresql_monitor.py (PID: 2833802)"
echo "  - websocket_progress.py (PID: 2833803)"
echo ""
echo "Keep running:"
echo "  - secured_api.py on port 8331 (PID: 3850631)"
echo "  - production_monitor.py (PID: 2227421)"
echo ""

# Step 8: Next steps
echo "🚀 Next Steps"
echo "============"
echo ""
echo "1. Review preserved components:"
echo "   ls -la $PRESERVED_DIR"
echo ""
echo "2. Stop redundant services:"
echo "   kill 2833799 2833800 2833801 2833802 2833803"
echo ""
echo "3. Complete the v3 API implementation:"
echo "   cd $NEW_DIR"
echo "   # Merge secured_api.py with v2_integration"
echo ""
echo "4. Create virtual environment:"
echo "   python3 -m venv $NEW_DIR/venv"
echo "   source $NEW_DIR/venv/bin/activate"
echo "   pip install -r requirements.txt"
echo ""
echo "5. Test the new implementation:"
echo "   python api/main.py"
echo ""
echo "6. Once verified, remove old directory:"
echo "   # rm -rf $SOURCE_DIR  # ONLY after thorough testing!"
echo ""
echo "✅ Migration plan ready. Run this script to execute."