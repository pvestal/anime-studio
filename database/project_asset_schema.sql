-- Project Asset Management Schema
-- Extends existing anime production database for proper project integration

-- Create project assets table for organized file management
CREATE TABLE IF NOT EXISTS anime_api.project_assets (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL, -- References projects table
    file_path TEXT NOT NULL UNIQUE,
    asset_type VARCHAR(50) NOT NULL, -- 'character', 'scene', 'background', 'prop', 'reference'
    character_name VARCHAR(255),
    scene_id INTEGER,
    generation_metadata JSONB, -- ComfyUI parameters, workflow info, etc.
    job_id INTEGER, -- References production_jobs.id
    file_hash VARCHAR(64) NOT NULL, -- SHA256 for integrity
    file_size INTEGER NOT NULL,
    visual_features JSONB, -- For future AI-based consistency matching
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create character references table for consistency management
CREATE TABLE IF NOT EXISTS anime_api.character_references (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    character_name VARCHAR(255) NOT NULL,
    reference_path TEXT NOT NULL,
    style_parameters JSONB, -- Extracted character features
    is_primary_reference BOOLEAN DEFAULT FALSE,
    reference_type VARCHAR(50) DEFAULT 'reference', -- 'reference', 'generated', 'concept'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create projects table if it doesn't exist
CREATE TABLE IF NOT EXISTS anime_api.projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    style_guide JSONB, -- Project-wide style parameters
    directory_path TEXT, -- Root project directory
    status VARCHAR(50) DEFAULT 'active', -- 'active', 'completed', 'archived'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create scenes table for scene organization
CREATE TABLE IF NOT EXISTS anime_api.scenes (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES anime_api.projects(id),
    scene_number INTEGER,
    scene_name VARCHAR(255),
    description TEXT,
    characters JSONB, -- Array of character names in scene
    style_parameters JSONB, -- Scene-specific style overrides
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create character consistency tracking
CREATE TABLE IF NOT EXISTS anime_api.character_consistency_scores (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    character_name VARCHAR(255) NOT NULL,
    asset_id INTEGER NOT NULL REFERENCES anime_api.project_assets(id),
    reference_asset_id INTEGER REFERENCES anime_api.project_assets(id),
    consistency_score FLOAT, -- 0.0 - 1.0
    comparison_method VARCHAR(100), -- 'visual_similarity', 'feature_match', etc.
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_project_assets_project_id ON anime_api.project_assets(project_id);
CREATE INDEX IF NOT EXISTS idx_project_assets_character ON anime_api.project_assets(character_name);
CREATE INDEX IF NOT EXISTS idx_project_assets_type ON anime_api.project_assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_project_assets_job_id ON anime_api.project_assets(job_id);
CREATE INDEX IF NOT EXISTS idx_character_refs_project_char ON anime_api.character_references(project_id, character_name);
CREATE INDEX IF NOT EXISTS idx_scenes_project ON anime_api.scenes(project_id);

-- Add foreign key constraints
ALTER TABLE anime_api.project_assets
ADD CONSTRAINT fk_project_assets_job
FOREIGN KEY (job_id) REFERENCES anime_api.production_jobs(id) ON DELETE SET NULL;

-- Update existing production_jobs table to include project context
ALTER TABLE anime_api.production_jobs
ADD COLUMN IF NOT EXISTS project_id INTEGER,
ADD COLUMN IF NOT EXISTS character_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS scene_id INTEGER,
ADD COLUMN IF NOT EXISTS asset_type VARCHAR(50) DEFAULT 'misc';

-- Add trigger to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_project_assets_updated_at
    BEFORE UPDATE ON anime_api.project_assets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_projects_updated_at
    BEFORE UPDATE ON anime_api.projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default project if none exists
INSERT INTO anime_api.projects (id, name, description, directory_path, style_guide)
VALUES (1, 'Default Project', 'Default anime project for unspecified generations',
        '/mnt/1TB-storage/anime-projects/project_1',
        '{"default_style": "anime", "quality": "high", "art_style": "modern_anime"}')
ON CONFLICT (id) DO NOTHING;

-- Sample data for testing
-- Insert example character references
INSERT INTO anime_api.character_references (project_id, character_name, reference_path, style_parameters, is_primary_reference)
VALUES
(1, 'Sakura', '/mnt/1TB-storage/anime-projects/project_1/references/character_refs/Sakura/primary.png',
 '{"hair_color": "pink", "eye_color": "green", "clothing_style": "school_uniform"}', true),
(1, 'Hiroshi', '/mnt/1TB-storage/anime-projects/project_1/references/character_refs/Hiroshi/primary.png',
 '{"hair_color": "black", "eye_color": "brown", "clothing_style": "casual"}', true)
ON CONFLICT DO NOTHING;

-- Create view for easy asset querying
CREATE OR REPLACE VIEW anime_api.project_asset_summary AS
SELECT
    pa.project_id,
    p.name as project_name,
    pa.character_name,
    pa.asset_type,
    COUNT(*) as asset_count,
    SUM(pa.file_size) as total_size_bytes,
    MAX(pa.created_at) as latest_asset
FROM anime_api.project_assets pa
JOIN anime_api.projects p ON pa.project_id = p.id
GROUP BY pa.project_id, p.name, pa.character_name, pa.asset_type
ORDER BY pa.project_id, pa.character_name, pa.asset_type;

-- Grant permissions (assuming patrick user)
GRANT ALL PRIVILEGES ON anime_api.project_assets TO patrick;
GRANT ALL PRIVILEGES ON anime_api.character_references TO patrick;
GRANT ALL PRIVILEGES ON anime_api.projects TO patrick;
GRANT ALL PRIVILEGES ON anime_api.scenes TO patrick;
GRANT ALL PRIVILEGES ON anime_api.character_consistency_scores TO patrick;
GRANT SELECT ON anime_api.project_asset_summary TO patrick;