"""NarrativeStateEngine — core logic for character state tracking and propagation."""

import json
import logging
from typing import Any

from packages.core.db import connect_direct
from .decay import apply_all_decay

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma3:12b"
OLLAMA_TIMEOUT = 120


class NarrativeStateEngine:
    """Manages character state across scenes."""

    async def get_state(self, scene_id: str, character_slug: str) -> dict | None:
        """Fetch a single character state for a scene."""
        conn = await connect_direct()
        try:
            row = await conn.fetchrow(
                "SELECT * FROM character_scene_state "
                "WHERE scene_id = $1 AND character_slug = $2",
                scene_id, character_slug,
            )
            return self._row_to_dict(row) if row else None
        finally:
            await conn.close()

    async def get_scene_states(self, scene_id: str) -> list[dict]:
        """Fetch all character states for a scene."""
        conn = await connect_direct()
        try:
            rows = await conn.fetch(
                "SELECT * FROM character_scene_state WHERE scene_id = $1 "
                "ORDER BY character_slug",
                scene_id,
            )
            return [self._row_to_dict(r) for r in rows]
        finally:
            await conn.close()

    async def set_state(
        self, scene_id: str, character_slug: str,
        state: dict, source: str = "auto",
    ) -> dict:
        """UPSERT a character state for a scene. Increments version on update."""
        conn = await connect_direct()
        try:
            row = await conn.fetchrow("""
                INSERT INTO character_scene_state
                    (scene_id, character_slug, clothing, hair_state, injuries,
                     accessories, body_state, emotional_state, energy_level,
                     relationship_context, location_in_scene, carrying,
                     state_source, version)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10::jsonb, $11, $12, $13, 1)
                ON CONFLICT (scene_id, character_slug) DO UPDATE SET
                    clothing = COALESCE(EXCLUDED.clothing, character_scene_state.clothing),
                    hair_state = COALESCE(EXCLUDED.hair_state, character_scene_state.hair_state),
                    injuries = COALESCE(EXCLUDED.injuries, character_scene_state.injuries),
                    accessories = COALESCE(EXCLUDED.accessories, character_scene_state.accessories),
                    body_state = COALESCE(EXCLUDED.body_state, character_scene_state.body_state),
                    emotional_state = COALESCE(EXCLUDED.emotional_state, character_scene_state.emotional_state),
                    energy_level = COALESCE(EXCLUDED.energy_level, character_scene_state.energy_level),
                    relationship_context = COALESCE(EXCLUDED.relationship_context, character_scene_state.relationship_context),
                    location_in_scene = COALESCE(EXCLUDED.location_in_scene, character_scene_state.location_in_scene),
                    carrying = COALESCE(EXCLUDED.carrying, character_scene_state.carrying),
                    state_source = EXCLUDED.state_source,
                    version = character_scene_state.version + 1,
                    updated_at = now()
                RETURNING *
            """,
                scene_id, character_slug,
                state.get("clothing"),
                state.get("hair_state"),
                json.dumps(state.get("injuries", [])),
                state.get("accessories", []),
                state.get("body_state", "clean"),
                state.get("emotional_state", "calm"),
                state.get("energy_level", "normal"),
                json.dumps(state.get("relationship_context", {})),
                state.get("location_in_scene"),
                state.get("carrying", []),
                source,
            )
            return self._row_to_dict(row)
        finally:
            await conn.close()

    async def delete_state(self, scene_id: str, character_slug: str) -> bool:
        """Remove a manual override, allowing re-propagation."""
        conn = await connect_direct()
        try:
            result = await conn.execute(
                "DELETE FROM character_scene_state "
                "WHERE scene_id = $1 AND character_slug = $2",
                scene_id, character_slug,
            )
            return result == "DELETE 1"
        finally:
            await conn.close()

    async def initialize_from_description(
        self, scene_id: str, project_id: int,
    ) -> list[dict]:
        """Use Ollama to parse scene description + characters into initial states."""
        conn = await connect_direct()
        try:
            scene = await conn.fetchrow(
                "SELECT description, location, mood, weather, time_of_day "
                "FROM scenes WHERE id = $1", scene_id,
            )
            if not scene or not scene["description"]:
                return []

            # Get characters in this scene's shots
            char_rows = await conn.fetch("""
                SELECT DISTINCT unnest(characters_present) as slug
                FROM shots WHERE scene_id = $1
            """, scene_id)
            if not char_rows:
                return []

            slugs = [r["slug"] for r in char_rows]

            # Get character details for context
            char_details = []
            for slug in slugs:
                crow = await conn.fetchrow(
                    "SELECT name, design_prompt, appearance_data FROM characters "
                    "WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), "
                    "'[^a-z0-9_-]', '', 'g') = $1",
                    slug,
                )
                if crow:
                    char_details.append({
                        "slug": slug,
                        "name": crow["name"],
                        "design_prompt": crow["design_prompt"],
                        "appearance_data": crow["appearance_data"],
                    })

            if not char_details:
                return []

            # Build Ollama prompt
            prompt = self._build_initialization_prompt(scene, char_details)
            parsed = await self._call_ollama(prompt)
            if not parsed:
                return []

            # Save states
            results = []
            for char_state in parsed:
                slug = char_state.pop("character_slug", None)
                if slug and slug in slugs:
                    saved = await self.set_state(
                        scene_id, slug, char_state, source="ai_initialized"
                    )
                    results.append(saved)

            return results
        finally:
            await conn.close()

    async def propagate_forward(
        self, from_scene_id: str, project_id: int,
    ) -> list[dict]:
        """Forward-propagate states from a scene to all downstream scenes.

        Respects manual overrides (state_source='manual') — never overwrites them.
        Applies decay rules between scenes.
        """
        conn = await connect_direct()
        try:
            # Get source scene states
            source_states = await conn.fetch(
                "SELECT * FROM character_scene_state WHERE scene_id = $1",
                from_scene_id,
            )
            if not source_states:
                return []

            # Get scene order for this project
            source_scene = await conn.fetchrow(
                "SELECT scene_number, project_id FROM scenes WHERE id = $1",
                from_scene_id,
            )
            if not source_scene:
                return []

            pid = source_scene["project_id"]
            source_num = source_scene["scene_number"]
            if source_num is None:
                return []

            # Get downstream scenes (higher scene_number)
            downstream = await conn.fetch(
                "SELECT id, scene_number FROM scenes "
                "WHERE project_id = $1 AND scene_number > $2 "
                "ORDER BY scene_number",
                pid, source_num,
            )
            if not downstream:
                return []

            propagated = []
            # Propagate each character separately
            for src_state in source_states:
                slug = src_state["character_slug"]
                current_state = self._row_to_dict(src_state)

                for ds_scene in downstream:
                    ds_id = ds_scene["id"]

                    # Check if target has a manual override
                    existing = await conn.fetchrow(
                        "SELECT state_source FROM character_scene_state "
                        "WHERE scene_id = $1 AND character_slug = $2",
                        ds_id, slug,
                    )
                    if existing and existing["state_source"] == "manual":
                        # Don't overwrite manual overrides, but use it as base
                        # for further downstream propagation
                        manual_row = await conn.fetchrow(
                            "SELECT * FROM character_scene_state "
                            "WHERE scene_id = $1 AND character_slug = $2",
                            ds_id, slug,
                        )
                        if manual_row:
                            current_state = self._row_to_dict(manual_row)
                        continue

                    # Apply decay
                    decayed = apply_all_decay(current_state)

                    # Save propagated state
                    saved = await self.set_state(
                        str(ds_id), slug, decayed, source="propagated"
                    )
                    propagated.append(saved)

                    # Use the decayed state as base for next scene
                    current_state = decayed

            return propagated
        finally:
            await conn.close()

    async def get_timeline(
        self, project_id: int, character_slug: str,
    ) -> list[dict]:
        """Get ordered state history for a character across all scenes in a project."""
        conn = await connect_direct()
        try:
            rows = await conn.fetch("""
                SELECT css.*, s.scene_number, s.title as scene_title
                FROM character_scene_state css
                JOIN scenes s ON css.scene_id = s.id
                WHERE s.project_id = $1 AND css.character_slug = $2
                ORDER BY s.scene_number
            """, project_id, character_slug)
            return [
                {**self._row_to_dict(r), "scene_number": r["scene_number"],
                 "scene_title": r["scene_title"]}
                for r in rows
            ]
        finally:
            await conn.close()

    def _row_to_dict(self, row) -> dict:
        """Convert an asyncpg Record to a clean dict."""
        d = dict(row)
        # Convert UUID to string
        if "scene_id" in d:
            d["scene_id"] = str(d["scene_id"])
        if "id" in d:
            d["id"] = d["id"]
        # Handle JSONB fields that might come as strings
        for field in ("injuries", "relationship_context"):
            if isinstance(d.get(field), str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        # Handle timestamps
        for ts_field in ("created_at", "updated_at"):
            if d.get(ts_field):
                d[ts_field] = d[ts_field].isoformat()
        return d

    def _build_initialization_prompt(
        self, scene: Any, char_details: list[dict],
    ) -> str:
        """Build the Ollama prompt for state initialization."""
        chars_block = "\n".join(
            f"- {c['name']} (slug: {c['slug']}): {c.get('design_prompt', 'no description')}"
            for c in char_details
        )

        scene_desc = scene["description"] or "No description"
        location = scene["location"] or "unknown"
        mood = scene["mood"] or "neutral"

        return f"""Analyze this anime scene and determine each character's physical state.

Scene: {scene_desc}
Location: {location}
Mood: {mood}

Characters present:
{chars_block}

For each character, output a JSON array with objects containing:
- character_slug: the slug identifier
- clothing: what they're wearing (be specific)
- hair_state: hair condition (e.g. "loose", "tied up", "wet", "messy")
- emotional_state: one of [calm, happy, content, sad, melancholy, angry, irritated, furious, scared, anxious, terrified, shocked, surprised, determined, focused, disgusted, uncomfortable, ecstatic, devastated]
- body_state: one of [clean, wet, damp, bloody, stained, dirty, dusty, sweaty]
- energy_level: one of [normal, tired, exhausted, energized, hyperactive]
- location_in_scene: where in the scene they are
- accessories: array of items they're wearing/holding that aren't clothing
- carrying: array of items they're carrying
- injuries: array of objects with "type", "severity" (severe/moderate/minor), "location"

Output ONLY the JSON array, no other text. Example:
[{{"character_slug": "rina", "clothing": "school uniform with white blouse", "hair_state": "loose", "emotional_state": "anxious", "body_state": "clean", "energy_level": "normal", "location_in_scene": "doorway", "accessories": [], "carrying": ["bag"], "injuries": []}}]"""

    async def _call_ollama(self, prompt: str) -> list[dict] | None:
        """Call Ollama and parse the JSON response."""
        import urllib.request
        try:
            payload = json.dumps({
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.3, "num_predict": 2048},
            }).encode()

            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)
            result = json.loads(resp.read())
            response_text = result.get("response", "")

            # Try to parse as JSON array
            parsed = json.loads(response_text)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                # Sometimes Ollama wraps in an object
                for key in ("characters", "states", "data", "results"):
                    if isinstance(parsed.get(key), list):
                        return parsed[key]
                # Single character response
                if "character_slug" in parsed:
                    return [parsed]
            return None
        except Exception as e:
            logger.warning(f"Ollama state initialization failed: {e}")
            return None


# Module-level singleton
narrative_engine = NarrativeStateEngine()
