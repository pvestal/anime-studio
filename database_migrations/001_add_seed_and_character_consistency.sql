-- Migration: Add seed storage and character consistency fields
-- Version: 001
-- Date: 2025-11-19
-- Purpose: Implement comprehensive seed storage and character consistency system

-- Step 1: Add new fields to production_jobs table
ALTER TABLE anime_api.production_jobs
ADD COLUMN IF NOT EXISTS seed BIGINT,
ADD COLUMN IF NOT EXISTS character_id INTEGER,
ADD COLUMN IF NOT EXISTS workflow_snapshot JSONB;

-- Step 2: Create character_versions table for tracking character evolution
CREATE TABLE IF NOT EXISTS anime_api.character_versions (
    id SERIAL PRIMARY KEY,
    character_id INTEGER NOT NULL REFERENCES anime_api.characters(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL DEFAULT 1,
    seed BIGINT,
    appearance_changes TEXT,
    lora_path TEXT,
    embedding_path TEXT,
    comfyui_workflow JSONB,
    workflow_template_path TEXT,
    generation_parameters JSONB,
    quality_score NUMERIC(5,2),
    consistency_score NUMERIC(5,2),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    is_canonical BOOLEAN DEFAULT FALSE,
    parent_version_id INTEGER REFERENCES anime_api.character_versions(id),

    -- Ensure unique version numbers per character
    CONSTRAINT unique_character_version UNIQUE(character_id, version_number),

    -- Validate scores
    CONSTRAINT check_quality_score CHECK (quality_score >= 0 AND quality_score <= 100),
    CONSTRAINT check_consistency_score CHECK (consistency_score >= 0 AND consistency_score <= 100)
);

-- Step 3: Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_production_jobs_character_id ON anime_api.production_jobs(character_id) WHERE character_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_production_jobs_seed ON anime_api.production_jobs(seed) WHERE seed IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_character_versions_character_id ON anime_api.character_versions(character_id);
CREATE INDEX IF NOT EXISTS idx_character_versions_seed ON anime_api.character_versions(seed) WHERE seed IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_character_versions_canonical ON anime_api.character_versions(character_id, is_canonical) WHERE is_canonical = TRUE;

-- Step 4: Add foreign key constraint for character_id in production_jobs
ALTER TABLE anime_api.production_jobs
ADD CONSTRAINT fk_production_jobs_character
FOREIGN KEY (character_id) REFERENCES anime_api.characters(id) ON DELETE SET NULL;

-- Step 5: Create function to auto-increment version numbers
CREATE OR REPLACE FUNCTION anime_api.get_next_character_version(p_character_id INTEGER)
RETURNS INTEGER AS $$
DECLARE
    next_version INTEGER;
BEGIN
    SELECT COALESCE(MAX(version_number), 0) + 1
    INTO next_version
    FROM anime_api.character_versions
    WHERE character_id = p_character_id;

    RETURN next_version;
END;
$$ LANGUAGE plpgsql;

-- Step 6: Create trigger to auto-update version timestamps
CREATE OR REPLACE FUNCTION anime_api.update_character_version_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_character_version_timestamp ON anime_api.character_versions;
CREATE TRIGGER trigger_character_version_timestamp
    BEFORE UPDATE ON anime_api.character_versions
    FOR EACH ROW
    EXECUTE FUNCTION anime_api.update_character_version_timestamp();

-- Step 7: Add comments for documentation
COMMENT ON TABLE anime_api.character_versions IS 'Stores character version evolution with complete workflow snapshots for exact regeneration';
COMMENT ON COLUMN anime_api.character_versions.seed IS 'Fixed seed for reproducible generation';
COMMENT ON COLUMN anime_api.character_versions.comfyui_workflow IS 'Complete ComfyUI workflow JSON for exact recreation';
COMMENT ON COLUMN anime_api.character_versions.is_canonical IS 'Marks the primary/canonical version of this character';
COMMENT ON COLUMN anime_api.production_jobs.seed IS 'Fixed seed used for this generation job';
COMMENT ON COLUMN anime_api.production_jobs.character_id IS 'Links job to specific character for consistency tracking';
COMMENT ON COLUMN anime_api.production_jobs.workflow_snapshot IS 'Complete workflow used for this generation';