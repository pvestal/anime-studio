-- Anime Production Database Schema
-- Supports autonomous Echo Brain control with state persistence

-- Create database if not exists
-- CREATE DATABASE IF NOT EXISTS anime_production;

-- Production jobs table (enhanced for Echo Brain integration)
CREATE TABLE IF NOT EXISTS production_jobs (
    id SERIAL PRIMARY KEY,
    project_id VARCHAR(255) NOT NULL,
    comfyui_job_id VARCHAR(255) UNIQUE,
    job_type VARCHAR(100) NOT NULL,
    prompt TEXT,
    style VARCHAR(100),
    frames INTEGER DEFAULT 120,
    status VARCHAR(50) DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    output_path TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    echo_task_id UUID,
    metadata JSONB
);

-- System state table for persistence
CREATE TABLE IF NOT EXISTS system_state (
    id SERIAL PRIMARY KEY,
    state_type VARCHAR(100) NOT NULL,
    state_data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

-- File organization tracking
CREATE TABLE IF NOT EXISTS organized_files (
    id SERIAL PRIMARY KEY,
    project_id VARCHAR(255) NOT NULL,
    original_path TEXT NOT NULL,
    organized_path TEXT NOT NULL,
    file_type VARCHAR(50),
    file_size BIGINT,
    organized_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    organized_by VARCHAR(100) DEFAULT 'echo_brain'
);

-- Workflow configurations
CREATE TABLE IF NOT EXISTS workflow_configs (
    id SERIAL PRIMARY KEY,
    workflow_name VARCHAR(255) UNIQUE NOT NULL,
    workflow_type VARCHAR(100),
    config_data JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Generation metrics for learning
CREATE TABLE IF NOT EXISTS generation_metrics (
    id SERIAL PRIMARY KEY,
    project_id VARCHAR(255) NOT NULL,
    generation_time_seconds FLOAT,
    vram_usage_mb INTEGER,
    quality_score FLOAT,
    user_rating INTEGER,
    parameters JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Anime characters and assets
CREATE TABLE IF NOT EXISTS anime_characters (
    id SERIAL PRIMARY KEY,
    character_name VARCHAR(255) NOT NULL,
    character_prompt TEXT,
    style_tags TEXT[],
    reference_images TEXT[],
    usage_count INTEGER DEFAULT 0,
    last_used TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- Progress tracking with verbose logging
CREATE TABLE IF NOT EXISTS progress_logs (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES production_jobs(id) ON DELETE CASCADE,
    log_level VARCHAR(20) DEFAULT 'INFO',
    message TEXT NOT NULL,
    progress_percentage INTEGER,
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Autonomous task history
CREATE TABLE IF NOT EXISTS anime_task_history (
    id SERIAL PRIMARY KEY,
    echo_task_id UUID,
    task_type VARCHAR(100),
    action VARCHAR(100),
    payload JSONB,
    result JSONB,
    execution_time_ms INTEGER,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_production_jobs_project_id ON production_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_production_jobs_status ON production_jobs(status);
CREATE INDEX IF NOT EXISTS idx_production_jobs_created_at ON production_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_organized_files_project_id ON organized_files(project_id);
CREATE INDEX IF NOT EXISTS idx_progress_logs_job_id ON progress_logs(job_id);
CREATE INDEX IF NOT EXISTS idx_anime_task_history_echo_task_id ON anime_task_history(echo_task_id);

-- Function to update timestamp on update
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
CREATE TRIGGER update_production_jobs_updated_at BEFORE UPDATE ON production_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workflow_configs_updated_at BEFORE UPDATE ON workflow_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default workflow configurations
INSERT INTO workflow_configs (workflow_name, workflow_type, config_data) VALUES
('animatediff_default', 'animatediff', '{
    "model": "dreamshaper_8.safetensors",
    "steps": 20,
    "cfg": 7.5,
    "sampler": "euler",
    "scheduler": "normal",
    "width": 512,
    "height": 512,
    "frames": 120
}'::jsonb),
('svd_video', 'svd', '{
    "model": "stable-video-diffusion-img2vid-xt.safetensors",
    "steps": 25,
    "cfg": 2.5,
    "fps": 7,
    "motion_bucket_id": 127,
    "augmentation_level": 0
}'::jsonb)
ON CONFLICT (workflow_name) DO NOTHING;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO patrick;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO patrick;