-- Migration: 002_video_production.sql
-- Tower Anime Production System
-- Adds video generation, scene management, and episode structure

-- Episodes (production organization)
CREATE TABLE IF NOT EXISTS episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    episode_number INTEGER NOT NULL,
    title VARCHAR(255),
    synopsis TEXT,
    status VARCHAR(50) DEFAULT 'pre_production',
    target_duration_seconds INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(project_id, episode_number)
);

-- Scenes
CREATE TABLE IF NOT EXISTS scenes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id UUID REFERENCES episodes(id) ON DELETE CASCADE,
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

-- Cuts (individual shots within scenes)
CREATE TABLE IF NOT EXISTS cuts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scene_id UUID REFERENCES scenes(id) ON DELETE CASCADE,
    cut_number INTEGER NOT NULL,
    description TEXT,
    camera_angle VARCHAR(100),
    duration_frames INTEGER,
    character_ids UUID[],
    dialogue TEXT,
    action_notes TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    output_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(scene_id, cut_number)
);

-- Scene-character associations (which characters appear in which scenes)
CREATE TABLE IF NOT EXISTS scene_characters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scene_id UUID REFERENCES scenes(id) ON DELETE CASCADE,
    character_id UUID REFERENCES characters(id) ON DELETE CASCADE,
    entrance_frame INTEGER DEFAULT 0,
    exit_frame INTEGER,
    position_notes TEXT,
    UNIQUE(scene_id, character_id)
);

-- Video render queue (for batch processing)
CREATE TABLE IF NOT EXISTS render_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    priority INTEGER DEFAULT 5,
    status VARCHAR(50) DEFAULT 'pending',
    worker_id VARCHAR(255),
    queued_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_episodes_project ON episodes(project_id);
CREATE INDEX IF NOT EXISTS idx_scenes_episode ON scenes(episode_id);
CREATE INDEX IF NOT EXISTS idx_cuts_scene ON cuts(scene_id);
CREATE INDEX IF NOT EXISTS idx_scene_chars_scene ON scene_characters(scene_id);
CREATE INDEX IF NOT EXISTS idx_render_queue_status ON render_queue(status, priority DESC);

-- Update jobs table for video support
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS scene_id UUID REFERENCES scenes(id);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cut_id UUID REFERENCES cuts(id);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS total_frames INTEGER;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS current_frame INTEGER;
