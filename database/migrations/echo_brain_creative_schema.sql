-- Echo Brain Creative Schema Extension
-- Adds storyline, episode, and semantic search capabilities
-- Run this after the main anime_production schema

-- Enable vector extension for embeddings (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- Storylines table - top-level narrative containers
CREATE TABLE IF NOT EXISTS storylines (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    summary TEXT,
    episodes JSONB,  -- Array of episode objects with metadata
    style_guidelines JSONB,  -- Visual style consistency rules
    theme VARCHAR(255),
    genre VARCHAR(100),
    target_audience VARCHAR(100),
    embedding vector(768),  -- For semantic search
    metadata JSONB,
    status VARCHAR(50) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Episodes table - individual episode management
CREATE TABLE IF NOT EXISTS episodes (
    id SERIAL PRIMARY KEY,
    storyline_id INTEGER REFERENCES storylines(id) ON DELETE CASCADE,
    episode_number INTEGER NOT NULL,
    title VARCHAR(255),
    synopsis TEXT,
    description TEXT,
    scene_breakdown JSONB,  -- [{scene_number: 1, description: "...", characters: [...], mood: "..."}]
    visual_references TEXT[],  -- Paths to reference images
    generated_scenes INTEGER[],  -- Links to production_jobs
    duration_seconds INTEGER,  -- Planned duration
    embedding vector(768),  -- For finding similar episodes
    metadata JSONB,
    status VARCHAR(50) DEFAULT 'planning',  -- planning, production, post-production, complete
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Character embeddings for semantic search and consistency
CREATE TABLE IF NOT EXISTS character_embeddings (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    description_embedding vector(768),  -- Text description embedding
    visual_style_embedding vector(768),  -- Visual style embedding
    personality_embedding vector(768),  -- Personality traits embedding
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(character_id)
);

-- Scene productions - detailed scene generation tracking
CREATE TABLE IF NOT EXISTS scene_productions (
    id SERIAL PRIMARY KEY,
    episode_id INTEGER REFERENCES episodes(id) ON DELETE CASCADE,
    scene_number INTEGER NOT NULL,
    description TEXT,
    prompt TEXT,
    negative_prompt TEXT,
    characters INTEGER[],  -- Array of character IDs
    checkpoint_used VARCHAR(255),
    lora_configs JSONB,  -- LoRA configurations used
    generation_params JSONB,  -- All generation parameters
    output_paths TEXT[],  -- Generated file paths
    quality_score FLOAT,
    consistency_score FLOAT,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(episode_id, scene_number)
);

-- Creative suggestions tracking
CREATE TABLE IF NOT EXISTS creative_suggestions (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    episode_id INTEGER REFERENCES episodes(id),
    suggestion_type VARCHAR(50),  -- storyline, character, visual_style, scene
    suggestion_text TEXT,
    suggestion_data JSONB,
    accepted BOOLEAN DEFAULT NULL,  -- NULL=pending, TRUE=accepted, FALSE=rejected
    applied_at TIMESTAMP,
    model_used VARCHAR(100),
    confidence_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Style consistency tracking
CREATE TABLE IF NOT EXISTS style_consistency (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    character_id INTEGER REFERENCES characters(id),
    checkpoint_preferences JSONB,  -- Preferred checkpoints for this character
    lora_preferences JSONB,  -- Preferred LoRAs
    prompt_templates JSONB,  -- Reusable prompt templates
    negative_templates JSONB,  -- Consistent negative prompts
    color_palette JSONB,  -- Preferred colors
    style_keywords TEXT[],  -- Key style descriptors
    reference_images TEXT[],  -- Paths to reference images
    embedding vector(768),  -- Style embedding for similarity search
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Production jobs extension for episode tracking
ALTER TABLE production_jobs ADD COLUMN IF NOT EXISTS episode_id INTEGER REFERENCES episodes(id);
ALTER TABLE production_jobs ADD COLUMN IF NOT EXISTS scene_number INTEGER;
ALTER TABLE production_jobs ADD COLUMN IF NOT EXISTS character_id INTEGER REFERENCES characters(id);

-- QC analyses extension for episode quality
ALTER TABLE qc_analyses ADD COLUMN IF NOT EXISTS episode_id INTEGER REFERENCES episodes(id);
ALTER TABLE qc_analyses ADD COLUMN IF NOT EXISTS scene_consistency_score FLOAT;

-- Semantic search indexes
CREATE INDEX IF NOT EXISTS idx_storylines_embedding ON storylines USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_episodes_embedding ON episodes USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_character_desc_embedding ON character_embeddings USING ivfflat (description_embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_character_visual_embedding ON character_embeddings USING ivfflat (visual_style_embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_style_consistency_embedding ON style_consistency USING ivfflat (embedding vector_cosine_ops);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_episodes_storyline ON episodes(storyline_id);
CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(status);
CREATE INDEX IF NOT EXISTS idx_scene_productions_episode ON scene_productions(episode_id);
CREATE INDEX IF NOT EXISTS idx_creative_suggestions_project ON creative_suggestions(project_id);
CREATE INDEX IF NOT EXISTS idx_creative_suggestions_accepted ON creative_suggestions(accepted);

-- Helper functions

-- Function to find similar content by embedding
CREATE OR REPLACE FUNCTION find_similar_by_embedding(
    query_embedding vector(768),
    table_name text,
    limit_count integer DEFAULT 10
) RETURNS TABLE (
    id integer,
    similarity float
) AS $$
BEGIN
    IF table_name = 'storylines' THEN
        RETURN QUERY
        SELECT s.id, 1 - (s.embedding <=> query_embedding) as similarity
        FROM storylines s
        WHERE s.embedding IS NOT NULL
        ORDER BY s.embedding <=> query_embedding
        LIMIT limit_count;
    ELSIF table_name = 'episodes' THEN
        RETURN QUERY
        SELECT e.id, 1 - (e.embedding <=> query_embedding) as similarity
        FROM episodes e
        WHERE e.embedding IS NOT NULL
        ORDER BY e.embedding <=> query_embedding
        LIMIT limit_count;
    ELSIF table_name = 'characters' THEN
        RETURN QUERY
        SELECT ce.character_id as id, 1 - (ce.description_embedding <=> query_embedding) as similarity
        FROM character_embeddings ce
        WHERE ce.description_embedding IS NOT NULL
        ORDER BY ce.description_embedding <=> query_embedding
        LIMIT limit_count;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate project completion percentage
CREATE OR REPLACE FUNCTION calculate_project_completion(project_id_param integer)
RETURNS float AS $$
DECLARE
    total_scenes integer;
    completed_scenes integer;
    completion_percentage float;
BEGIN
    -- Count total planned scenes
    SELECT COUNT(*)
    INTO total_scenes
    FROM episodes e
    JOIN storylines s ON e.storyline_id = s.id
    WHERE s.project_id = project_id_param;

    -- Count completed scenes
    SELECT COUNT(*)
    INTO completed_scenes
    FROM scene_productions sp
    JOIN episodes e ON sp.episode_id = e.id
    JOIN storylines s ON e.storyline_id = s.id
    WHERE s.project_id = project_id_param
    AND sp.status = 'completed';

    IF total_scenes = 0 THEN
        RETURN 0;
    END IF;

    completion_percentage := (completed_scenes::float / total_scenes::float) * 100;
    RETURN completion_percentage;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_storylines_updated_at BEFORE UPDATE ON storylines
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_character_embeddings_updated_at BEFORE UPDATE ON character_embeddings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_style_consistency_updated_at BEFORE UPDATE ON style_consistency
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Sample data for testing (commented out by default)
/*
-- Insert sample storyline
INSERT INTO storylines (project_id, title, summary, theme, genre, episodes) VALUES
(1, 'The Time Wanderer', 'A story about a character who can travel through different timelines', 'Time Travel', 'Sci-Fi',
'[{"number": 1, "title": "The Discovery"}, {"number": 2, "title": "First Jump"}]'::jsonb);

-- Insert sample episode
INSERT INTO episodes (storyline_id, episode_number, title, synopsis, scene_breakdown) VALUES
(1, 1, 'The Discovery', 'The protagonist discovers their time travel ability',
'[{"scene_number": 1, "description": "Opening scene in modern Tokyo", "characters": ["protagonist"], "mood": "mysterious"}]'::jsonb);
*/

-- Grant permissions (adjust user as needed)
GRANT ALL ON ALL TABLES IN SCHEMA public TO patrick;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO patrick;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO patrick;