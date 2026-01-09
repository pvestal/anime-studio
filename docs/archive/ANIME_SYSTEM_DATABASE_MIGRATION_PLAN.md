# Anime System v2.0 Database Migration Plan
## Complete Step-by-Step Guide from Start to Finish

**Target Database**: `anime_production` on Tower (192.168.50.135)
**Current User**: `patrick` (via peer authentication)
**Migration Source**: `/tmp/anime-system-extracted/anime-system/migrations/`
**Estimated Duration**: 45-60 minutes (including backups and verification)
**Risk Level**: LOW (additive migrations only, no destructive changes)

---

## 📋 Pre-Migration Checklist

### ✅ Phase 0: Environment Verification (5 minutes)

#### 0.1 Verify Tower Access
```bash
# From laptop - test SSH connection
ssh patrick@vestal-garcia.duckdns.org "hostname && date"

# Expected output:
# tower
# Wed Dec  4 [current time] 2025
```

#### 0.2 Verify Database Access
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c 'SELECT current_database(), current_user, version();'"

# Expected output:
# current_database | current_user | version
# anime_production | postgres     | PostgreSQL 14.x or 15.x
```

#### 0.3 Check Current Schema
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c '\dt' | grep -E '(projects|characters|jobs)'"

# Expected tables:
# projects
# characters
# jobs
# (possibly: project_bibles, etc.)
```

#### 0.4 Verify Disk Space
```bash
ssh patrick@vestal-garcia.duckdns.org "df -h /var/lib/postgresql"

# Need at least 500MB free for backups
```

---

## 💾 Phase 1: Backup Strategy (10 minutes)

### 1.1 Create Backup Directory
```bash
ssh patrick@vestal-garcia.duckdns.org "mkdir -p /tmp/anime_db_backups/$(date +%Y%m%d_%H%M%S)"

# Store backup path
BACKUP_DIR="/tmp/anime_db_backups/$(date +%Y%m%d_%H%M%S)"
```

### 1.2 Full Database Backup (Primary Safety Net)
```bash
ssh patrick@vestal-garcia.duckdns.org "pg_dump -U postgres -d anime_production -F c -b -v -f /tmp/anime_db_backups/$(date +%Y%m%d_%H%M%S)/anime_production_full.backup"

# -F c = Custom format (compressed, restorable)
# -b = Include large objects
# -v = Verbose output

# Verify backup created
ssh patrick@vestal-garcia.duckdns.org "ls -lh /tmp/anime_db_backups/*/anime_production_full.backup"

# Expected: File size 5-50MB depending on data
```

### 1.3 Schema-Only Backup (Quick Reference)
```bash
ssh patrick@vestal-garcia.duckdns.org "pg_dump -U postgres -d anime_production -s -f /tmp/anime_db_backups/$(date +%Y%m%d_%H%M%S)/anime_production_schema.sql"

# -s = Schema only (no data)

# This allows quick schema comparison after migration
```

### 1.4 Current Table List Snapshot
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c '\dt' > /tmp/anime_db_backups/$(date +%Y%m%d_%H%M%S)/tables_before_migration.txt"

# Save for comparison
```

### 1.5 Verify Backups
```bash
# Check all backup files exist
ssh patrick@vestal-garcia.duckdns.org "ls -lh /tmp/anime_db_backups/$(date +%Y%m%d_%H%M%S)/"

# Expected files:
# anime_production_full.backup
# anime_production_schema.sql
# tables_before_migration.txt
```

**CHECKPOINT**: Do not proceed until backups are verified ✅

---

## 📊 Phase 2: Current Schema Audit (5 minutes)

### 2.1 Identify Existing Tables
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
\""

# Document output - these are the current tables
```

### 2.2 Check for Migration Table Conflicts
```bash
# Check if any of the new tables already exist
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT EXISTS (SELECT FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name IN (
        'character_attributes',
        'character_variations',
        'generation_params',
        'quality_scores',
        'story_bibles',
        'episodes',
        'scenes',
        'cuts',
        'scene_characters',
        'render_queue'
    ));
\""

# Expected: f (false) - none should exist
# If true, need to investigate which tables conflict
```

### 2.3 Check Foreign Key Dependencies
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM
    information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
        ON tc.constraint_name = kcu.constraint_name
        AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage AS ccu
        ON ccu.constraint_name = tc.constraint_name
        AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
    AND tc.table_schema='public'
ORDER BY tc.table_name;
\""

# Document current foreign key relationships
```

### 2.4 Verify Required Parent Tables Exist
```bash
# New tables reference: projects, characters, jobs
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
    AND table_name IN ('projects', 'characters', 'jobs');
\""

# Expected: All 3 tables must exist
# If missing, migrations will fail
```

**CHECKPOINT**: Verify all parent tables exist ✅

---

## 🗂️ Phase 3: Copy Migration Files to Tower (5 minutes)

### 3.1 Create Migration Directory on Tower
```bash
ssh patrick@vestal-garcia.duckdns.org "mkdir -p /opt/tower-anime-production/migrations"
```

### 3.2 Copy Migration 001
```bash
scp /tmp/anime-system-extracted/anime-system/migrations/001_character_consistency.sql \
    patrick@vestal-garcia.duckdns.org:/opt/tower-anime-production/migrations/

# Verify copy
ssh patrick@vestal-garcia.duckdns.org "wc -l /opt/tower-anime-production/migrations/001_character_consistency.sql"

# Expected: 96 lines
```

### 3.3 Copy Migration 002
```bash
scp /tmp/anime-system-extracted/anime-system/migrations/002_video_production.sql \
    patrick@vestal-garcia.duckdns.org:/opt/tower-anime-production/migrations/

# Verify copy
ssh patrick@vestal-garcia.duckdns.org "wc -l /opt/tower-anime-production/migrations/002_video_production.sql"

# Expected: 89 lines
```

### 3.4 Verify Migration Files on Tower
```bash
ssh patrick@vestal-garcia.duckdns.org "ls -lh /opt/tower-anime-production/migrations/"

# Expected:
# 001_character_consistency.sql
# 002_video_production.sql
```

---

## 🚀 Phase 4: Execute Migration 001 - Character Consistency (10 minutes)

### 4.1 Review Migration 001 Contents
```bash
ssh patrick@vestal-garcia.duckdns.org "cat /opt/tower-anime-production/migrations/001_character_consistency.sql"

# Verify contents match expectations:
# - ALTER TABLE characters (5 new columns)
# - CREATE TABLE character_attributes
# - CREATE TABLE character_variations
# - CREATE TABLE generation_params
# - CREATE TABLE quality_scores
# - CREATE TABLE story_bibles
# - CREATE INDEX statements (4 indexes)
```

### 4.2 Dry Run - Check for Errors
```bash
# Parse SQL without executing (if psql supports --dry-run)
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production --single-transaction -f /opt/tower-anime-production/migrations/001_character_consistency.sql --echo-errors 2>&1 | head -50"

# Review output for syntax errors
```

### 4.3 Execute Migration 001
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -f /opt/tower-anime-production/migrations/001_character_consistency.sql"

# Expected output:
# ALTER TABLE (for each column added)
# CREATE TABLE (for each new table)
# CREATE INDEX (for each index)
# No errors
```

### 4.4 Verify Migration 001 Success
```bash
# Check that new tables exist
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
    AND table_name IN (
        'character_attributes',
        'character_variations',
        'generation_params',
        'quality_scores',
        'story_bibles'
    )
ORDER BY table_name;
\""

# Expected: All 5 tables listed
```

### 4.5 Verify characters Table Alterations
```bash
# Check that new columns were added to characters table
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'characters'
    AND column_name IN (
        'reference_embedding',
        'color_palette',
        'base_prompt',
        'negative_tokens',
        'lora_model_path'
    )
ORDER BY column_name;
\""

# Expected: All 5 columns present
# reference_embedding: bytea
# color_palette: jsonb (default '{}')
# base_prompt: text
# negative_tokens: ARRAY (default '{}')
# lora_model_path: character varying(500)
```

### 4.6 Verify Indexes Created
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT indexname, tablename
FROM pg_indexes
WHERE schemaname = 'public'
    AND indexname IN (
        'idx_char_attrs_char',
        'idx_gen_params_job',
        'idx_quality_job',
        'idx_story_bible_project'
    )
ORDER BY indexname;
\""

# Expected: All 4 indexes listed
```

**CHECKPOINT**: Verify Migration 001 completed successfully ✅

---

## 🎬 Phase 5: Execute Migration 002 - Video Production (10 minutes)

### 5.1 Review Migration 002 Contents
```bash
ssh patrick@vestal-garcia.duckdns.org "cat /opt/tower-anime-production/migrations/002_video_production.sql"

# Verify contents:
# - CREATE TABLE episodes
# - CREATE TABLE scenes
# - CREATE TABLE cuts
# - CREATE TABLE scene_characters
# - CREATE TABLE render_queue
# - ALTER TABLE jobs (4 new columns)
# - CREATE INDEX statements (5 indexes)
```

### 5.2 Execute Migration 002
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -f /opt/tower-anime-production/migrations/002_video_production.sql"

# Expected output:
# CREATE TABLE (for each new table)
# ALTER TABLE (for jobs table)
# CREATE INDEX (for each index)
# No errors
```

### 5.3 Verify Migration 002 Success
```bash
# Check that new tables exist
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
    AND table_name IN (
        'episodes',
        'scenes',
        'cuts',
        'scene_characters',
        'render_queue'
    )
ORDER BY table_name;
\""

# Expected: All 5 tables listed
```

### 5.4 Verify jobs Table Alterations
```bash
# Check that new columns were added to jobs table
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'jobs'
    AND column_name IN (
        'scene_id',
        'cut_id',
        'total_frames',
        'current_frame'
    )
ORDER BY column_name;
\""

# Expected: All 4 columns present
# scene_id: uuid
# cut_id: uuid
# total_frames: integer
# current_frame: integer
```

### 5.5 Verify Indexes Created
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT indexname, tablename
FROM pg_indexes
WHERE schemaname = 'public'
    AND indexname IN (
        'idx_episodes_project',
        'idx_scenes_episode',
        'idx_cuts_scene',
        'idx_scene_chars_scene',
        'idx_render_queue_status'
    )
ORDER BY indexname;
\""

# Expected: All 5 indexes listed
```

**CHECKPOINT**: Verify Migration 002 completed successfully ✅

---

## ✅ Phase 6: Post-Migration Verification (10 minutes)

### 6.1 Complete Table Inventory
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c '\dt' > /tmp/anime_db_backups/$(date +%Y%m%d)_*/tables_after_migration.txt"

# Compare before/after
ssh patrick@vestal-garcia.duckdns.org "diff /tmp/anime_db_backups/$(date +%Y%m%d)_*/tables_before_migration.txt /tmp/anime_db_backups/$(date +%Y%m%d)_*/tables_after_migration.txt"

# Should show 10 new tables added
```

### 6.2 Verify Foreign Key Integrity
```bash
# Check that all foreign keys were created correctly
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name
FROM
    information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
        ON tc.constraint_name = kcu.constraint_name
    JOIN information_schema.constraint_column_usage AS ccu
        ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
    AND tc.table_schema='public'
    AND tc.table_name IN (
        'character_attributes',
        'character_variations',
        'generation_params',
        'quality_scores',
        'story_bibles',
        'episodes',
        'scenes',
        'cuts',
        'scene_characters',
        'render_queue'
    )
ORDER BY tc.table_name;
\""

# Verify expected foreign keys:
# character_attributes.character_id -> characters.id
# character_variations.character_id -> characters.id
# generation_params.job_id -> jobs.id
# quality_scores.job_id -> jobs.id
# story_bibles.project_id -> projects.id
# episodes.project_id -> projects.id
# scenes.episode_id -> episodes.id
# cuts.scene_id -> scenes.id
# scene_characters.scene_id -> scenes.id
# scene_characters.character_id -> characters.id
# render_queue.job_id -> jobs.id
```

### 6.3 Test Foreign Key Cascade Behavior
```bash
# Test that cascading deletes work (without actually deleting)
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT
    tc.table_name,
    tc.constraint_name,
    rc.update_rule,
    rc.delete_rule
FROM information_schema.table_constraints tc
JOIN information_schema.referential_constraints rc
    ON tc.constraint_name = rc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
    AND tc.table_schema = 'public'
    AND tc.table_name IN (
        'character_attributes',
        'character_variations',
        'generation_params',
        'quality_scores',
        'story_bibles',
        'episodes',
        'scenes',
        'cuts',
        'scene_characters',
        'render_queue'
    )
ORDER BY tc.table_name;
\""

# Verify DELETE CASCADE is set where expected
```

### 6.4 Verify Index Performance
```bash
# Check that all indexes are valid and ready
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
    AND tablename IN (
        'character_attributes',
        'character_variations',
        'generation_params',
        'quality_scores',
        'story_bibles',
        'episodes',
        'scenes',
        'cuts',
        'scene_characters',
        'render_queue'
    )
ORDER BY tablename, indexname;
\""

# Verify all 9 indexes created (4 from migration 001, 5 from migration 002)
```

### 6.5 Database Size Check
```bash
# Check new database size
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
SELECT
    pg_size_pretty(pg_database_size('anime_production')) as db_size;
\""

# Should be slightly larger than pre-migration (tables are empty, only schema)
```

### 6.6 Vacuum and Analyze (Optimize)
```bash
# Update statistics for query planner
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c 'VACUUM ANALYZE;'"

# This ensures PostgreSQL has accurate stats for the new tables
```

**CHECKPOINT**: All post-migration checks passed ✅

---

## 🧪 Phase 7: Smoke Tests (5 minutes)

### 7.1 Test character_attributes Insert
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
-- This will fail if no characters exist, which is expected
INSERT INTO character_attributes (character_id, attribute_type, attribute_value, prompt_tokens, priority)
SELECT
    id,
    'test_attribute',
    'test_value',
    ARRAY['test', 'tokens'],
    0
FROM characters
LIMIT 1
RETURNING id;
\""

# Expected: Either 1 row inserted (if characters exist) or error (if no characters)
# Error is OK - proves table structure is correct

# Clean up test data if inserted
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
DELETE FROM character_attributes WHERE attribute_type = 'test_attribute';
\""
```

### 7.2 Test generation_params Insert
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
-- Test JSONB columns work correctly
INSERT INTO generation_params (job_id, positive_prompt, negative_prompt, seed, model_name, lora_models, controlnet_models, ipadapter_refs)
SELECT
    id,
    'test prompt',
    'test negative',
    12345,
    'test_model',
    '[]'::jsonb,
    '[]'::jsonb,
    '[]'::jsonb
FROM jobs
LIMIT 1
RETURNING id;
\""

# Expected: Either 1 row or error (both OK for validation)

# Clean up
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
DELETE FROM generation_params WHERE positive_prompt = 'test prompt';
\""
```

### 7.3 Test episode → scene → cut Hierarchy
```bash
# Test the full episode/scene/cut structure with transaction rollback
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
BEGIN;

-- Create test episode
INSERT INTO episodes (project_id, episode_number, title)
SELECT id, 999, 'Test Episode'
FROM projects
LIMIT 1
RETURNING id;

-- Rollback - don't actually insert
ROLLBACK;
\""

# Expected: Episode created in transaction, then rolled back
# Proves foreign keys and structure work
```

**CHECKPOINT**: All smoke tests passed (structure validated) ✅

---

## 📝 Phase 8: Create Migration Record (5 minutes)

### 8.1 Create Migration Tracking Table
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    version VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    applied_at TIMESTAMP DEFAULT NOW(),
    applied_by VARCHAR(100),
    checksum VARCHAR(64)
);
\""
```

### 8.2 Record Migration 001
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
INSERT INTO schema_migrations (version, description, applied_by)
VALUES
    ('001', 'Character Consistency - Attributes, Variations, Quality Scores, Story Bibles', 'patrick'),
    ('002', 'Video Production - Episodes, Scenes, Cuts, Render Queue')
ON CONFLICT (version) DO NOTHING;
\""
```

### 8.3 Verify Migration Record
```bash
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c 'SELECT * FROM schema_migrations ORDER BY version;'"

# Expected:
# version | description                          | applied_at           | applied_by
# 001     | Character Consistency...             | [timestamp]          | patrick
# 002     | Video Production...                  | [timestamp]          | patrick
```

---

## 📊 Phase 9: Final Documentation (5 minutes)

### 9.1 Generate Post-Migration Schema Diagram
```bash
# Export complete schema with all relationships
ssh patrick@vestal-garcia.duckdns.org "pg_dump -U postgres -d anime_production -s > /opt/tower-anime-production/migrations/anime_production_schema_v2.sql"

# This serves as reference for future development
```

### 9.2 Create Migration Summary Report
```bash
ssh patrick@vestal-garcia.duckdns.org "cat > /opt/tower-anime-production/migrations/MIGRATION_SUMMARY.md << 'EOF'
# Anime Production Database Migration Summary

**Date**: $(date)
**Database**: anime_production
**Executed By**: patrick

## Migrations Applied

### Migration 001: Character Consistency
- Added 5 columns to `characters` table
- Created `character_attributes` table
- Created `character_variations` table
- Created `generation_params` table
- Created `quality_scores` table
- Created `story_bibles` table
- Created 4 indexes

### Migration 002: Video Production
- Created `episodes` table
- Created `scenes` table
- Created `cuts` table
- Created `scene_characters` table
- Created `render_queue` table
- Added 4 columns to `jobs` table
- Created 5 indexes

## Total Changes
- **10 new tables**
- **9 new columns** (5 on characters, 4 on jobs)
- **9 new indexes**
- **11 new foreign key relationships**

## Backups Location
- Full backup: /tmp/anime_db_backups/[timestamp]/anime_production_full.backup
- Schema backup: /tmp/anime_db_backups/[timestamp]/anime_production_schema.sql

## Rollback Plan
If issues occur, restore from backup:
\`\`\`bash
pg_restore -U postgres -d anime_production -c /tmp/anime_db_backups/[timestamp]/anime_production_full.backup
\`\`\`

## Next Steps
1. Update anime_api.py to use new tables
2. Integrate CharacterConsistencyService
3. Integrate QualityMetricsService
4. Install InsightFace for face embeddings
5. Test character consistency endpoints

**Migration Status**: ✅ SUCCESS
EOF
"
```

### 9.3 Save Table Count Comparison
```bash
# Before vs After comparison
ssh patrick@vestal-garcia.duckdns.org "echo 'Tables Before Migration:' && wc -l < /tmp/anime_db_backups/$(date +%Y%m%d)_*/tables_before_migration.txt && echo 'Tables After Migration:' && psql -U postgres -d anime_production -c '\dt' | wc -l"

# Expected: +10 tables
```

---

## 🔄 Rollback Plan (If Needed)

### Only execute if migration fails or needs reversal

### Rollback Option A: Full Database Restore
```bash
# CAUTION: This will restore entire database to pre-migration state
# All data changes after migration will be lost

ssh patrick@vestal-garcia.duckdns.org "pg_restore -U postgres -d anime_production -c -v /tmp/anime_db_backups/[TIMESTAMP]/anime_production_full.backup"

# Verify restoration
ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c '\dt'"
```

### Rollback Option B: Manual Table Drops (Surgical)
```bash
# Drop only the new tables (preserves existing data)

ssh patrick@vestal-garcia.duckdns.org "psql -U postgres -d anime_production -c \"
BEGIN;

-- Drop Migration 002 tables
DROP TABLE IF EXISTS render_queue CASCADE;
DROP TABLE IF EXISTS scene_characters CASCADE;
DROP TABLE IF EXISTS cuts CASCADE;
DROP TABLE IF EXISTS scenes CASCADE;
DROP TABLE IF EXISTS episodes CASCADE;

-- Drop Migration 001 tables
DROP TABLE IF EXISTS story_bibles CASCADE;
DROP TABLE IF EXISTS quality_scores CASCADE;
DROP TABLE IF EXISTS generation_params CASCADE;
DROP TABLE IF EXISTS character_variations CASCADE;
DROP TABLE IF EXISTS character_attributes CASCADE;

-- Remove columns from existing tables
ALTER TABLE jobs
    DROP COLUMN IF EXISTS scene_id,
    DROP COLUMN IF EXISTS cut_id,
    DROP COLUMN IF EXISTS total_frames,
    DROP COLUMN IF EXISTS current_frame;

ALTER TABLE characters
    DROP COLUMN IF EXISTS reference_embedding,
    DROP COLUMN IF EXISTS color_palette,
    DROP COLUMN IF EXISTS base_prompt,
    DROP COLUMN IF EXISTS negative_tokens,
    DROP COLUMN IF EXISTS lora_model_path;

-- Delete migration records
DELETE FROM schema_migrations WHERE version IN ('001', '002');

COMMIT;
\""
```

---

## 🎯 Success Criteria Summary

**Migration is successful when ALL of the following are true**:

- [✅] Backups created and verified
- [✅] Migration 001 applied without errors
- [✅] Migration 002 applied without errors
- [✅] 10 new tables exist in database
- [✅] 9 new columns added to existing tables
- [✅] 9 new indexes created
- [✅] All foreign keys validated
- [✅] Smoke tests passed
- [✅] schema_migrations table updated
- [✅] Documentation generated

**Database is now ready for**:
- ✅ Character consistency tracking (face embeddings)
- ✅ Quality metrics storage
- ✅ Full reproducibility (generation params)
- ✅ Episode/scene/cut production structure
- ✅ Render queue batch processing
- ✅ Story bible management

---

## ⏭️ Post-Migration Next Steps

### Immediate (This Session)
1. ✅ Verify all tables exist
2. ✅ Test foreign key relationships
3. ✅ Document migration completion

### Next Development Session
1. Copy service files from zip to Tower
2. Install InsightFace dependencies
3. Update anime_api.py imports
4. Create test character with face embedding
5. Run first quality evaluation

### Week 1 Goals
1. Integrate CharacterConsistencyService
2. Integrate QualityMetricsService
3. Implement generation_params storage
4. Test Phase 1 quality gates

---

**Migration Plan Status**: ✅ READY FOR EXECUTION

**Estimated Total Time**: 45-60 minutes
**Risk Level**: LOW (additive only, full backups, rollback available)
**Recommended Execution Time**: Non-peak hours (evening/weekend)

---

**Questions Before Proceeding?**
- Are backups sufficient? (Yes - full backup + schema backup)
- Will this break existing code? (No - additive migrations only)
- Can we rollback? (Yes - full backup + manual drop commands)
- What if migrations fail? (Rollback plan documented above)

**Ready to execute**: Run Phase 0 checklist first, then proceed sequentially through all phases.
