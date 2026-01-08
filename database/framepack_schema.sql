-- FramePack Movie Pipeline Schema
-- Echo Brain memory persistence for character/story/visual consistency
-- Supports chaining 30-60 second segments into movie-length content

-- ============================================================
-- 1. MOVIE PROJECTS - Top-level movie container
-- ============================================================
CREATE TABLE IF NOT EXISTS movie_projects (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    target_duration_minutes INTEGER DEFAULT 90,
    target_fps INTEGER DEFAULT 30,
    resolution_width INTEGER DEFAULT 1280,
    resolution_height INTEGER DEFAULT 720,
    style_preset VARCHAR(100) DEFAULT 'anime',
    status VARCHAR(50) DEFAULT 'planning',  -- planning, in_production, completed, archived
    total_scenes INTEGER DEFAULT 0,
    completed_scenes INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- ============================================================
-- 2. MOVIE EPISODES - Episode breakdown (for series)
-- ============================================================
CREATE TABLE IF NOT EXISTS movie_episodes (
    id SERIAL PRIMARY KEY,
    movie_id INTEGER REFERENCES movie_projects(id) ON DELETE CASCADE,
    episode_number INTEGER NOT NULL,
    title VARCHAR(255),
    synopsis TEXT,
    target_duration_minutes INTEGER DEFAULT 24,
    status VARCHAR(50) DEFAULT 'planning',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(movie_id, episode_number)
);

-- ============================================================
-- 3. MOVIE SCENES - Scene breakdown with keyframe paths
-- ============================================================
CREATE TABLE IF NOT EXISTS movie_scenes (
    id SERIAL PRIMARY KEY,
    movie_id INTEGER REFERENCES movie_projects(id) ON DELETE CASCADE,
    episode_id INTEGER REFERENCES movie_episodes(id) ON DELETE SET NULL,
    scene_number INTEGER NOT NULL,
    scene_title VARCHAR(255),
    description TEXT,

    -- Timing
    target_duration_seconds INTEGER DEFAULT 30,
    actual_duration_seconds FLOAT,

    -- Keyframes for FramePack anchoring
    entry_keyframe_path TEXT,      -- First frame of scene
    exit_keyframe_path TEXT,       -- Last frame of scene (becomes next scene's entry)

    -- Scene context
    location VARCHAR(255),
    time_of_day VARCHAR(50),       -- dawn, morning, afternoon, evening, night
    weather VARCHAR(50),           -- clear, cloudy, rain, snow, etc.
    mood VARCHAR(100),             -- tense, romantic, action, peaceful

    -- Production status
    status VARCHAR(50) DEFAULT 'pending',  -- pending, generating, completed, failed, review
    total_segments INTEGER DEFAULT 0,
    completed_segments INTEGER DEFAULT 0,

    -- Output
    final_video_path TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(movie_id, scene_number)
);

-- ============================================================
-- 4. GENERATION SEGMENTS - FramePack segment tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS generation_segments (
    id SERIAL PRIMARY KEY,
    scene_id INTEGER REFERENCES movie_scenes(id) ON DELETE CASCADE,
    segment_number INTEGER NOT NULL,

    -- FramePack anchoring
    first_frame_path TEXT,         -- Anchor start frame
    last_frame_path TEXT,          -- Anchor end frame (extracted after generation)

    -- Generation parameters
    motion_prompt TEXT NOT NULL,
    negative_prompt TEXT,
    seed BIGINT,
    duration_seconds INTEGER DEFAULT 30,
    fps INTEGER DEFAULT 30,

    -- ComfyUI integration
    comfyui_prompt_id VARCHAR(255),

    -- Output
    output_video_path TEXT,

    -- Quality metrics
    frame_consistency_score FLOAT,    -- SSIM-based
    motion_smoothness_score FLOAT,    -- Optical flow-based
    overall_quality_score FLOAT,      -- Combined score

    -- Status
    status VARCHAR(50) DEFAULT 'pending',  -- pending, queued, processing, completed, failed
    error_message TEXT,
    generation_time_seconds FLOAT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(scene_id, segment_number)
);

-- ============================================================
-- 5. CHARACTER SCENE MEMORY - Echo Brain character state per scene
-- ============================================================
CREATE TABLE IF NOT EXISTS character_scene_memory (
    id SERIAL PRIMARY KEY,
    scene_id INTEGER REFERENCES movie_scenes(id) ON DELETE CASCADE,
    character_id INTEGER REFERENCES anime_characters(id) ON DELETE CASCADE,

    -- Visual state
    outfit_description TEXT,
    hair_style TEXT,
    accessories TEXT[],

    -- Expression/pose
    facial_expression VARCHAR(100),
    body_pose VARCHAR(100),
    emotional_state VARCHAR(100),

    -- Position in scene
    position_description TEXT,      -- "standing by window", "sitting at desk"
    facing_direction VARCHAR(50),   -- left, right, camera, away

    -- Reference embeddings (for IPAdapter consistency)
    face_embedding_path TEXT,
    pose_embedding_path TEXT,

    -- Continuity tracking
    entered_scene_at INTEGER DEFAULT 0,  -- Segment number
    exited_scene_at INTEGER,             -- NULL if still in scene

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(scene_id, character_id)
);

-- ============================================================
-- 6. STORY STATE MEMORY - Echo Brain plot/narrative state per scene
-- ============================================================
CREATE TABLE IF NOT EXISTS story_state_memory (
    id SERIAL PRIMARY KEY,
    scene_id INTEGER REFERENCES movie_scenes(id) ON DELETE CASCADE UNIQUE,

    -- Plot context
    plot_summary TEXT,              -- What's happening in this scene
    prior_context TEXT,             -- What happened before (for continuity)
    upcoming_context TEXT,          -- Foreshadowing/setup for next scenes

    -- Dramatic elements
    tension_level FLOAT DEFAULT 0.5,        -- 0.0 (peaceful) to 1.0 (peak tension)
    pacing VARCHAR(50) DEFAULT 'medium',    -- slow, medium, fast, frantic
    story_beat VARCHAR(100),                -- setup, rising_action, climax, resolution

    -- Dialogue/audio cues
    key_dialogue TEXT[],            -- Important lines in this scene
    background_sounds TEXT[],       -- Ambient audio cues
    music_mood VARCHAR(100),        -- Action, romantic, suspense, etc.

    -- Transitions
    transition_from_previous VARCHAR(50),   -- cut, fade, dissolve, wipe
    transition_to_next VARCHAR(50),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 7. VISUAL STYLE MEMORY - Echo Brain visual consistency per scene
-- ============================================================
CREATE TABLE IF NOT EXISTS visual_style_memory (
    id SERIAL PRIMARY KEY,
    scene_id INTEGER REFERENCES movie_scenes(id) ON DELETE CASCADE UNIQUE,

    -- Lighting
    lighting_type VARCHAR(100),         -- natural, artificial, dramatic, soft
    lighting_direction VARCHAR(50),     -- front, back, side, rim, ambient
    lighting_color VARCHAR(50),         -- warm, cool, neutral
    shadow_intensity FLOAT DEFAULT 0.5, -- 0.0 (no shadows) to 1.0 (harsh shadows)

    -- Color palette
    primary_colors TEXT[],              -- Dominant colors in scene
    accent_colors TEXT[],               -- Highlight/accent colors
    color_temperature VARCHAR(50),      -- warm, neutral, cool
    saturation_level VARCHAR(50),       -- desaturated, normal, vibrant

    -- Camera
    camera_angle VARCHAR(100),          -- wide, medium, close-up, extreme_close
    camera_movement VARCHAR(100),       -- static, pan, tilt, dolly, crane
    depth_of_field VARCHAR(50),         -- shallow, medium, deep

    -- Style modifiers (for prompt enhancement)
    style_keywords TEXT[],              -- ["cinematic", "high contrast", "film grain"]
    negative_style_keywords TEXT[],     -- ["blurry", "oversaturated"]

    -- Reference
    reference_frame_path TEXT,          -- Key frame that defines scene style
    style_lora_path TEXT,               -- Optional style LoRA to use
    style_lora_strength FLOAT DEFAULT 0.7,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 8. GENERATION QUALITY FEEDBACK - Learning from generations
-- ============================================================
CREATE TABLE IF NOT EXISTS generation_quality_feedback (
    id SERIAL PRIMARY KEY,
    segment_id INTEGER REFERENCES generation_segments(id) ON DELETE CASCADE,
    character_id INTEGER REFERENCES anime_characters(id) ON DELETE SET NULL,

    -- Quality assessment
    overall_score FLOAT NOT NULL,           -- 0.0 to 1.0
    frame_consistency_score FLOAT,
    motion_smoothness_score FLOAT,
    character_accuracy_score FLOAT,
    style_consistency_score FLOAT,

    -- Prompt analysis
    full_prompt TEXT,
    successful_elements TEXT[],             -- Elements that contributed to high scores
    failed_elements TEXT[],                 -- Elements that caused issues

    -- Learning metadata
    generation_parameters JSONB,            -- Full params for reproduction

    -- User feedback (optional)
    user_rating INTEGER CHECK (user_rating >= 1 AND user_rating <= 5),
    user_notes TEXT,

    -- Categorization
    feedback_type VARCHAR(50) DEFAULT 'automatic',  -- automatic, user, review

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- INDEXES for performance
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_movie_scenes_movie_id ON movie_scenes(movie_id);
CREATE INDEX IF NOT EXISTS idx_movie_scenes_status ON movie_scenes(status);
CREATE INDEX IF NOT EXISTS idx_generation_segments_scene_id ON generation_segments(scene_id);
CREATE INDEX IF NOT EXISTS idx_generation_segments_status ON generation_segments(status);
CREATE INDEX IF NOT EXISTS idx_character_scene_memory_scene_id ON character_scene_memory(scene_id);
CREATE INDEX IF NOT EXISTS idx_character_scene_memory_character_id ON character_scene_memory(character_id);
CREATE INDEX IF NOT EXISTS idx_story_state_memory_scene_id ON story_state_memory(scene_id);
CREATE INDEX IF NOT EXISTS idx_visual_style_memory_scene_id ON visual_style_memory(scene_id);
CREATE INDEX IF NOT EXISTS idx_quality_feedback_segment_id ON generation_quality_feedback(segment_id);
CREATE INDEX IF NOT EXISTS idx_quality_feedback_character_id ON generation_quality_feedback(character_id);
CREATE INDEX IF NOT EXISTS idx_quality_feedback_score ON generation_quality_feedback(overall_score);

-- ============================================================
-- TRIGGERS for updated_at
-- ============================================================
CREATE TRIGGER update_movie_projects_updated_at BEFORE UPDATE ON movie_projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_movie_episodes_updated_at BEFORE UPDATE ON movie_episodes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_movie_scenes_updated_at BEFORE UPDATE ON movie_scenes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_generation_segments_updated_at BEFORE UPDATE ON generation_segments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_character_scene_memory_updated_at BEFORE UPDATE ON character_scene_memory
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_story_state_memory_updated_at BEFORE UPDATE ON story_state_memory
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_visual_style_memory_updated_at BEFORE UPDATE ON visual_style_memory
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- HELPER VIEWS
-- ============================================================

-- View: Scene generation progress
CREATE OR REPLACE VIEW scene_generation_progress AS
SELECT
    ms.id as scene_id,
    mp.title as movie_title,
    ms.scene_number,
    ms.scene_title,
    ms.status,
    ms.total_segments,
    ms.completed_segments,
    CASE
        WHEN ms.total_segments > 0
        THEN ROUND((ms.completed_segments::float / ms.total_segments * 100)::numeric, 1)
        ELSE 0
    END as progress_percent,
    AVG(gs.overall_quality_score) as avg_quality_score
FROM movie_scenes ms
JOIN movie_projects mp ON ms.movie_id = mp.id
LEFT JOIN generation_segments gs ON gs.scene_id = ms.id
GROUP BY ms.id, mp.title, ms.scene_number, ms.scene_title, ms.status,
         ms.total_segments, ms.completed_segments;

-- View: Character appearance history
CREATE OR REPLACE VIEW character_appearance_history AS
SELECT
    ac.character_name,
    mp.title as movie_title,
    ms.scene_number,
    csm.outfit_description,
    csm.emotional_state,
    csm.position_description
FROM character_scene_memory csm
JOIN anime_characters ac ON csm.character_id = ac.id
JOIN movie_scenes ms ON csm.scene_id = ms.id
JOIN movie_projects mp ON ms.movie_id = mp.id
ORDER BY mp.id, ms.scene_number;

-- View: Successful prompt patterns (for learning)
CREATE OR REPLACE VIEW successful_prompt_patterns AS
SELECT
    ac.character_name,
    gqf.successful_elements,
    gqf.overall_score,
    COUNT(*) as occurrence_count
FROM generation_quality_feedback gqf
LEFT JOIN anime_characters ac ON gqf.character_id = ac.id
WHERE gqf.overall_score >= 0.7
GROUP BY ac.character_name, gqf.successful_elements, gqf.overall_score
ORDER BY occurrence_count DESC;

-- ============================================================
-- GRANT PERMISSIONS
-- ============================================================
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO patrick;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO patrick;
