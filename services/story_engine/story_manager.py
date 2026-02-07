"""
Story Bible Manager
All reads and writes to story data go through here.
Every mutation is logged to story_changelog and triggers change propagation.
"""

import json
import logging
from typing import Optional
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor

from .models import (
    ChangeEvent,
    CharacterCreate,
    DialogueLine,
    EpisodeCreate,
    PropagationScope,
    SceneCreate,
    StoryArcCreate,
)
from .vector_store import StoryVectorStore

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": "localhost",
    "database": "anime_production",
    "user": "patrick",
    "password": "RP78eIrW7cI2jYvL5akt1yurE",
}


class StoryManager:
    """
    Central manager for all story bible operations.
    Every write logs a changelog entry and updates vectors.
    """

    def __init__(self):
        self.vector_store = StoryVectorStore()

    def _get_conn(self):
        return psycopg2.connect(**DB_CONFIG)

    def _log_change(self, cursor, event: ChangeEvent, affected_scenes: list[str] = None, scope: str = "all"):
        """Log a change to story_changelog and return the changelog ID."""
        # Convert scene UUIDs to array format for PostgreSQL
        if affected_scenes:
            scene_array_str = ','.join([f"'{s}'::uuid" for s in affected_scenes])
            scene_array = f"ARRAY[{scene_array_str}]::uuid[]"
        else:
            scene_array = "NULL"

        cursor.execute(f"""
            INSERT INTO story_changelog
                (project_id, table_name, record_id, field_changed, old_value, new_value,
                 change_type, propagation_scope, affected_scenes, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, {scene_array}, %s)
            RETURNING id
        """, (
            event.project_id, event.table_name, event.record_id,
            event.field_changed, event.old_value, event.new_value,
            event.change_type, scope, event.created_by,
        ))
        result = cursor.fetchone()
        if isinstance(result, dict):
            return result["id"]
        else:
            return result[0]

    # ── Characters ────────────────────────────────────────────

    def create_character(self, data: CharacterCreate) -> dict:
        """Create a character and index it in Qdrant."""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO characters
                        (project_id, name, description, visual_prompt_template,
                         voice_profile, personality_tags, character_role, relationships)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                """, (
                    data.project_id, data.name, data.description,
                    data.visual_prompt_template,
                    json.dumps(data.voice_profile.model_dump()),
                    data.personality_tags, data.character_role,
                    json.dumps(data.relationships),
                ))
                character = dict(cur.fetchone())

                self._log_change(cur, ChangeEvent(
                    project_id=data.project_id,
                    table_name="characters",
                    record_id=character["id"],
                    change_type="insert",
                    created_by="story_manager",
                ))
                conn.commit()

        # Index in Qdrant
        embed_text = f"{data.name}: {data.description or ''} Personality: {', '.join(data.personality_tags)}"
        self.vector_store.upsert_story_content(
            content_id=f"character:{character['id']}",
            text=embed_text,
            metadata={
                "project_id": data.project_id,
                "content_type": "character",
                "character_id": character["id"],
                "character_name": data.name,
            },
        )

        return character

    def get_character(self, character_id: int) -> Optional[dict]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM characters WHERE id = %s", (character_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def get_characters_for_project(self, project_id: int) -> list[dict]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM characters WHERE project_id = %s ORDER BY name",
                    (project_id,),
                )
                return [dict(r) for r in cur.fetchall()]

    def update_character(self, character_id: int, updates: dict) -> dict:
        """
        Update character fields. Logs change and determines propagation scope.
        Visual changes → regenerate visuals for scenes with this character.
        Personality changes → regenerate dialogue.
        Voice changes → regenerate audio.
        """
        character = self.get_character(character_id)
        if not character:
            raise ValueError(f"Character {character_id} not found")

        # Determine propagation scope per field
        visual_fields = {"visual_prompt_template", "description"}
        writing_fields = {"personality_tags", "relationships", "description"}
        audio_fields = {"voice_profile"}

        scopes = set()
        for field in updates:
            if field in visual_fields:
                scopes.add("visual")
            if field in writing_fields:
                scopes.add("writing")
            if field in audio_fields:
                scopes.add("audio")

        scope = "all" if len(scopes) > 1 else (scopes.pop() if scopes else "all")

        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Find affected scenes
                cur.execute(
                    "SELECT id FROM scenes WHERE %s = ANY(characters_present)",
                    (character_id,),
                )
                affected_scene_ids = [str(r["id"]) for r in cur.fetchall()]

                # Build dynamic UPDATE
                set_clauses = []
                values = []
                for key, value in updates.items():
                    set_clauses.append(f"{key} = %s")
                    # Handle arrays for PostgreSQL text[] or other array columns
                    if key in ["personality_tags"] and isinstance(value, list):
                        values.append(value)  # psycopg2 handles Python lists -> PostgreSQL arrays
                    elif isinstance(value, (dict, list)):
                        values.append(json.dumps(value))
                    else:
                        values.append(value)

                if set_clauses:
                    set_clauses.append("updated_at = NOW()")
                    values.append(character_id)
                    cur.execute(
                        f"UPDATE characters SET {', '.join(set_clauses)} WHERE id = %s RETURNING *",
                        values,
                    )
                    updated = dict(cur.fetchone())

                    # Log each changed field
                    for field, new_val in updates.items():
                        old_val = character.get(field)
                        self._log_change(cur, ChangeEvent(
                            project_id=character["project_id"],
                            table_name="characters",
                            record_id=character_id,
                            field_changed=field,
                            old_value=str(old_val) if old_val else None,
                            new_value=str(new_val),
                            change_type="update",
                            created_by="story_manager",
                        ), affected_scenes=affected_scene_ids, scope=scope)

                    conn.commit()

                    # Re-index in Qdrant
                    embed_text = f"{updated['name']}: {updated.get('description','')} Personality: {', '.join(updated.get('personality_tags',[]))}"
                    self.vector_store.upsert_story_content(
                        content_id=f"character:{character_id}",
                        text=embed_text,
                        metadata={
                            "project_id": character["project_id"],
                            "content_type": "character",
                            "character_id": character_id,
                            "character_name": updated["name"],
                        },
                    )

                    return updated
        return character

    # ── Episodes ──────────────────────────────────────────────

    def create_episode(self, data: EpisodeCreate) -> dict:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                episode_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO episodes
                        (id, project_id, episode_number, title, synopsis, tone_profile, status)
                    VALUES (%s::uuid, %s, %s, %s, %s, %s, 'outline')
                    RETURNING *
                """, (
                    episode_id, data.project_id, data.episode_number, data.title,
                    data.synopsis, json.dumps(data.tone_profile),
                ))
                episode = dict(cur.fetchone())
                self._log_change(cur, ChangeEvent(
                    project_id=data.project_id,
                    table_name="episodes",
                    record_id=int(episode["episode_number"]),  # Use episode number as record_id for changelog
                    change_type="insert",
                    created_by="story_manager",
                ))
                conn.commit()

        # Index synopsis in Qdrant
        if data.synopsis:
            self.vector_store.upsert_story_content(
                content_id=f"episode:{episode['id']}",
                text=f"Episode {data.episode_number}: {data.title}. {data.synopsis}",
                metadata={
                    "project_id": data.project_id,
                    "content_type": "episode",
                    "episode_id": episode["id"],
                    "episode_number": data.episode_number,
                },
            )

        return episode

    # ── Scenes ────────────────────────────────────────────────

    def create_scene(self, data: SceneCreate) -> dict:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get project_id from episode
                cur.execute("SELECT project_id FROM episodes WHERE id = %s::uuid", (data.episode_id,))
                ep_row = cur.fetchone()
                if not ep_row:
                    raise ValueError(f"Episode {data.episode_id} not found")
                project_id = ep_row["project_id"]

                scene_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO scenes
                        (id, episode_id, scene_number, narrative_text, setting_description,
                         emotional_tone, characters_present, dialogue, narration,
                         camera_directions, audio_mood, generation_status)
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft')
                    RETURNING *
                """, (
                    scene_id, data.episode_id, data.sequence_order, data.narrative_text,
                    data.setting_description, data.emotional_tone,
                    data.characters_present,
                    json.dumps([d.model_dump() for d in data.dialogue]),
                    data.narration, data.camera_directions, data.audio_mood,
                ))
                scene = dict(cur.fetchone())

                self._log_change(cur, ChangeEvent(
                    project_id=project_id,
                    table_name="scenes",
                    record_id=data.sequence_order,  # Use scene_number for changelog record_id
                    change_type="insert",
                    created_by="story_manager",
                ))
                conn.commit()

        # Index in Qdrant
        self.vector_store.upsert_story_content(
            content_id=f"scene:{scene['id']}",
            text=f"{data.narrative_text} Setting: {data.setting_description} Tone: {data.emotional_tone}",
            metadata={
                "project_id": project_id,
                "content_type": "scene",
                "scene_id": scene["id"],
                "episode_id": data.episode_id,
                "emotional_tone": data.emotional_tone,
            },
        )

        # Also index each dialogue line for contradiction detection
        for dl in data.dialogue:
            self.vector_store.upsert_story_content(
                content_id=f"dialogue:{scene['id']}:{dl.character_id}:{dl.timing_offset}",
                text=dl.line,
                metadata={
                    "project_id": project_id,
                    "content_type": "dialogue",
                    "scene_id": scene["id"],
                    "character_id": dl.character_id,
                    "emotion": dl.emotion,
                },
            )

        return scene

    def update_scene_status(self, scene_id: str, status: str):
        """Update generation status of a scene."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE scenes SET generation_status = %s WHERE id = %s::uuid",
                    (status, scene_id),
                )
                conn.commit()

    def get_scene_with_context(self, scene_id: str) -> dict:
        """
        Get a scene with ALL context needed for generation:
        - Scene data
        - Character details for all characters_present
        - Episode info
        - Project production profile
        - World rules
        - Active story arcs touching this scene
        """
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Scene
                cur.execute("SELECT * FROM scenes WHERE id = %s::uuid", (scene_id,))
                scene = cur.fetchone()
                if not scene:
                    return None
                scene = dict(scene)

                # Episode
                cur.execute("SELECT * FROM episodes WHERE id = %s::uuid", (str(scene["episode_id"]),))
                episode = dict(cur.fetchone())

                project_id = episode["project_id"]

                # Characters
                characters = []
                if scene.get("characters_present"):
                    cur.execute(
                        "SELECT * FROM characters WHERE id = ANY(%s)",
                        (scene["characters_present"],),
                    )
                    characters = [dict(r) for r in cur.fetchall()]

                # Production profiles
                profiles = {}
                cur.execute(
                    "SELECT profile_type, settings FROM production_profiles WHERE project_id = %s AND is_active = TRUE",
                    (project_id,),
                )
                for row in cur.fetchall():
                    profiles[row["profile_type"]] = row["settings"]

                # World rules
                cur.execute(
                    "SELECT rule_category, rule_key, rule_value FROM world_rules WHERE project_id = %s ORDER BY priority DESC",
                    (project_id,),
                )
                world_rules = {}
                for row in cur.fetchall():
                    cat = row["rule_category"]
                    if cat not in world_rules:
                        world_rules[cat] = {}
                    world_rules[cat][row["rule_key"]] = row["rule_value"]

                # Story arcs touching this scene
                cur.execute("""
                    SELECT sa.*, acs.relevance
                    FROM story_arcs sa
                    JOIN arc_scenes acs ON sa.id = acs.arc_id
                    WHERE acs.scene_id = %s::uuid AND sa.status = 'active'
                """, (scene_id,))
                arcs = [dict(r) for r in cur.fetchall()]

                return {
                    "scene": scene,
                    "episode": episode,
                    "project_id": project_id,
                    "characters": characters,
                    "production_profiles": profiles,
                    "world_rules": world_rules,
                    "active_arcs": arcs,
                }

    # ── Story Arcs ────────────────────────────────────────────

    def create_story_arc(self, data: StoryArcCreate) -> dict:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO story_arcs
                        (project_id, name, description, arc_type, themes,
                         tension_start, tension_peak, resolution_style)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                """, (
                    data.project_id, data.name, data.description,
                    data.arc_type, data.themes,
                    data.tension_start, data.tension_peak, data.resolution_style,
                ))
                arc = dict(cur.fetchone())
                conn.commit()

        self.vector_store.upsert_story_content(
            content_id=f"arc:{arc['id']}",
            text=f"Story Arc: {data.name}. {data.description or ''} Themes: {', '.join(data.themes)}",
            metadata={
                "project_id": data.project_id,
                "content_type": "arc",
                "arc_id": arc["id"],
            },
        )
        return arc

    def link_arc_to_scene(self, arc_id: int, scene_id: str, relevance: float = 1.0):
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO arc_scenes (arc_id, scene_id, relevance)
                    VALUES (%s, %s::uuid, %s)
                    ON CONFLICT (arc_id, scene_id) DO UPDATE SET relevance = EXCLUDED.relevance
                """, (arc_id, scene_id, relevance))
                conn.commit()

    def link_arc_to_episode(self, arc_id: int, episode_id: str, arc_phase: str = "rising", tension: float = 0.5):
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO arc_episodes (arc_id, episode_id, arc_phase, tension_level)
                    VALUES (%s, %s::uuid, %s, %s)
                    ON CONFLICT (arc_id, episode_id) DO UPDATE SET arc_phase = EXCLUDED.arc_phase, tension_level = EXCLUDED.tension_level
                """, (arc_id, episode_id, arc_phase, tension))
                conn.commit()

    # ── Production Profiles ───────────────────────────────────

    def set_production_profile(self, project_id: int, profile_type: str, settings: dict):
        """Set or update a production profile for a project."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO production_profiles (project_id, profile_type, settings)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (project_id, profile_type)
                    DO UPDATE SET settings = EXCLUDED.settings, updated_at = NOW()
                """, (project_id, profile_type, json.dumps(settings)))
                conn.commit()

    # ── World Rules ───────────────────────────────────────────

    def set_world_rule(self, project_id: int, category: str, key: str, value: str, priority: int = 50):
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO world_rules (project_id, rule_category, rule_key, rule_value, priority)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (project_id, rule_category, rule_key)
                    DO UPDATE SET rule_value = EXCLUDED.rule_value, priority = EXCLUDED.priority
                """, (project_id, category, key, value, priority))
                conn.commit()

    # ── Reality Feed ──────────────────────────────────────────

    def log_reality_event(self, source: str, event_type: str, content: str,
                          project_id: int = None, tags: list[str] = None):
        """Log a real-world event that could become story material."""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO reality_feed (project_id, source, event_type, raw_content, tags)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING *
                """, (project_id, source, event_type, content, tags))
                event = dict(cur.fetchone())
                conn.commit()
        return event

    def get_unrated_reality_events(self, limit: int = 20) -> list[dict]:
        """Get reality feed events that haven't been rated for story potential."""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM reality_feed
                    WHERE comedic_potential IS NULL AND dramatic_potential IS NULL
                    ORDER BY created_at DESC LIMIT %s
                """, (limit,))
                return [dict(r) for r in cur.fetchall()]