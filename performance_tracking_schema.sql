-- Enhanced Performance Tracking Schema for ML Prediction
-- Extends existing generation_performance table with additional metrics

-- Add missing columns to generation_performance table for better ML predictions
ALTER TABLE anime_api.generation_performance ADD COLUMN IF NOT EXISTS job_type VARCHAR(50);
ALTER TABLE anime_api.generation_performance ADD COLUMN IF NOT EXISTS success_rate NUMERIC(5,2);
ALTER TABLE anime_api.generation_performance ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;
ALTER TABLE anime_api.generation_performance ADD COLUMN IF NOT EXISTS disk_io_mb INTEGER;
ALTER TABLE anime_api.generation_performance ADD COLUMN IF NOT EXISTS network_latency_ms NUMERIC(10,3);
ALTER TABLE anime_api.generation_performance ADD COLUMN IF NOT EXISTS model_load_time_seconds NUMERIC(10,3);
ALTER TABLE anime_api.generation_performance ADD COLUMN IF NOT EXISTS preprocessing_time_seconds NUMERIC(10,3);
ALTER TABLE anime_api.generation_performance ADD COLUMN IF NOT EXISTS postprocessing_time_seconds NUMERIC(10,3);
ALTER TABLE anime_api.generation_performance ADD COLUMN IF NOT EXISTS complexity_score NUMERIC(5,2);
ALTER TABLE anime_api.generation_performance ADD COLUMN IF NOT EXISTS predicted_time_seconds NUMERIC(10,3);
ALTER TABLE anime_api.generation_performance ADD COLUMN IF NOT EXISTS prediction_accuracy NUMERIC(5,2);

-- Create performance prediction models table
CREATE TABLE IF NOT EXISTS anime_api.performance_prediction_models (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_type VARCHAR(50) NOT NULL, -- 'linear_regression', 'random_forest', 'neural_network'
    pipeline_type VARCHAR(20) NOT NULL,
    model_data BYTEA NOT NULL, -- Serialized scikit-learn model
    feature_columns JSON NOT NULL, -- List of features used
    accuracy_score NUMERIC(5,2),
    mean_absolute_error NUMERIC(10,3),
    training_data_count INTEGER,
    last_trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create performance trends table for historical analysis
CREATE TABLE IF NOT EXISTS anime_api.performance_trends (
    id SERIAL PRIMARY KEY,
    trend_date DATE NOT NULL,
    pipeline_type VARCHAR(20) NOT NULL,
    avg_generation_time NUMERIC(10,3),
    median_generation_time NUMERIC(10,3),
    min_generation_time NUMERIC(10,3),
    max_generation_time NUMERIC(10,3),
    success_rate NUMERIC(5,2),
    total_jobs INTEGER,
    total_failures INTEGER,
    avg_queue_time NUMERIC(10,3),
    avg_gpu_utilization NUMERIC(5,2),
    bottlenecks JSON, -- Array of identified bottlenecks
    recommendations JSON, -- Performance improvement recommendations
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create performance alerts table for monitoring
CREATE TABLE IF NOT EXISTS anime_api.performance_alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(50) NOT NULL, -- 'slow_generation', 'high_failure_rate', 'resource_bottleneck'
    severity VARCHAR(20) NOT NULL, -- 'low', 'medium', 'high', 'critical'
    message TEXT NOT NULL,
    details JSON,
    job_id INTEGER,
    threshold_value NUMERIC(10,3),
    actual_value NUMERIC(10,3),
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance optimization
CREATE INDEX IF NOT EXISTS idx_performance_prediction_models_pipeline ON anime_api.performance_prediction_models(pipeline_type, is_active);
CREATE INDEX IF NOT EXISTS idx_performance_trends_date_pipeline ON anime_api.performance_trends(trend_date, pipeline_type);
CREATE INDEX IF NOT EXISTS idx_performance_alerts_severity ON anime_api.performance_alerts(severity, created_at DESC) WHERE NOT is_resolved;
CREATE INDEX IF NOT EXISTS idx_generation_performance_job_type ON anime_api.generation_performance(job_type) WHERE job_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_generation_performance_complexity ON anime_api.generation_performance(complexity_score) WHERE complexity_score IS NOT NULL;

-- Create view for ML training data
CREATE OR REPLACE VIEW anime_api.ml_training_data AS
SELECT
    gp.id,
    gp.pipeline_type,
    gp.frame_count,
    gp.resolution,
    gp.steps,
    gp.guidance_scale,
    gp.complexity_score,
    gp.job_type,
    gp.model_version,
    gp.gpu_model,
    gp.vram_used_mb,
    gp.total_time_seconds,
    gp.processing_time_seconds,
    gp.queue_time_seconds,
    gp.initialization_time_seconds,
    gp.gpu_utilization_avg,
    gp.cpu_utilization_avg,
    gp.memory_used_mb,
    gp.retry_count,
    gp.success_rate,
    gp.created_at,
    -- Derived features for ML
    CASE
        WHEN gp.resolution LIKE '%x%' THEN
            CAST(SPLIT_PART(gp.resolution, 'x', 1) AS INTEGER) *
            CAST(SPLIT_PART(gp.resolution, 'x', 2) AS INTEGER)
        ELSE 0
    END as resolution_pixels,
    EXTRACT(HOUR FROM gp.created_at) as generation_hour,
    EXTRACT(DOW FROM gp.created_at) as generation_dow,
    gp.frame_count * COALESCE(gp.steps, 20) as total_computation_units
FROM anime_api.generation_performance gp
WHERE gp.total_time_seconds IS NOT NULL;

-- Performance thresholds configuration
INSERT INTO anime_api.performance_alerts (alert_type, severity, message, threshold_value, created_at)
VALUES
    ('slow_generation', 'medium', 'Image generation taking longer than expected', 120.0, CURRENT_TIMESTAMP),
    ('slow_generation', 'high', 'Video generation taking longer than expected', 300.0, CURRENT_TIMESTAMP),
    ('high_failure_rate', 'high', 'Generation failure rate above threshold', 0.1, CURRENT_TIMESTAMP),
    ('resource_bottleneck', 'medium', 'GPU utilization below optimal range', 0.6, CURRENT_TIMESTAMP)
ON CONFLICT DO NOTHING;

-- Comment documentation
COMMENT ON TABLE anime_api.performance_prediction_models IS 'Stores trained ML models for performance prediction';
COMMENT ON TABLE anime_api.performance_trends IS 'Daily aggregated performance metrics for trend analysis';
COMMENT ON TABLE anime_api.performance_alerts IS 'System alerts for performance anomalies';
COMMENT ON VIEW anime_api.ml_training_data IS 'Preprocessed data view for ML model training';