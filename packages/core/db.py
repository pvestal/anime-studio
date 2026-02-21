"""Database — connection pool, migrations, and cached queries."""

import json
import logging
import time as _time

import asyncpg

from .config import DB_CONFIG

logger = logging.getLogger(__name__)

# Module-level pool reference
_pool: asyncpg.Pool | None = None

# Cache for character→project mapping from DB
_char_project_cache: dict = {}
_cache_time: float = 0


async def init_pool():
    """Create the asyncpg connection pool. Call once at startup."""
    global _pool
    _pool = await asyncpg.create_pool(
        host=DB_CONFIG["host"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        min_size=2,
        max_size=10,
    )
    logger.info(f"DB pool created: {DB_CONFIG['database']}@{DB_CONFIG['host']}")


async def get_pool() -> asyncpg.Pool:
    """Return the connection pool, initializing if needed."""
    global _pool
    if _pool is None:
        await init_pool()
    return _pool


async def get_connection():
    """Acquire a connection from the pool. Use as: async with get_connection() as conn:"""
    pool = await get_pool()
    return pool.acquire()


async def connect_direct() -> asyncpg.Connection:
    """Open a direct (non-pooled) connection. Caller must close it."""
    return await asyncpg.connect(
        host=DB_CONFIG["host"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )


async def run_migrations():
    """Run schema migrations at startup. Idempotent (uses IF NOT EXISTS)."""
    try:
        conn = await connect_direct()

        # world_settings table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS world_settings (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                style_preamble TEXT,
                art_style TEXT,
                aesthetic TEXT,
                color_palette JSONB,
                cinematography JSONB,
                world_location JSONB,
                time_period TEXT,
                production_notes TEXT,
                known_issues JSONB,
                negative_prompt_guidance TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(project_id)
            )
        """)

        # Enhance storylines table
        for col, coltype in [
            ("tone", "TEXT"),
            ("themes", "TEXT[]"),
            ("humor_style", "TEXT"),
            ("story_arcs", "JSONB"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE storylines ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # Enhance projects table
        for col, coltype in [
            ("premise", "TEXT"),
            ("content_rating", "TEXT"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE projects ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # Scene Builder: enhance scenes table
        for col, coltype in [
            ("location", "TEXT"),
            ("time_of_day", "TEXT"),
            ("weather", "TEXT"),
            ("mood", "TEXT"),
            ("target_duration_seconds", "INTEGER DEFAULT 30"),
            ("actual_duration_seconds", "FLOAT"),
            ("final_video_path", "TEXT"),
            ("total_shots", "INTEGER DEFAULT 0"),
            ("completed_shots", "INTEGER DEFAULT 0"),
            ("current_generating_shot_id", "UUID"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE scenes ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # Scene Builder: enhance shots table
        for col, coltype in [
            ("source_image_path", "TEXT"),
            ("motion_prompt", "TEXT"),
            ("first_frame_path", "TEXT"),
            ("last_frame_path", "TEXT"),
            ("output_video_path", "TEXT"),
            ("comfyui_prompt_id", "TEXT"),
            ("seed", "INTEGER"),
            ("steps", "INTEGER"),
            ("use_f1", "BOOLEAN DEFAULT FALSE"),
            ("quality_score", "FLOAT"),
            ("error_message", "TEXT"),
            ("generation_time_seconds", "FLOAT"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE shots ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # Shot dialogue columns
        for col, coltype in [
            ("dialogue_text", "TEXT"),
            ("dialogue_character_slug", "VARCHAR(255)"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE shots ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # Scene dialogue audio path
        for col, coltype in [
            ("dialogue_audio_path", "TEXT"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE scenes ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # Scene audio overlay columns
        for col, coltype in [
            ("audio_track_id", "VARCHAR(255)"),
            ("audio_track_name", "VARCHAR(500)"),
            ("audio_track_artist", "VARCHAR(500)"),
            ("audio_preview_url", "TEXT"),
            ("audio_preview_path", "TEXT"),
            ("audio_fade_in", "FLOAT DEFAULT 1.0"),
            ("audio_fade_out", "FLOAT DEFAULT 2.0"),
            ("audio_start_offset", "FLOAT DEFAULT 0"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE scenes ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # --- Episode Assembly ---

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                episode_number INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                story_arc TEXT,
                status VARCHAR(50) DEFAULT 'draft',
                final_video_path TEXT,
                thumbnail_path TEXT,
                actual_duration_seconds FLOAT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS episode_scenes (
                id SERIAL PRIMARY KEY,
                episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
                scene_id UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                transition VARCHAR(50) DEFAULT 'cut',
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(episode_id, scene_id),
                UNIQUE(episode_id, position)
            )
        """)

        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_episodes_project ON episodes(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_episodes_number ON episodes(project_id, episode_number)",
            "CREATE INDEX IF NOT EXISTS idx_episode_scenes_episode ON episode_scenes(episode_id)",
            "CREATE INDEX IF NOT EXISTS idx_episode_scenes_scene ON episode_scenes(scene_id)",
        ]:
            await conn.execute(idx_sql)

        # --- Phase 1: Autonomous Learning Infrastructure ---

        # generation_history: add autonomy columns to pre-existing table
        # (table exists with character_id INT schema; we add character_slug etc.)
        for col, coltype in [
            ("character_slug", "VARCHAR(255)"),
            ("project_name", "VARCHAR(255)"),
            ("generation_type", "VARCHAR(50) DEFAULT 'image'"),
            ("comfyui_prompt_id", "VARCHAR(255)"),
            ("checkpoint_model", "VARCHAR(255)"),
            ("prompt", "TEXT"),
            ("cfg_scale", "FLOAT"),
            ("steps", "INTEGER"),
            ("sampler", "VARCHAR(100)"),
            ("scheduler", "VARCHAR(100)"),
            ("width", "INTEGER"),
            ("height", "INTEGER"),
            ("quality_score", "FLOAT"),
            ("character_match", "FLOAT"),
            ("clarity", "FLOAT"),
            ("training_value", "FLOAT"),
            ("solo", "BOOLEAN"),
            ("species_verified", "BOOLEAN"),
            ("artifact_path", "TEXT"),
            ("status", "VARCHAR(50) DEFAULT 'pending'"),
            ("rejection_categories", "TEXT[]"),
            ("generated_at", "TIMESTAMP DEFAULT NOW()"),
            ("reviewed_at", "TIMESTAMP"),
            ("generation_time_ms", "INTEGER"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE generation_history ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # rejections — structured rejection data (replaces feedback.json for queries)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rejections (
                id SERIAL PRIMARY KEY,
                character_slug VARCHAR(255) NOT NULL,
                project_name VARCHAR(255),
                image_name VARCHAR(500),
                generation_history_id INTEGER REFERENCES generation_history(id),
                categories TEXT[] NOT NULL DEFAULT '{}',
                feedback_text TEXT,
                negative_additions TEXT[],
                source VARCHAR(50) DEFAULT 'vision',
                quality_score FLOAT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # approvals — successful generations (queryable history)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                id SERIAL PRIMARY KEY,
                character_slug VARCHAR(255) NOT NULL,
                project_name VARCHAR(255),
                image_name VARCHAR(500),
                generation_history_id INTEGER REFERENCES generation_history(id),
                quality_score FLOAT,
                auto_approved BOOLEAN DEFAULT FALSE,
                vision_review JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # learned_patterns — what works / what doesn't (populated by learning_system)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS learned_patterns (
                id SERIAL PRIMARY KEY,
                character_slug VARCHAR(255),
                project_name VARCHAR(255),
                pattern_type VARCHAR(50) NOT NULL,
                checkpoint_model VARCHAR(255),
                prompt_keywords TEXT[],
                quality_score_avg FLOAT,
                frequency INTEGER DEFAULT 1,
                cfg_range_min FLOAT,
                cfg_range_max FLOAT,
                steps_range_min INTEGER,
                steps_range_max INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # autonomy_decisions — audit trail for every autonomous action
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS autonomy_decisions (
                id SERIAL PRIMARY KEY,
                decision_type VARCHAR(100) NOT NULL,
                character_slug VARCHAR(255),
                project_name VARCHAR(255),
                input_context JSONB,
                decision_made VARCHAR(255),
                confidence_score FLOAT,
                reasoning TEXT,
                outcome VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                resolved_at TIMESTAMP
            )
        """)

        # --- Phase 5: Quality Gates & Consistency ---

        # Quality gates — add autonomy columns to pre-existing table
        # (existing schema: project_name, stage, metric, threshold, is_blocking, description)
        for col, coltype in [
            ("gate_name", "VARCHAR(255)"),
            ("gate_type", "VARCHAR(100)"),
            ("threshold_value", "FLOAT"),
            ("is_active", "BOOLEAN DEFAULT TRUE"),
            ("created_at", "TIMESTAMP DEFAULT NOW()"),
            ("metadata", "JSONB"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE quality_gates ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # Seed autonomy gates (using new columns, coexisting with existing per-project gates)
        for gate_name, gate_type, threshold_value, desc in [
            ("auto_reject_threshold", "auto_reject", 0.4, "Images below this quality score are auto-rejected"),
            ("auto_approve_threshold", "auto_approve", 0.8, "Images above this score (and solo) are auto-approved"),
            ("scene_shot_minimum", "overall_consistency", 0.4, "Minimum quality for scene builder shots"),
        ]:
            existing = await conn.fetchval(
                "SELECT COUNT(*) FROM quality_gates WHERE gate_name = $1", gate_name
            )
            if not existing:
                await conn.execute("""
                    INSERT INTO quality_gates (project_name, stage, metric, threshold,
                                              gate_name, gate_type, threshold_value, description)
                    VALUES ($1::varchar(50), $2::varchar(30), $3::varchar(30), $4::numeric(5,4),
                            $5, $6, $7, $8)
                """, gate_name[:50], gate_type[:30], gate_type[:30], threshold_value,
                    gate_name, gate_type, threshold_value, desc)

        # Consistency columns on generation_history
        for col, coltype in [
            ("correction_of", "INTEGER"),
            ("correction_strategies", "TEXT[]"),
            ("face_similarity", "FLOAT"),
            ("style_similarity", "FLOAT"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE generation_history ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # --- Voice Pipeline Tables ---

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS voice_speakers (
                id SERIAL PRIMARY KEY,
                speaker_label VARCHAR(50) NOT NULL,
                project_name VARCHAR(255) NOT NULL,
                assigned_character_id INTEGER,
                assigned_character_slug VARCHAR(255),
                embedding_path TEXT,
                segment_count INTEGER DEFAULT 0,
                total_duration_seconds FLOAT DEFAULT 0,
                avg_confidence FLOAT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS voice_samples (
                id SERIAL PRIMARY KEY,
                speaker_id INTEGER REFERENCES voice_speakers(id),
                character_slug VARCHAR(255),
                project_name VARCHAR(255) NOT NULL,
                filename VARCHAR(500) NOT NULL,
                file_path TEXT NOT NULL,
                approval_status VARCHAR(50) DEFAULT 'pending',
                transcript TEXT,
                language VARCHAR(10),
                duration_seconds FLOAT,
                start_time FLOAT,
                end_time FLOAT,
                snr_db FLOAT,
                quality_score FLOAT,
                speaker_confidence FLOAT,
                feedback TEXT,
                rejection_categories TEXT[],
                created_at TIMESTAMP DEFAULT NOW(),
                reviewed_at TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS voice_training_jobs (
                id SERIAL PRIMARY KEY,
                job_id VARCHAR(255) UNIQUE NOT NULL,
                character_slug VARCHAR(255) NOT NULL,
                character_name VARCHAR(255),
                project_name VARCHAR(255),
                engine VARCHAR(50) NOT NULL,
                status VARCHAR(50) DEFAULT 'queued',
                approved_samples INTEGER DEFAULT 0,
                total_duration_seconds FLOAT DEFAULT 0,
                epochs INTEGER,
                model_path TEXT,
                log_path TEXT,
                pid INTEGER,
                error TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS voice_synthesis_jobs (
                id SERIAL PRIMARY KEY,
                job_id VARCHAR(255) UNIQUE NOT NULL,
                scene_id UUID,
                shot_id UUID,
                character_slug VARCHAR(255) NOT NULL,
                engine VARCHAR(50) NOT NULL,
                text TEXT NOT NULL,
                output_path TEXT,
                duration_seconds FLOAT,
                status VARCHAR(50) DEFAULT 'pending',
                error TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            )
        """)

        # Add voice_profile JSONB to characters table
        await conn.execute("""
            DO $$ BEGIN
                ALTER TABLE characters ADD COLUMN voice_profile JSONB;
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$
        """)

        # Voice pipeline indexes
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_voice_speakers_project ON voice_speakers(project_name)",
            "CREATE INDEX IF NOT EXISTS idx_voice_samples_character ON voice_samples(character_slug)",
            "CREATE INDEX IF NOT EXISTS idx_voice_samples_project ON voice_samples(project_name)",
            "CREATE INDEX IF NOT EXISTS idx_voice_samples_status ON voice_samples(approval_status)",
            "CREATE INDEX IF NOT EXISTS idx_voice_samples_speaker ON voice_samples(speaker_id)",
            "CREATE INDEX IF NOT EXISTS idx_voice_training_character ON voice_training_jobs(character_slug)",
            "CREATE INDEX IF NOT EXISTS idx_voice_training_status ON voice_training_jobs(status)",
            "CREATE INDEX IF NOT EXISTS idx_voice_synthesis_scene ON voice_synthesis_jobs(scene_id)",
            "CREATE INDEX IF NOT EXISTS idx_voice_synthesis_character ON voice_synthesis_jobs(character_slug)",
        ]:
            await conn.execute(idx_sql)

        # --- Style Switching History ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS style_history (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                style_name VARCHAR(255) NOT NULL,
                checkpoint_model VARCHAR(255),
                cfg_scale FLOAT,
                steps INTEGER,
                sampler VARCHAR(100),
                scheduler VARCHAR(100),
                width INTEGER,
                height INTEGER,
                positive_prompt_template TEXT,
                negative_prompt_template TEXT,
                switched_at TIMESTAMP DEFAULT NOW(),
                reason TEXT,
                generation_count INTEGER DEFAULT 0,
                avg_quality_at_switch FLOAT
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_style_history_project ON style_history(project_id)"
        )

        # Add checkpoint_model to rejections/approvals for per-checkpoint queries
        for tbl in ("rejections", "approvals"):
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE {tbl} ADD COLUMN checkpoint_model VARCHAR(255);
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # Model-aware generation: override columns on generation_styles
        for col, coltype in [
            ("model_architecture", "VARCHAR(50)"),
            ("prompt_format", "VARCHAR(50)"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE generation_styles ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # Indexes for Phase 1 tables
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_gen_history_character ON generation_history(character_slug)",
            "CREATE INDEX IF NOT EXISTS idx_gen_history_project ON generation_history(project_name)",
            "CREATE INDEX IF NOT EXISTS idx_gen_history_quality ON generation_history(quality_score)",
            "CREATE INDEX IF NOT EXISTS idx_gen_history_status ON generation_history(status)",
            "CREATE INDEX IF NOT EXISTS idx_gen_history_date ON generation_history(generated_at)",
            "CREATE INDEX IF NOT EXISTS idx_gen_history_checkpoint ON generation_history(checkpoint_model)",
            "CREATE INDEX IF NOT EXISTS idx_rejections_character ON rejections(character_slug)",
            "CREATE INDEX IF NOT EXISTS idx_rejections_date ON rejections(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_approvals_character ON approvals(character_slug)",
            "CREATE INDEX IF NOT EXISTS idx_approvals_date ON approvals(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_learned_character ON learned_patterns(character_slug)",
            "CREATE INDEX IF NOT EXISTS idx_learned_type ON learned_patterns(pattern_type)",
            "CREATE INDEX IF NOT EXISTS idx_autonomy_type ON autonomy_decisions(decision_type)",
            "CREATE INDEX IF NOT EXISTS idx_autonomy_date ON autonomy_decisions(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_autonomy_character ON autonomy_decisions(character_slug)",
        ]:
            await conn.execute(idx_sql)

        await conn.close()
        logger.info("Schema migrations completed successfully (incl. Phase 1 autonomy tables)")
    except Exception as e:
        logger.warning(f"Schema migration failed (non-fatal): {e}")


async def get_char_project_map() -> dict:
    """Load character→project mapping from DB with generation style info. Cached for 60s."""
    global _char_project_cache, _cache_time
    if _char_project_cache and (_time.time() - _cache_time) < 60:
        return _char_project_cache

    try:
        conn = await connect_direct()
        rows = await conn.fetch("""
            SELECT c.name,
                   REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') as slug,
                   c.design_prompt, c.appearance_data, p.name as project_name,
                   p.default_style,
                   gs.checkpoint_model, gs.cfg_scale, gs.steps,
                   gs.width, gs.height, gs.sampler, gs.scheduler,
                   gs.positive_prompt_template, gs.negative_prompt_template,
                   gs.model_architecture, gs.prompt_format,
                   ws.style_preamble
            FROM characters c
            JOIN projects p ON c.project_id = p.id
            LEFT JOIN generation_styles gs ON gs.style_name = p.default_style
            LEFT JOIN world_settings ws ON ws.project_id = p.id
        """)
        await conn.close()

        mapping = {}
        for row in rows:
            slug = row["slug"]
            if slug not in mapping or len(row["design_prompt"] or "") > len(mapping[slug].get("design_prompt") or ""):
                appearance_raw = row["appearance_data"]
                appearance = json.loads(appearance_raw) if isinstance(appearance_raw, str) else (appearance_raw or {})
                mapping[slug] = {
                    "name": row["name"],
                    "slug": slug,
                    "project_name": row["project_name"],
                    "design_prompt": row["design_prompt"],
                    "appearance_data": appearance,
                    "default_style": row["default_style"],
                    "checkpoint_model": row["checkpoint_model"],
                    "cfg_scale": float(row["cfg_scale"]) if row["cfg_scale"] else None,
                    "steps": row["steps"],
                    "sampler": row["sampler"],
                    "scheduler": row["scheduler"],
                    "width": row["width"],
                    "height": row["height"],
                    "resolution": f"{row['width']}x{row['height']}" if row["width"] else None,
                    "positive_prompt_template": row["positive_prompt_template"],
                    "negative_prompt_template": row["negative_prompt_template"],
                    "style_preamble": row["style_preamble"],
                    "model_architecture": row["model_architecture"],
                    "prompt_format": row["prompt_format"],
                }
        _char_project_cache = mapping
        _cache_time = _time.time()
    except Exception as e:
        logger.warning(f"Failed to load char→project map: {e}")

    return _char_project_cache


def invalidate_char_cache():
    """Invalidate the character→project cache so it reloads on next access."""
    global _char_project_cache, _cache_time
    _char_project_cache = {}
    _cache_time = 0
