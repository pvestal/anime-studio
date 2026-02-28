"""Database schema migrations — all ensure_* / CREATE TABLE / ALTER TABLE logic."""

import logging

from .db import connect_direct

logger = logging.getLogger(__name__)


async def run_migrations():
    """Run schema migrations at startup. Idempotent (uses IF NOT EXISTS)."""
    try:
        conn = await connect_direct()
        await conn.execute("SET search_path TO public")

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

        # Shot video review columns
        for col, coltype in [
            ("review_status", "VARCHAR(50) DEFAULT 'unreviewed'"),
            ("reviewed_at", "TIMESTAMP"),
            ("review_feedback", "TEXT"),
            ("qc_issues", "TEXT[]"),
            ("qc_category_averages", "JSONB"),
            ("qc_per_frame", "JSONB"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE shots ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # Shot LoRA columns (engine selector)
        for col, coltype in [
            ("lora_name", "VARCHAR(255)"),
            ("lora_strength", "REAL DEFAULT 0.8"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE shots ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # Reference V2V: source video clip columns on shots
        for col, coltype in [
            ("source_video_path", "TEXT"),
            ("source_video_auto_assigned", "BOOLEAN DEFAULT FALSE"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE shots ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
            """)

        # Character clips table (persists CLIP-extracted video clips per character)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS character_clips (
                id SERIAL PRIMARY KEY,
                character_slug VARCHAR(255) NOT NULL,
                clip_path TEXT NOT NULL UNIQUE,
                source_video TEXT,
                timestamp_seconds FLOAT,
                similarity FLOAT,
                duration_seconds FLOAT DEFAULT 2.0,
                frame_index INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_character_clips_slug ON character_clips(character_slug)",
            "CREATE INDEX IF NOT EXISTS idx_character_clips_similarity ON character_clips(character_slug, similarity DESC NULLS LAST)",
        ]:
            await conn.execute(idx_sql)

        # Scene generated music columns (ACE-Step pipeline)
        for col, coltype in [
            ("generated_music_path", "TEXT"),
            ("generated_music_task_id", "VARCHAR(255)"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE scenes ADD COLUMN {col} {coltype};
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

        # Episode music columns
        for col, coltype in [
            ("episode_music_path", "TEXT"),
            ("episode_mood", "TEXT"),
        ]:
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE episodes ADD COLUMN {col} {coltype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$
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

        # --- Engine Blacklist (video review) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS engine_blacklist (
                id SERIAL PRIMARY KEY,
                character_slug VARCHAR(255) NOT NULL,
                project_id INTEGER REFERENCES projects(id),
                video_engine VARCHAR(50) NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(character_slug, project_id, video_engine)
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_engine_blacklist_char ON engine_blacklist(character_slug, project_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_shots_review_status ON shots(review_status)"
        )

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
            ("video_engine", "VARCHAR(50)"),
            ("negative_prompt", "TEXT"),
            ("seed", "BIGINT"),
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

        # --- Production Pipeline (Orchestrator) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS production_pipeline (
                id SERIAL PRIMARY KEY,
                entity_type VARCHAR(30) NOT NULL,
                entity_id VARCHAR(255) NOT NULL,
                project_id INTEGER NOT NULL,
                phase VARCHAR(50) NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'pending',
                progress_current INTEGER DEFAULT 0,
                progress_target INTEGER DEFAULT 0,
                progress_detail JSONB DEFAULT '{}',
                gate_check_result JSONB,
                blocked_reason TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                last_checked_at TIMESTAMP DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(entity_type, entity_id, phase)
            )
        """)
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_pipeline_project ON production_pipeline(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_pipeline_status ON production_pipeline(status)",
            "CREATE INDEX IF NOT EXISTS idx_pipeline_entity ON production_pipeline(entity_type, entity_id)",
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

        # --- Model Audit Log ---
        # Tracks every checkpoint change, download, removal, and config update
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS model_audit_log (
                id SERIAL PRIMARY KEY,
                action VARCHAR(50) NOT NULL,
                checkpoint_model VARCHAR(255),
                previous_model VARCHAR(255),
                project_name VARCHAR(255),
                style_name VARCHAR(100),
                reason TEXT,
                changed_by VARCHAR(100) DEFAULT 'system',
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_model_audit_date ON model_audit_log(created_at)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_model_audit_checkpoint ON model_audit_log(checkpoint_model)"
        )

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

        # --- Narrative State Machine (NSM) ---

        # Character state per scene
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS character_scene_state (
                id SERIAL PRIMARY KEY,
                scene_id UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
                character_slug VARCHAR(255) NOT NULL,
                clothing TEXT,
                hair_state TEXT,
                injuries JSONB DEFAULT '[]',
                accessories TEXT[] DEFAULT '{}',
                body_state TEXT DEFAULT 'clean',
                emotional_state TEXT DEFAULT 'calm',
                energy_level TEXT DEFAULT 'normal',
                relationship_context JSONB DEFAULT '{}',
                location_in_scene TEXT,
                carrying TEXT[] DEFAULT '{}',
                state_source VARCHAR(50) NOT NULL DEFAULT 'auto',
                version INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE(scene_id, character_slug)
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_css_scene ON character_scene_state(scene_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_css_char ON character_scene_state(character_slug)"
        )

        # Image visual tags (Phase 1b)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS image_visual_tags (
                id SERIAL PRIMARY KEY,
                character_slug VARCHAR(255) NOT NULL,
                project_name VARCHAR(255),
                image_name VARCHAR(500) NOT NULL,
                clothing TEXT,
                hair_state TEXT,
                expression TEXT,
                body_state TEXT,
                pose TEXT,
                accessories TEXT[],
                setting TEXT,
                quality_score FLOAT,
                nsfw_level INTEGER DEFAULT 0,
                face_visible BOOLEAN,
                full_body BOOLEAN,
                tagged_by VARCHAR(50) DEFAULT 'vision_llm',
                confidence FLOAT DEFAULT 1.0,
                created_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE(character_slug, image_name)
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ivt_char ON image_visual_tags(character_slug)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ivt_project ON image_visual_tags(project_name)"
        )

        # Scene dependencies (Phase 2)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS scene_dependencies (
                id SERIAL PRIMARY KEY,
                source_scene_id UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
                target_scene_id UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
                dependency_type VARCHAR(50) NOT NULL,
                character_slug VARCHAR(255) DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE(source_scene_id, target_scene_id, dependency_type, character_slug)
            )
        """)

        # Regeneration queue (Phase 2)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS regeneration_queue (
                id SERIAL PRIMARY KEY,
                scene_id UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
                shot_id UUID REFERENCES shots(id) ON DELETE CASCADE,
                reason TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 5,
                source_scene_id UUID,
                source_field TEXT,
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT now(),
                processed_at TIMESTAMPTZ
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_regen_queue_status ON regeneration_queue(status)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_regen_queue_scene ON regeneration_queue(scene_id)"
        )

        await conn.close()
        logger.info("Schema migrations completed successfully (incl. Phase 1 autonomy + NSM tables)")
    except Exception as e:
        logger.warning(f"Schema migration failed (non-fatal): {e}")
