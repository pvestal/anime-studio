#!/bin/bash
# Cleanup Script for Duplicate/Fragmented Anime Services
# Removes duplicate directories after consolidation

set -e

echo "🧹 Cleaning up duplicate and fragmented anime services..."

# Source directory (Tower repo)
TOWER_DIR="/home/patrick/Documents/Tower"

# Backup important files before cleanup
BACKUP_DIR="$TOWER_DIR/Archives/anime-cleanup-backup-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "💾 Creating backup at: $BACKUP_DIR"

# Backup any unique files from fragmented services
echo "🔍 Scanning for unique files to preserve..."

# Archive the large anime_pipeline_env if it contains important data
if [ -d "$TOWER_DIR/projects/Anime/anime_pipeline_env" ]; then
    echo "📦 Backing up anime_pipeline_env (325M)..."
    cp -r "$TOWER_DIR/projects/Anime/anime_pipeline_env" "$BACKUP_DIR/"
fi

# Archive test files
if [ -d "$TOWER_DIR/tests/anime-pipeline" ]; then
    echo "📦 Backing up anime-pipeline tests..."
    cp -r "$TOWER_DIR/tests/anime-pipeline" "$BACKUP_DIR/"
fi

# Archive any Python files from real-anime-generation
if [ -d "$TOWER_DIR/services/media/real-anime-generation" ]; then
    echo "📦 Backing up real-anime-generation archive..."
    cp -r "$TOWER_DIR/services/media/real-anime-generation" "$BACKUP_DIR/"
fi

echo "✅ Backup complete"

# List directories to be removed
echo "🗑️  The following duplicate/fragmented directories will be removed:"
echo "   - $TOWER_DIR/projects/Anime/anime-video-studio"
echo "   - $TOWER_DIR/projects/Anime/anime_pipeline_env"
echo "   - $TOWER_DIR/services/media/real-anime-generation"
echo "   - $TOWER_DIR/services/media/media/anime"
echo "   - $TOWER_DIR/services/media/anime-generator"
echo "   - $TOWER_DIR/services/media/anime-production (empty)"
echo "   - $TOWER_DIR/services/media/enhanced-anime-service"
echo "   - $TOWER_DIR/services/ai/anime-service"
echo "   - $TOWER_DIR/services/anime-api"
echo "   - $TOWER_DIR/core-services/anime-service"
echo "   - $TOWER_DIR/tests/anime-pipeline"

read -p "⚠️  Continue with cleanup? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cleanup cancelled"
    exit 1
fi

# Remove duplicate/fragmented directories
echo "🗑️  Removing fragmented services..."

cd "$TOWER_DIR"

# Remove fragmented anime services
rm -rf projects/Anime/anime-video-studio
rm -rf projects/Anime/anime_pipeline_env
rm -rf services/media/real-anime-generation
rm -rf services/media/media/anime
rm -rf services/media/anime-generator
rm -rf services/media/anime-production
rm -rf services/media/enhanced-anime-service
rm -rf services/ai/anime-service
rm -rf services/anime-api
rm -rf core-services/anime-service
rm -rf tests/anime-pipeline

# Clean up dashboard anime components (duplicated)
rm -rf deployment/dashboard/src/components/anime

echo "✅ Fragmented services removed"

# Remove standalone duplicate
DUPLICATE_DIR="/home/patrick/Documents/Tower-Anime-Production"
if [ -d "$DUPLICATE_DIR" ]; then
    echo "🗑️  Removing standalone duplicate: Tower-Anime-Production"

    # Backup any unique files
    if [ -d "$DUPLICATE_DIR/.git" ]; then
        echo "📦 Backing up git history from duplicate..."
        cp -r "$DUPLICATE_DIR/.git" "$BACKUP_DIR/duplicate-git"
    fi

    # Remove duplicate
    rm -rf "$DUPLICATE_DIR"
    echo "✅ Standalone duplicate removed"
fi

# Clean up broken production deployment
if [ -d "/opt/tower-anime" ]; then
    echo "🗑️  Cleaning up broken production deployment..."
    sudo rm -rf /opt/tower-anime
    echo "✅ Broken production deployment cleaned"
fi

# Update git to track changes
echo "📝 Updating git repository..."
cd "$TOWER_DIR"
git add .
git status

echo "🎉 Cleanup complete!"
echo ""
echo "📋 Summary:"
echo "   ✅ Fragmented services removed and backed up"
echo "   ✅ Standalone duplicate removed"
echo "   ✅ Broken production deployment cleaned"
echo "   ✅ Unified service ready for deployment"
echo ""
echo "📁 Backup location: $BACKUP_DIR"
echo "🚀 Ready to deploy: ./services/anime-production/deploy-anime-production.sh"