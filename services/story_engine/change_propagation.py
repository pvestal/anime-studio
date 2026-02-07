"""
Change Propagation Engine
Watches story_changelog for pending changes, determines affected scenes,
and queues regeneration jobs with the correct scope.

This is the system that makes "change the character design, only affected
scenes regenerate their visuals" work.
"""

import logging
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": "localhost",
    "database": "anime_production",
    "user": "patrick",
    "password": "RP78eIrW7cI2jYvL5akt1yurE",
}


class ChangePropagator:
    """
    Processes pending changelog entries and queues scene regeneration jobs.

    The key insight: we never regenerate everything. The dependency graph
    tells us exactly what's stale.

    Dependency Rules:
        character.visual_prompt_template changed → visual regen for scenes with that character
        character.personality_tags changed       → writing regen for scenes with that character
        character.voice_profile changed          → audio regen for scenes with that character
        character.description changed            → visual + writing regen
        story_arc changed                        → writing regen for all linked scenes
        episode.tone_profile changed             → writing regen for all scenes in episode
        scene.narrative_text changed             → writing + visual regen for that scene
        scene.dialogue changed                   → audio + caption regen for that scene
        production_profile changed               → scope-specific regen for ALL scenes in project
        world_rule changed                       → depends on category
    """

    def _get_conn(self):
        return psycopg2.connect(**DB_CONFIG)

    def process_pending_changes(self, limit: int = 50) -> list[dict]:
        """
        Process pending changelog entries.
        Returns list of queued jobs.
        """
        queued = []

        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get pending changes with row-level locking
                cur.execute("""
                    SELECT * FROM story_changelog
                    WHERE propagation_status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                """, (limit,))
                changes = cur.fetchall()

                for change in changes:
                    change = dict(change)
                    affected_scenes = change.get("affected_scenes") or []
                    scope = change.get("propagation_scope", "all")

                    # If affected_scenes wasn't pre-computed, compute now
                    if not affected_scenes:
                        affected_scenes = self._compute_affected_scenes(
                            cur, change["table_name"], change["record_id"], change.get("field_changed")
                        )

                    # Queue regeneration jobs for each affected scene
                    for scene_id in affected_scenes:
                        # Check if job already exists to avoid duplicates
                        cur.execute("""
                            SELECT id FROM scene_generation_queue
                            WHERE scene_id = %s::uuid AND generation_scope = %s AND status = 'queued'
                        """, (str(scene_id), scope))

                        if not cur.fetchone():
                            cur.execute("""
                                INSERT INTO scene_generation_queue
                                    (scene_id, generation_scope, priority, status, triggered_by)
                                VALUES (%s::uuid, %s, %s, 'queued', %s)
                                RETURNING id
                            """, (str(scene_id), scope, 50, change["id"]))
                            job_id = cur.fetchone()["id"]
                            queued.append({
                                "job_id": job_id,
                                "scene_id": str(scene_id),
                                "scope": scope,
                                "triggered_by_change": change["id"]
                            })

                    # Mark change as processed
                    if affected_scenes:
                        # Convert UUIDs to PostgreSQL array format
                        scene_array_str = ','.join([f"'{s}'::uuid" for s in affected_scenes])
                        cur.execute(f"""
                            UPDATE story_changelog
                            SET propagation_status = 'complete',
                                affected_scenes = ARRAY[{scene_array_str}]::uuid[]
                            WHERE id = %s
                        """, (change["id"],))
                    else:
                        cur.execute("""
                            UPDATE story_changelog
                            SET propagation_status = 'complete'
                            WHERE id = %s
                        """, (change["id"],))

                conn.commit()

        if queued:
            logger.info(f"Propagated {len(changes)} changes → {len(queued)} regeneration jobs")
        return queued

    def _compute_affected_scenes(self, cursor, table_name: str, record_id: int, field: Optional[str]) -> list[str]:
        """Compute which scenes are affected by a change based on the dependency graph."""

        if table_name == "characters":
            # Find all scenes where this character appears
            # characters_present is INTEGER[]
            cursor.execute(
                "SELECT id FROM scenes WHERE %s = ANY(characters_present)",
                (record_id,),
            )
            return [str(r["id"]) for r in cursor.fetchall()]

        elif table_name == "story_arcs":
            # Find scenes linked to this arc
            cursor.execute(
                "SELECT scene_id FROM arc_scenes WHERE arc_id = %s",
                (record_id,),
            )
            return [str(r["scene_id"]) for r in cursor.fetchall()]

        elif table_name == "episodes":
            # Find all scenes in this episode
            # episodes.id is UUID, need to handle carefully
            cursor.execute(
                "SELECT id FROM scenes WHERE episode_id = (SELECT id FROM episodes WHERE CAST(id AS TEXT) = %s OR id::text = %s LIMIT 1)",
                (str(record_id), str(record_id)),
            )
            return [str(r["id"]) for r in cursor.fetchall()]

        elif table_name == "scenes":
            # The scene itself is affected
            # Need to get the UUID for this scene
            cursor.execute(
                "SELECT id FROM scenes WHERE id::text = %s OR CAST(id AS TEXT) = %s LIMIT 1",
                (str(record_id), str(record_id)),
            )
            result = cursor.fetchone()
            return [str(result["id"])] if result else []

        elif table_name == "production_profiles":
            # Affects all scenes in the project
            cursor.execute("""
                SELECT s.id FROM scenes s
                JOIN episodes e ON s.episode_id = e.id
                JOIN production_profiles pp ON e.project_id = pp.project_id
                WHERE pp.id = %s
            """, (record_id,))
            return [str(r["id"]) for r in cursor.fetchall()]

        elif table_name == "world_rules":
            # Get project and find all its scenes
            cursor.execute(
                "SELECT project_id FROM world_rules WHERE id = %s",
                (record_id,)
            )
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                    SELECT s.id FROM scenes s
                    JOIN episodes e ON s.episode_id = e.id
                    WHERE e.project_id = %s
                """, (row["project_id"],))
                return [str(r["id"]) for r in cursor.fetchall()]

        return []

    def get_queue_status(self) -> dict:
        """Get current state of the generation queue."""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT status, generation_scope, COUNT(*) as count
                    FROM scene_generation_queue
                    GROUP BY status, generation_scope
                    ORDER BY status, generation_scope
                """)
                rows = [dict(r) for r in cur.fetchall()]

                cur.execute("""
                    SELECT COUNT(*) as pending FROM story_changelog
                    WHERE propagation_status = 'pending'
                """)
                pending_changes = cur.fetchone()["pending"]

                return {
                    "queue": rows,
                    "pending_changelog_entries": pending_changes,
                }

    def get_stale_scenes(self, project_id: int) -> list[dict]:
        """Get scenes that have queued regeneration jobs (i.e., are stale)."""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT DISTINCT s.id, s.scene_number as sequence_order, s.emotional_tone,
                           s.generation_status, sgq.generation_scope, sgq.status as queue_status
                    FROM scenes s
                    JOIN scene_generation_queue sgq ON s.id = sgq.scene_id
                    JOIN episodes e ON s.episode_id = e.id
                    WHERE e.project_id = %s AND sgq.status = 'queued'
                    ORDER BY s.scene_number
                """, (project_id,))
                return [dict(r) for r in cur.fetchall()]