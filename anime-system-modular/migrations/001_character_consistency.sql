-- Migration: 001_character_consistency.sql
-- Tower Anime Production System
-- Adds character consistency anchors, generation reproducibility, and quality metrics

-- Character consistency anchors
ALTER TABLE characters ADD COLUMN IF NOT EXISTS reference_embedding BYTEA;
ALTER TABLE characters ADD COLUMN IF NOT EXISTS color_palette JSONB DEFAULT '{}';
ALTER TABLE characters ADD COLUMN IF NOT EXISTS base_prompt TEXT;
ALTER TABLE characters ADD COLUMN IF NOT EXISTS negative_tokens TEXT[] DEFAULT '{}';
ALTER TABLE characters ADD COLUMN IF NOT EXISTS lora_model_path VARCHAR(500);

-- Character visual attributes (normalized)
CREATE TABLE IF NOT EXISTS character_attributes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id UUID REFERENCES characters(id) ON DELETE CASCADE,
    attribute_type VARCHAR(100) NOT NULL,
    attribute_value TEXT NOT NULL,
    prompt_tokens TEXT[],
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Character variations (outfits, expressions, poses)
CREATE TABLE IF NOT EXISTS character_variations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id UUID REFERENCES characters(id) ON DELETE CASCADE,
    variation_name VARCHAR(255) NOT NULL,
    variation_type VARCHAR(100),
    prompt_modifiers JSONB DEFAULT '{}',
    reference_image_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Generation parameters for reproducibility
CREATE TABLE IF NOT EXISTS generation_params (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
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
    frame_count INTEGER DEFAULT 1,
    fps INTEGER DEFAULT 24,
    lora_models JSONB DEFAULT '[]',
    controlnet_models JSONB DEFAULT '[]',
    ipadapter_refs JSONB DEFAULT '[]',
    comfyui_workflow JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Quality scores
CREATE TABLE IF NOT EXISTS quality_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    face_similarity FLOAT,
    aesthetic_score FLOAT,
    temporal_lpips FLOAT,
    motion_smoothness FLOAT,
    subject_consistency FLOAT,
    passes_threshold BOOLEAN DEFAULT false,
    evaluated_at TIMESTAMP DEFAULT NOW()
);

-- Story bible
CREATE TABLE IF NOT EXISTS story_bibles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    art_style TEXT,
    color_palette JSONB DEFAULT '{}',
    line_weight VARCHAR(50),
    shading_style VARCHAR(100),
    setting_description TEXT,
    time_period VARCHAR(100),
    mood_keywords TEXT[] DEFAULT '{}',
    narrative_themes TEXT[] DEFAULT '{}',
    global_seed BIGINT,
    version VARCHAR(20) DEFAULT '1.0.0',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_char_attrs_char ON character_attributes(character_id);
CREATE INDEX IF NOT EXISTS idx_gen_params_job ON generation_params(job_id);
CREATE INDEX IF NOT EXISTS idx_quality_job ON quality_scores(job_id);
CREATE INDEX IF NOT EXISTS idx_story_bible_project ON story_bibles(project_id);
