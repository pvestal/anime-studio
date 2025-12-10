-- Hybrid Migration: Bridge current schema with v2.0 requirements
-- Adds missing tables needed for v2.0 services without breaking current schema

-- Core tables that v2.0 services expect
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,  -- Keep integer for compatibility
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    type VARCHAR(100) DEFAULT 'anime',
    status VARCHAR(50) DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,  -- Keep integer for compatibility
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
    job_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    prompt TEXT,
    negative_prompt TEXT,
    output_path VARCHAR(500),
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    INDEX(status),
    INDEX(job_type),
    INDEX(created_at)
);

-- v2.0 tables modified for integer compatibility
CREATE TABLE IF NOT EXISTS character_attributes (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    attribute_type VARCHAR(100) NOT NULL,
    attribute_value TEXT NOT NULL,
    prompt_tokens TEXT[],
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS character_variations (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    variation_name VARCHAR(255) NOT NULL,
    variation_type VARCHAR(100),
    prompt_modifiers JSONB DEFAULT '{}',
    reference_image_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS generation_params (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    positive_prompt TEXT NOT NULL,
    negative_prompt TEXT,
    seed BIGINT NOT NULL,
    subseed BIGINT,
    model_name VARCHAR(255) NOT NULL,
    model_hash VARCHAR(64),
    vae_name VARCHAR(255),
    sampler_name VARCHAR(100),
    scheduler VARCHAR(100),
    steps INTEGER,
    cfg_scale FLOAT,
    width INTEGER,
    height INTEGER,
    batch_size INTEGER DEFAULT 1,
    n_iter INTEGER DEFAULT 1,
    lora_models JSONB DEFAULT '[]',
    controlnet_configs JSONB DEFAULT '[]',
    comfyui_workflow JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quality_scores (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    metric_name VARCHAR(100) NOT NULL,
    score_value FLOAT NOT NULL,
    threshold_min FLOAT,
    threshold_max FLOAT,
    passed BOOLEAN,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX(metric_name),
    INDEX(passed)
);

CREATE TABLE IF NOT EXISTS story_bibles (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    version INTEGER DEFAULT 1,
    art_style_description TEXT,
    color_palette JSONB DEFAULT '{}',
    character_design_rules TEXT,
    world_building_notes TEXT,
    technical_requirements JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(project_id, version)
);

-- Video production tables (modified for integer IDs)
CREATE TABLE IF NOT EXISTS episodes (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    episode_number INTEGER NOT NULL,
    title VARCHAR(255),
    synopsis TEXT,
    status VARCHAR(50) DEFAULT 'pre_production',
    target_duration_seconds INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(project_id, episode_number)
);

CREATE TABLE IF NOT EXISTS scenes (
    id SERIAL PRIMARY KEY,
    episode_id INTEGER REFERENCES episodes(id) ON DELETE CASCADE,
    scene_number INTEGER NOT NULL,
    name VARCHAR(255),
    description TEXT,
    location VARCHAR(255),
    time_of_day VARCHAR(50),
    mood VARCHAR(100),
    duration_frames INTEGER,
    style_overrides JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(episode_id, scene_number)
);

CREATE TABLE IF NOT EXISTS cuts (
    id SERIAL PRIMARY KEY,
    scene_id INTEGER REFERENCES scenes(id) ON DELETE CASCADE,
    cut_number INTEGER NOT NULL,
    description TEXT,
    camera_angle VARCHAR(100),
    duration_frames INTEGER,
    character_ids INTEGER[], -- Array of character IDs
    dialogue TEXT,
    action_notes TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    output_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(scene_id, cut_number)
);

CREATE TABLE IF NOT EXISTS scene_characters (
    id SERIAL PRIMARY KEY,
    scene_id INTEGER REFERENCES scenes(id) ON DELETE CASCADE,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    role VARCHAR(100),
    costume_variant VARCHAR(255),
    emotional_state VARCHAR(100),
    position_notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(scene_id, character_id)
);

CREATE TABLE IF NOT EXISTS render_queue (
    id SERIAL PRIMARY KEY,
    cut_id INTEGER REFERENCES cuts(id) ON DELETE CASCADE,
    priority INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'queued',
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    error_message TEXT,
    render_params JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    INDEX(status),
    INDEX(priority),
    INDEX(created_at)
);

-- Create default project if none exists
INSERT INTO projects (name, description, type)
SELECT 'Default Anime Project', 'Auto-created default project for existing characters', 'anime'
WHERE NOT EXISTS (SELECT 1 FROM projects);

-- Link existing characters to default project
UPDATE characters
SET project_id = (SELECT id FROM projects WHERE name = 'Default Anime Project' LIMIT 1)
WHERE project_id IS NULL;

-- Add helpful indexes
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_character_id ON jobs(character_id);
CREATE INDEX IF NOT EXISTS idx_generation_params_job_id ON generation_params(job_id);
CREATE INDEX IF NOT EXISTS idx_quality_scores_job_id ON quality_scores(job_id);
CREATE INDEX IF NOT EXISTS idx_render_queue_status ON render_queue(status);

ANALYZE;