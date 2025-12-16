-- Asset Metadata Schema for CLIP-based Character Consistency
-- Extends existing anime production database schema
-- Created: 2025-12-15

-- Asset metadata: Store metadata for generated images/videos
CREATE TABLE IF NOT EXISTS asset_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_path TEXT NOT NULL UNIQUE,
    asset_hash TEXT NOT NULL, -- File content hash for integrity
    asset_type TEXT NOT NULL CHECK(asset_type IN ('image', 'video', 'audio')),
    file_size INTEGER,
    dimensions TEXT, -- JSON: {"width": 1024, "height": 1024}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    project_id INTEGER,
    scene_id INTEGER,
    character_name TEXT,
    generation_prompt TEXT,
    generation_metadata TEXT, -- JSON: ComfyUI params, etc.

    -- Quality metrics
    technical_quality_score REAL, -- Resolution, compression, artifacts
    visual_quality_score REAL, -- Composition, clarity, aesthetics
    character_consistency_score REAL, -- CLIP-based character consistency
    style_consistency_score REAL, -- Art style consistency

    -- Status tracking
    quality_gate_status TEXT DEFAULT 'pending' CHECK(
        quality_gate_status IN ('pending', 'passed', 'failed', 'manual_review')
    ),
    quality_gate_results TEXT, -- JSON: detailed gate results
    last_validated_at TIMESTAMP,

    -- Relationships
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE SET NULL
);

-- CLIP embeddings: Store CLIP feature vectors for character consistency
CREATE TABLE IF NOT EXISTS clip_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    character_name TEXT NOT NULL,
    model_name TEXT NOT NULL DEFAULT 'ViT-B/32', -- CLIP model used
    embedding_vector BLOB NOT NULL, -- Serialized numpy array
    embedding_dimension INTEGER NOT NULL DEFAULT 512,
    confidence_score REAL, -- How confident we are in the character detection
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (asset_id) REFERENCES asset_metadata(id) ON DELETE CASCADE,
    UNIQUE(asset_id, character_name, model_name)
);

-- Character references: Track reference images for each character
CREATE TABLE IF NOT EXISTS character_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_name TEXT NOT NULL,
    asset_id INTEGER NOT NULL,
    reference_type TEXT DEFAULT 'auto' CHECK(
        reference_type IN ('manual', 'auto', 'canonical', 'style_guide')
    ),
    reference_weight REAL DEFAULT 1.0, -- How much to weight this reference
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT, -- User who added this reference

    FOREIGN KEY (asset_id) REFERENCES asset_metadata(id) ON DELETE CASCADE,
    UNIQUE(character_name, asset_id)
);

-- Quality gate configurations: Configurable thresholds and rules
CREATE TABLE IF NOT EXISTS quality_gate_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_name TEXT NOT NULL UNIQUE,
    is_active BOOLEAN DEFAULT 1,

    -- Technical validation thresholds
    min_resolution TEXT, -- JSON: {"width": 512, "height": 512}
    max_file_size INTEGER,
    allowed_formats TEXT, -- JSON: ["png", "jpg", "webp"]

    -- Quality thresholds
    min_technical_quality REAL DEFAULT 0.7,
    min_visual_quality REAL DEFAULT 0.6,
    min_character_consistency REAL DEFAULT 0.75,
    min_style_consistency REAL DEFAULT 0.65,

    -- CLIP-specific settings
    clip_model TEXT DEFAULT 'ViT-B/32',
    character_similarity_threshold REAL DEFAULT 0.8,
    max_references_per_character INTEGER DEFAULT 10,
    auto_update_references BOOLEAN DEFAULT 1,

    -- Gate behavior
    require_manual_review BOOLEAN DEFAULT 0,
    auto_fail_on_threshold BOOLEAN DEFAULT 1,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Quality gate results: Detailed results from gate execution
CREATE TABLE IF NOT EXISTS quality_gate_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    config_id INTEGER NOT NULL,
    gate_name TEXT NOT NULL,

    -- Results
    passed BOOLEAN NOT NULL,
    score REAL,
    threshold REAL,
    details TEXT, -- JSON: detailed results and reasoning

    -- Metadata
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    execution_time_ms INTEGER, -- Performance tracking

    FOREIGN KEY (asset_id) REFERENCES asset_metadata(id) ON DELETE CASCADE,
    FOREIGN KEY (config_id) REFERENCES quality_gate_configs(id)
);

-- Character consistency history: Track consistency over time
CREATE TABLE IF NOT EXISTS character_consistency_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_name TEXT NOT NULL,
    asset_id INTEGER NOT NULL,

    -- Consistency metrics
    clip_similarity_score REAL NOT NULL,
    reference_count INTEGER NOT NULL,
    best_match_asset_id INTEGER,
    best_match_score REAL,

    -- Analysis details
    embedding_model TEXT NOT NULL,
    comparison_method TEXT DEFAULT 'cosine_similarity',
    analysis_metadata TEXT, -- JSON: detailed analysis results

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (asset_id) REFERENCES asset_metadata(id) ON DELETE CASCADE,
    FOREIGN KEY (best_match_asset_id) REFERENCES asset_metadata(id) ON DELETE SET NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_asset_metadata_character ON asset_metadata(character_name);
CREATE INDEX IF NOT EXISTS idx_asset_metadata_project ON asset_metadata(project_id);
CREATE INDEX IF NOT EXISTS idx_asset_metadata_created ON asset_metadata(created_at);
CREATE INDEX IF NOT EXISTS idx_asset_metadata_quality_status ON asset_metadata(quality_gate_status);

CREATE INDEX IF NOT EXISTS idx_clip_embeddings_character ON clip_embeddings(character_name);
CREATE INDEX IF NOT EXISTS idx_clip_embeddings_asset ON clip_embeddings(asset_id);

CREATE INDEX IF NOT EXISTS idx_character_refs_character ON character_references(character_name);
CREATE INDEX IF NOT EXISTS idx_character_refs_active ON character_references(character_name, is_active);

CREATE INDEX IF NOT EXISTS idx_quality_results_asset ON quality_gate_results(asset_id);
CREATE INDEX IF NOT EXISTS idx_quality_results_gate ON quality_gate_results(gate_name);

CREATE INDEX IF NOT EXISTS idx_consistency_history_character ON character_consistency_history(character_name);
CREATE INDEX IF NOT EXISTS idx_consistency_history_created ON character_consistency_history(created_at);

-- Insert default quality gate configuration
INSERT OR REPLACE INTO quality_gate_configs (
    config_name,
    is_active,
    min_resolution,
    max_file_size,
    allowed_formats,
    min_technical_quality,
    min_visual_quality,
    min_character_consistency,
    min_style_consistency,
    clip_model,
    character_similarity_threshold,
    max_references_per_character,
    auto_update_references,
    require_manual_review,
    auto_fail_on_threshold
) VALUES (
    'default_production',
    1,
    '{"width": 512, "height": 512}',
    10485760, -- 10MB
    '["png", "jpg", "jpeg", "webp"]',
    0.7,
    0.6,
    0.75,
    0.65,
    'ViT-B/32',
    0.8,
    10,
    1,
    0,
    1
);

-- Insert high-quality gate configuration for hero characters
INSERT OR REPLACE INTO quality_gate_configs (
    config_name,
    is_active,
    min_resolution,
    max_file_size,
    allowed_formats,
    min_technical_quality,
    min_visual_quality,
    min_character_consistency,
    min_style_consistency,
    clip_model,
    character_similarity_threshold,
    max_references_per_character,
    auto_update_references,
    require_manual_review,
    auto_fail_on_threshold
) VALUES (
    'hero_character_strict',
    1,
    '{"width": 1024, "height": 1024}',
    20971520, -- 20MB
    '["png"]',
    0.85,
    0.8,
    0.9,
    0.85,
    'ViT-B/32',
    0.9,
    15,
    1,
    1, -- Require manual review for hero characters
    0  -- Don't auto-fail, require manual review instead
);

-- Views for common queries
CREATE VIEW IF NOT EXISTS asset_quality_summary AS
SELECT
    am.id,
    am.asset_path,
    am.character_name,
    am.quality_gate_status,
    am.character_consistency_score,
    am.technical_quality_score,
    am.visual_quality_score,
    COUNT(cr.id) as reference_count,
    MAX(cch.clip_similarity_score) as best_clip_score,
    am.created_at
FROM asset_metadata am
LEFT JOIN character_references cr ON cr.character_name = am.character_name AND cr.is_active = 1
LEFT JOIN character_consistency_history cch ON cch.asset_id = am.id
GROUP BY am.id;

CREATE VIEW IF NOT EXISTS character_reference_summary AS
SELECT
    character_name,
    COUNT(*) as total_references,
    COUNT(CASE WHEN reference_type = 'canonical' THEN 1 END) as canonical_count,
    COUNT(CASE WHEN reference_type = 'manual' THEN 1 END) as manual_count,
    COUNT(CASE WHEN reference_type = 'auto' THEN 1 END) as auto_count,
    AVG(reference_weight) as avg_weight,
    MAX(created_at) as last_updated
FROM character_references
WHERE is_active = 1
GROUP BY character_name;