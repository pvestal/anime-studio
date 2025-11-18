-- Intent Classification System Database Schema
-- Supports comprehensive intent tracking, user preferences, and learning patterns

-- User preferences table for storing user-specific settings
CREATE TABLE IF NOT EXISTS user_preferences (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL UNIQUE,
    preferences_data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,

    -- Indexes for performance
    INDEX idx_user_preferences_user_id (user_id),
    INDEX idx_user_preferences_updated (updated_at)
);

-- Intent classifications table for storing all classification results
CREATE TABLE IF NOT EXISTS intent_classifications (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(255) NOT NULL UNIQUE,
    user_id VARCHAR(255) DEFAULT 'default',

    -- Original user input
    user_prompt TEXT NOT NULL,
    processed_prompt TEXT,

    -- Classification results
    content_type VARCHAR(50) NOT NULL, -- image, video, audio, mixed_media
    generation_scope VARCHAR(50) NOT NULL, -- character_profile, character_scene, etc.
    style_preference VARCHAR(50) NOT NULL, -- photorealistic_anime, traditional_anime, etc.
    urgency_level VARCHAR(50) NOT NULL, -- immediate, urgent, standard, etc.
    complexity_level VARCHAR(50) NOT NULL, -- simple, moderate, complex, expert

    -- Technical specifications
    character_names JSONB DEFAULT '[]',
    duration_seconds INTEGER,
    frame_count INTEGER,
    resolution VARCHAR(20),
    aspect_ratio VARCHAR(10),
    quality_level VARCHAR(20) NOT NULL DEFAULT 'standard',
    post_processing JSONB DEFAULT '[]',
    output_format VARCHAR(10) NOT NULL DEFAULT 'png',

    -- Routing information
    target_service VARCHAR(100) NOT NULL,
    target_workflow VARCHAR(100) NOT NULL,
    estimated_time_minutes INTEGER NOT NULL DEFAULT 5,
    estimated_vram_gb DECIMAL(4,2) NOT NULL DEFAULT 4.0,

    -- Analysis metadata
    confidence_score DECIMAL(3,2) NOT NULL DEFAULT 0.5,
    ambiguity_flags JSONB DEFAULT '[]',
    fallback_options JSONB DEFAULT '[]',

    -- Complete classification data (for analysis)
    classification_data JSONB NOT NULL,

    -- Execution tracking
    execution_status VARCHAR(50) DEFAULT 'pending',
    execution_started_at TIMESTAMP,
    execution_completed_at TIMESTAMP,
    execution_results JSONB,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes for performance
    INDEX idx_intent_class_request_id (request_id),
    INDEX idx_intent_class_user_id (user_id),
    INDEX idx_intent_class_content_type (content_type),
    INDEX idx_intent_class_created (created_at),
    INDEX idx_intent_class_confidence (confidence_score),
    INDEX idx_intent_class_execution_status (execution_status)
);

-- Pattern learning table for improving classification accuracy
CREATE TABLE IF NOT EXISTS intent_pattern_learning (
    id SERIAL PRIMARY KEY,

    -- Pattern identification
    pattern_text TEXT NOT NULL,
    pattern_type VARCHAR(50) NOT NULL, -- content_type, scope, style, urgency, complexity
    classification_result VARCHAR(50) NOT NULL,

    -- Learning metrics
    accuracy_score DECIMAL(3,2) DEFAULT 0.5,
    usage_count INTEGER DEFAULT 1,
    success_rate DECIMAL(3,2) DEFAULT 0.5,

    -- Pattern context
    context_requirements JSONB DEFAULT '{}',
    negative_indicators JSONB DEFAULT '[]',

    -- Learning metadata
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,

    -- Manual review
    manually_verified BOOLEAN DEFAULT FALSE,
    verification_notes TEXT,

    UNIQUE(pattern_text, pattern_type, classification_result),
    INDEX idx_pattern_learning_type (pattern_type),
    INDEX idx_pattern_learning_accuracy (accuracy_score),
    INDEX idx_pattern_learning_usage (usage_count)
);

-- User behavior analytics for preference learning
CREATE TABLE IF NOT EXISTS user_behavior_analytics (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,

    -- Behavior tracking
    action_type VARCHAR(100) NOT NULL, -- request, modification, approval, etc.
    action_data JSONB NOT NULL,

    -- Request context
    related_request_id VARCHAR(255),
    session_id VARCHAR(255),

    -- Preference inference
    inferred_preferences JSONB DEFAULT '{}',
    preference_confidence DECIMAL(3,2) DEFAULT 0.5,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_behavior_user_id (user_id),
    INDEX idx_behavior_action_type (action_type),
    INDEX idx_behavior_created (created_at),

    FOREIGN KEY (related_request_id) REFERENCES intent_classifications(request_id)
);

-- Workflow performance metrics for optimization
CREATE TABLE IF NOT EXISTS workflow_performance_metrics (
    id SERIAL PRIMARY KEY,

    -- Workflow identification
    target_service VARCHAR(100) NOT NULL,
    target_workflow VARCHAR(100) NOT NULL,
    content_type VARCHAR(50) NOT NULL,
    complexity_level VARCHAR(50) NOT NULL,

    -- Performance metrics
    execution_time_minutes INTEGER NOT NULL,
    vram_usage_gb DECIMAL(4,2) NOT NULL,
    cpu_usage_percent INTEGER,
    success_rate DECIMAL(3,2) NOT NULL,
    quality_score DECIMAL(3,2),

    -- Request characteristics
    resolution VARCHAR(20),
    duration_seconds INTEGER,
    post_processing_steps INTEGER DEFAULT 0,

    -- System state
    system_load_percent INTEGER,
    available_vram_gb DECIMAL(4,2),
    concurrent_jobs INTEGER DEFAULT 0,

    -- Results
    output_file_size_mb DECIMAL(8,2),
    user_satisfaction_score DECIMAL(3,2),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_workflow_perf_service (target_service),
    INDEX idx_workflow_perf_type (content_type),
    INDEX idx_workflow_perf_complexity (complexity_level),
    INDEX idx_workflow_perf_success (success_rate),
    INDEX idx_workflow_perf_created (created_at)
);

-- Ambiguity resolution strategies
CREATE TABLE IF NOT EXISTS ambiguity_resolution_strategies (
    id SERIAL PRIMARY KEY,

    -- Ambiguity identification
    ambiguity_type VARCHAR(100) NOT NULL,
    ambiguity_pattern TEXT NOT NULL,
    confidence_threshold DECIMAL(3,2) NOT NULL DEFAULT 0.7,

    -- Resolution strategy
    resolution_strategy VARCHAR(100) NOT NULL, -- clarification_prompt, default_value, user_selection, etc.
    strategy_data JSONB NOT NULL DEFAULT '{}',

    -- Strategy performance
    usage_count INTEGER DEFAULT 0,
    success_rate DECIMAL(3,2) DEFAULT 0.5,
    average_resolution_time_seconds INTEGER DEFAULT 30,

    -- Configuration
    is_active BOOLEAN DEFAULT TRUE,
    priority_order INTEGER DEFAULT 10,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_ambiguity_type (ambiguity_type),
    INDEX idx_ambiguity_priority (priority_order),
    INDEX idx_ambiguity_success (success_rate)
);

-- Feedback and corrections for learning
CREATE TABLE IF NOT EXISTS classification_feedback (
    id SERIAL PRIMARY KEY,

    -- Reference to original classification
    request_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,

    -- Feedback type
    feedback_type VARCHAR(50) NOT NULL, -- correction, rating, preference
    feedback_data JSONB NOT NULL,

    -- Original vs corrected values
    original_classification JSONB NOT NULL,
    corrected_classification JSONB,

    -- Feedback metadata
    feedback_source VARCHAR(50) DEFAULT 'user', -- user, system, admin
    confidence_in_feedback DECIMAL(3,2) DEFAULT 1.0,

    -- Learning impact
    applied_to_model BOOLEAN DEFAULT FALSE,
    impact_score DECIMAL(3,2),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_feedback_request_id (request_id),
    INDEX idx_feedback_user_id (user_id),
    INDEX idx_feedback_type (feedback_type),
    INDEX idx_feedback_applied (applied_to_model),

    FOREIGN KEY (request_id) REFERENCES intent_classifications(request_id)
);

-- Quick lookup tables for common classifications
CREATE TABLE IF NOT EXISTS quick_classification_templates (
    id SERIAL PRIMARY KEY,

    -- Template identification
    template_name VARCHAR(255) NOT NULL UNIQUE,
    template_description TEXT,

    -- Quick classification data
    template_classification JSONB NOT NULL,
    template_prompt_patterns JSONB NOT NULL DEFAULT '[]',

    -- Usage tracking
    usage_count INTEGER DEFAULT 0,
    success_rate DECIMAL(3,2) DEFAULT 0.5,

    -- Template metadata
    is_active BOOLEAN DEFAULT TRUE,
    is_featured BOOLEAN DEFAULT FALSE,
    created_by VARCHAR(255) DEFAULT 'system',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_quick_template_name (template_name),
    INDEX idx_quick_template_active (is_active),
    INDEX idx_quick_template_featured (is_featured)
);

-- Insert default quick templates
INSERT INTO quick_classification_templates (template_name, template_description, template_classification, template_prompt_patterns) VALUES
(
    'Character Profile Image',
    'Single character portrait/profile image generation',
    '{
        "content_type": "image",
        "generation_scope": "character_profile",
        "style_preference": "traditional_anime",
        "urgency_level": "standard",
        "complexity_level": "moderate",
        "quality_level": "high",
        "resolution": "768x768",
        "output_format": "png"
    }',
    '["character profile", "character design", "portrait of", "design a character"]'
),
(
    'Short Action Video',
    '5-30 second action sequence video',
    '{
        "content_type": "video",
        "generation_scope": "action_sequence",
        "style_preference": "cinematic",
        "urgency_level": "standard",
        "complexity_level": "complex",
        "quality_level": "high",
        "duration_seconds": 15,
        "output_format": "mp4"
    }',
    '["action scene", "fighting", "battle sequence", "short video"]'
),
(
    'Environment Background',
    'Background/environment scene without characters',
    '{
        "content_type": "image",
        "generation_scope": "environment",
        "style_preference": "traditional_anime",
        "urgency_level": "standard",
        "complexity_level": "moderate",
        "quality_level": "high",
        "resolution": "1024x768",
        "output_format": "png"
    }',
    '["background", "environment", "landscape", "cityscape", "setting"]'
);

-- Insert default user preferences
INSERT INTO user_preferences (user_id, preferences_data) VALUES
(
    'default',
    '{
        "preferred_style": "traditional_anime",
        "default_quality": "high",
        "preferred_duration": 5,
        "auto_upscale": true,
        "notification_preferences": {
            "completion": true,
            "progress": false,
            "errors": true
        },
        "workflow_preferences": {
            "fast_preview": true,
            "quality_over_speed": false
        }
    }'
);

-- Insert common ambiguity resolution strategies
INSERT INTO ambiguity_resolution_strategies (ambiguity_type, ambiguity_pattern, resolution_strategy, strategy_data) VALUES
(
    'content_type_unclear',
    'Could be image or video',
    'user_selection',
    '{"options": ["image", "video"], "default": "image", "prompt": "Would you like an image or video?"}'
),
(
    'character_name_missing',
    'Character mentioned but name unclear',
    'clarification_prompt',
    '{"prompt": "What would you like to name this character?", "default": "Unnamed Character"}'
),
(
    'style_preference_ambiguous',
    'Style not specified clearly',
    'default_value',
    '{"default": "traditional_anime", "reason": "Most common user preference"}'
),
(
    'duration_not_specified',
    'Video requested but no duration given',
    'user_selection',
    '{"options": ["5 seconds", "15 seconds", "30 seconds", "1 minute"], "default": "15 seconds"}'
);

-- Create indexes for performance optimization
CREATE INDEX IF NOT EXISTS idx_intent_class_composite ON intent_classifications(content_type, generation_scope, style_preference);
CREATE INDEX IF NOT EXISTS idx_user_prefs_data_gin ON user_preferences USING GIN(preferences_data);
CREATE INDEX IF NOT EXISTS idx_classification_data_gin ON intent_classifications USING GIN(classification_data);
CREATE INDEX IF NOT EXISTS idx_behavior_data_gin ON user_behavior_analytics USING GIN(action_data);

-- Create a view for quick classification statistics
CREATE VIEW classification_statistics AS
SELECT
    content_type,
    generation_scope,
    style_preference,
    COUNT(*) as request_count,
    AVG(confidence_score) as avg_confidence,
    AVG(estimated_time_minutes) as avg_estimated_time,
    COUNT(CASE WHEN execution_status = 'completed' THEN 1 END) as completed_count,
    ROUND(
        COUNT(CASE WHEN execution_status = 'completed' THEN 1 END)::numeric /
        COUNT(*)::numeric * 100, 2
    ) as completion_rate
FROM intent_classifications
WHERE created_at > CURRENT_DATE - INTERVAL '30 days'
GROUP BY content_type, generation_scope, style_preference
ORDER BY request_count DESC;

-- Function to update user preferences based on behavior
CREATE OR REPLACE FUNCTION update_user_preferences_from_behavior()
RETURNS TRIGGER AS $$
BEGIN
    -- Update user preferences when new behavior is recorded
    IF NEW.action_type = 'request_approval' THEN
        UPDATE user_preferences
        SET
            preferences_data = preferences_data || NEW.inferred_preferences,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = NEW.user_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update user preferences
CREATE TRIGGER trigger_update_preferences_from_behavior
    AFTER INSERT ON user_behavior_analytics
    FOR EACH ROW
    EXECUTE FUNCTION update_user_preferences_from_behavior();

-- Function to calculate classification accuracy over time
CREATE OR REPLACE FUNCTION calculate_classification_accuracy(days_back INTEGER DEFAULT 30)
RETURNS TABLE(
    classification_type VARCHAR,
    accuracy_score DECIMAL,
    sample_size INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        CONCAT(ic.content_type, '_', ic.generation_scope) as classification_type,
        COALESCE(AVG(cf.confidence_in_feedback), 0.5) as accuracy_score,
        COUNT(*)::INTEGER as sample_size
    FROM intent_classifications ic
    LEFT JOIN classification_feedback cf ON ic.request_id = cf.request_id
    WHERE ic.created_at > CURRENT_DATE - INTERVAL '1 day' * days_back
    GROUP BY classification_type
    HAVING COUNT(*) >= 5  -- Only include classifications with enough samples
    ORDER BY accuracy_score DESC;
END;
$$ LANGUAGE plpgsql;

-- Comments for documentation
COMMENT ON TABLE intent_classifications IS 'Stores all intent classification results for learning and analytics';
COMMENT ON TABLE user_preferences IS 'User-specific preferences for anime generation';
COMMENT ON TABLE intent_pattern_learning IS 'Machine learning patterns for improving classification accuracy';
COMMENT ON TABLE workflow_performance_metrics IS 'Performance tracking for different generation workflows';
COMMENT ON TABLE ambiguity_resolution_strategies IS 'Strategies for handling ambiguous user requests';
COMMENT ON TABLE classification_feedback IS 'User feedback for improving classification accuracy';
COMMENT ON TABLE quick_classification_templates IS 'Pre-defined templates for common generation types';

-- Grant permissions (adjust as needed for your user setup)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO patrick;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO patrick;