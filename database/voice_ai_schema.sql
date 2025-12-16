-- Voice AI Database Schema for Anime Production
-- Extends anime_schema.sql with voice and dialogue capabilities

-- Voice profiles for characters
CREATE TABLE IF NOT EXISTS voice_profiles (
    id SERIAL PRIMARY KEY,
    character_name VARCHAR(255) UNIQUE NOT NULL,
    voice_id VARCHAR(255) NOT NULL,
    voice_name VARCHAR(255) NOT NULL,
    voice_settings JSONB DEFAULT '{}',
    description TEXT,
    sample_text TEXT DEFAULT 'Hello, this is a sample of my voice.',
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Voice generation jobs tracking
CREATE TABLE IF NOT EXISTS voice_generation_jobs (
    id SERIAL PRIMARY KEY,
    job_id UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    text TEXT NOT NULL,
    character_name VARCHAR(255),
    voice_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    audio_file_path TEXT,
    error_message TEXT,
    generation_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Voice assignments for scenes (enhanced from original)
CREATE TABLE IF NOT EXISTS voice_assignments (
    id SERIAL PRIMARY KEY,
    scene_id INTEGER,
    character_id INTEGER,
    voice_id VARCHAR(255) NOT NULL,
    dialogue_text TEXT NOT NULL,
    audio_file_path TEXT NOT NULL,
    timing_start FLOAT DEFAULT 0.0,
    duration FLOAT,
    emotion VARCHAR(100) DEFAULT 'neutral',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (character_id) REFERENCES anime_characters(id) ON DELETE CASCADE
);

-- Dialogue scenes management
CREATE TABLE IF NOT EXISTS dialogue_scenes (
    id SERIAL PRIMARY KEY,
    scene_id VARCHAR(255) UNIQUE NOT NULL,
    project_id VARCHAR(255),
    scene_name VARCHAR(255) NOT NULL,
    background_music_path TEXT,
    background_music_volume FLOAT DEFAULT 0.3,
    scene_duration FLOAT DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Individual dialogue lines
CREATE TABLE IF NOT EXISTS dialogue_lines (
    id SERIAL PRIMARY KEY,
    line_id VARCHAR(255) UNIQUE NOT NULL,
    scene_id VARCHAR(255) NOT NULL,
    character_name VARCHAR(255) NOT NULL,
    dialogue_text TEXT NOT NULL,
    emotion VARCHAR(100) DEFAULT 'neutral',
    timing_start FLOAT,
    timing_end FLOAT,
    priority INTEGER DEFAULT 1,
    voice_settings JSONB DEFAULT '{}',
    audio_file_path TEXT,
    lip_sync_data_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scene_id) REFERENCES dialogue_scenes(scene_id) ON DELETE CASCADE
);

-- Lip sync data storage
CREATE TABLE IF NOT EXISTS lip_sync_data (
    id SERIAL PRIMARY KEY,
    audio_file_path TEXT NOT NULL,
    character_name VARCHAR(255) NOT NULL,
    lip_sync_json_path TEXT NOT NULL,
    frame_count INTEGER,
    duration_seconds FLOAT,
    frame_rate FLOAT DEFAULT 24.0,
    processing_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Video-voice integration processing records
CREATE TABLE IF NOT EXISTS video_voice_processing (
    id SERIAL PRIMARY KEY,
    processing_id VARCHAR(255) UNIQUE NOT NULL,
    project_id VARCHAR(255) NOT NULL,
    scene_name VARCHAR(255) NOT NULL,
    video_prompt TEXT NOT NULL,
    dialogue_lines_count INTEGER DEFAULT 0,
    characters_count INTEGER DEFAULT 0,
    video_type VARCHAR(50) DEFAULT 'video',
    frames INTEGER DEFAULT 120,
    fps INTEGER DEFAULT 24,
    width INTEGER DEFAULT 512,
    height INTEGER DEFAULT 512,
    enable_lip_sync BOOLEAN DEFAULT TRUE,
    output_video_path TEXT,
    scene_duration FLOAT DEFAULT 0.0,
    processing_status VARCHAR(50) DEFAULT 'pending',
    dialogue_result JSONB,
    video_result JSONB,
    audio_integration_result JSONB,
    quality_result JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Echo Brain voice quality assessments
CREATE TABLE IF NOT EXISTS voice_quality_assessments (
    id SERIAL PRIMARY KEY,
    assessment_id UUID DEFAULT gen_random_uuid(),
    voice_job_id UUID,
    character_name VARCHAR(255),
    audio_file_path TEXT NOT NULL,
    echo_brain_response JSONB,
    quality_score FLOAT,
    consistency_score FLOAT,
    emotion_accuracy FLOAT,
    recommendations TEXT[],
    approved BOOLEAN DEFAULT FALSE,
    assessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (voice_job_id) REFERENCES voice_generation_jobs(job_id) ON DELETE CASCADE
);

-- Voice style templates for different emotions/situations
CREATE TABLE IF NOT EXISTS voice_style_templates (
    id SERIAL PRIMARY KEY,
    template_name VARCHAR(255) UNIQUE NOT NULL,
    emotion VARCHAR(100) NOT NULL,
    voice_settings JSONB NOT NULL,
    description TEXT,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audio processing cache for performance
CREATE TABLE IF NOT EXISTS audio_processing_cache (
    id SERIAL PRIMARY KEY,
    cache_key VARCHAR(255) UNIQUE NOT NULL,
    input_text_hash VARCHAR(64) NOT NULL,
    character_name VARCHAR(255),
    voice_settings_hash VARCHAR(64),
    cached_audio_path TEXT NOT NULL,
    lip_sync_data_path TEXT,
    cache_size_bytes BIGINT,
    access_count INTEGER DEFAULT 1,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Performance metrics for voice generation
CREATE TABLE IF NOT EXISTS voice_performance_metrics (
    id SERIAL PRIMARY KEY,
    job_id UUID,
    character_name VARCHAR(255),
    text_length INTEGER,
    generation_time_ms INTEGER,
    audio_duration_ms INTEGER,
    voice_service VARCHAR(100), -- 'elevenlabs', 'fallback_tts', etc.
    quality_score FLOAT,
    error_occurred BOOLEAN DEFAULT FALSE,
    error_type VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES voice_generation_jobs(job_id) ON DELETE CASCADE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_voice_profiles_character ON voice_profiles(character_name);
CREATE INDEX IF NOT EXISTS idx_voice_jobs_status ON voice_generation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_voice_jobs_character ON voice_generation_jobs(character_name);
CREATE INDEX IF NOT EXISTS idx_voice_assignments_scene ON voice_assignments(scene_id);
CREATE INDEX IF NOT EXISTS idx_dialogue_scenes_project ON dialogue_scenes(project_id);
CREATE INDEX IF NOT EXISTS idx_dialogue_lines_scene ON dialogue_lines(scene_id);
CREATE INDEX IF NOT EXISTS idx_dialogue_lines_character ON dialogue_lines(character_name);
CREATE INDEX IF NOT EXISTS idx_lip_sync_character ON lip_sync_data(character_name);
CREATE INDEX IF NOT EXISTS idx_video_voice_processing_project ON video_voice_processing(project_id);
CREATE INDEX IF NOT EXISTS idx_video_voice_processing_status ON video_voice_processing(processing_status);
CREATE INDEX IF NOT EXISTS idx_quality_assessments_character ON voice_quality_assessments(character_name);
CREATE INDEX IF NOT EXISTS idx_audio_cache_key ON audio_processing_cache(cache_key);
CREATE INDEX IF NOT EXISTS idx_audio_cache_character ON audio_processing_cache(character_name);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_character ON voice_performance_metrics(character_name);

-- Create triggers for updated_at columns
CREATE TRIGGER update_voice_profiles_updated_at BEFORE UPDATE ON voice_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_dialogue_scenes_updated_at BEFORE UPDATE ON dialogue_scenes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_dialogue_lines_updated_at BEFORE UPDATE ON dialogue_lines
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default voice style templates
INSERT INTO voice_style_templates (template_name, emotion, voice_settings, description) VALUES
('neutral_conversational', 'neutral', '{
    "stability": 0.5,
    "similarity_boost": 0.8,
    "style": 0.0,
    "use_speaker_boost": true
}'::jsonb, 'Standard conversational tone'),

('excited_energetic', 'excited', '{
    "stability": 0.3,
    "similarity_boost": 0.9,
    "style": 0.4,
    "use_speaker_boost": true
}'::jsonb, 'High energy, excited speaking'),

('sad_melancholy', 'sad', '{
    "stability": 0.8,
    "similarity_boost": 0.6,
    "style": 0.2,
    "use_speaker_boost": false
}'::jsonb, 'Slow, melancholic delivery'),

('angry_intense', 'angry', '{
    "stability": 0.2,
    "similarity_boost": 0.9,
    "style": 0.6,
    "use_speaker_boost": true
}'::jsonb, 'Intense, forceful delivery'),

('whisper_quiet', 'whisper', '{
    "stability": 0.9,
    "similarity_boost": 0.4,
    "style": 0.1,
    "use_speaker_boost": false
}'::jsonb, 'Quiet, intimate whisper'),

('shout_loud', 'shout', '{
    "stability": 0.1,
    "similarity_boost": 1.0,
    "style": 0.8,
    "use_speaker_boost": true
}'::jsonb, 'Loud, commanding voice')

ON CONFLICT (template_name) DO NOTHING;

-- Insert sample character voice profiles
INSERT INTO voice_profiles (character_name, voice_id, voice_name, voice_settings, description) VALUES
('Akira_Protagonist', '21m00Tcm4TlvDq8ikWAM', 'Rachel', '{
    "stability": 0.4,
    "similarity_boost": 0.9,
    "style": 0.2,
    "use_speaker_boost": true
}'::jsonb, 'Young male protagonist with determined voice'),

('Yuki_Heroine', 'AZnzlk1XvdvUeBnXmlld', 'Domi', '{
    "stability": 0.6,
    "similarity_boost": 0.8,
    "style": 0.3,
    "use_speaker_boost": true
}'::jsonb, 'Female lead with gentle but strong voice'),

('Sensei_Mentor', 'VR6AewLTigWG4xSOukaG', 'Arnold', '{
    "stability": 0.8,
    "similarity_boost": 0.7,
    "style": 0.1,
    "use_speaker_boost": true
}'::jsonb, 'Wise mentor figure with calm authority'),

('Villain_Antagonist', 'onwK4e9ZLuTAKqWW03F9', 'Antoni', '{
    "stability": 0.3,
    "similarity_boost": 1.0,
    "style": 0.7,
    "use_speaker_boost": true
}'::jsonb, 'Menacing antagonist with commanding presence')

ON CONFLICT (character_name) DO NOTHING;

-- Create views for common queries
CREATE OR REPLACE VIEW scene_dialogue_summary AS
SELECT
    ds.scene_id,
    ds.scene_name,
    ds.project_id,
    ds.scene_duration,
    COUNT(dl.id) as line_count,
    COUNT(DISTINCT dl.character_name) as character_count,
    MIN(dl.timing_start) as scene_start,
    MAX(dl.timing_end) as scene_end,
    STRING_AGG(DISTINCT dl.character_name, ', ') as characters,
    ds.created_at
FROM dialogue_scenes ds
LEFT JOIN dialogue_lines dl ON ds.scene_id = dl.scene_id
GROUP BY ds.scene_id, ds.scene_name, ds.project_id, ds.scene_duration, ds.created_at;

CREATE OR REPLACE VIEW character_voice_usage AS
SELECT
    vp.character_name,
    vp.voice_name,
    vp.usage_count as profile_usage,
    COUNT(vgj.id) as generation_jobs,
    COUNT(CASE WHEN vgj.status = 'completed' THEN 1 END) as completed_jobs,
    COUNT(CASE WHEN vgj.status = 'failed' THEN 1 END) as failed_jobs,
    AVG(vgj.generation_time_ms) as avg_generation_time,
    vp.created_at as profile_created
FROM voice_profiles vp
LEFT JOIN voice_generation_jobs vgj ON vp.character_name = vgj.character_name
GROUP BY vp.id, vp.character_name, vp.voice_name, vp.usage_count, vp.created_at;

-- Create function to clean up old cache entries
CREATE OR REPLACE FUNCTION cleanup_audio_cache(days_old INTEGER DEFAULT 7)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Delete cache entries older than specified days and accessed less than 3 times
    DELETE FROM audio_processing_cache
    WHERE last_accessed < CURRENT_TIMESTAMP - (days_old || ' days')::INTERVAL
    AND access_count < 3;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO patrick;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO patrick;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO patrick;