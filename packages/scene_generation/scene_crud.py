"""Scene & Shot CRUD endpoints — list, create, get, update, delete.

Split from router.py for readability.
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from packages.core.config import BASE_PATH, COMFYUI_OUTPUT_DIR
from packages.core.db import connect_direct, get_char_project_map
from packages.core.events import event_bus, SCENE_UPDATED, SHOT_UPDATED
from packages.core.models import (
    SceneCreateRequest, ShotCreateRequest, ShotUpdateRequest,
    SceneUpdateRequest, SceneAudioRequest,
)
from pydantic import BaseModel
from .builder import (
    SCENE_OUTPUT_DIR, _scene_generation_tasks,
    extract_last_frame, concat_videos, copy_to_comfyui_input,
    poll_comfyui_completion, generate_scene, apply_scene_audio,
)
from .framepack import (
    build_framepack_workflow, _submit_comfyui_workflow,
    MOTION_PRESETS,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Concurrency guard: only one scene generation at a time (GPU constraint)
_scene_gen_semaphore = asyncio.Semaphore(1)


@router.get("/scenes")
async def list_scenes(project_id: int):
    """List scenes for a project."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT id, project_id, title, description, location, time_of_day,
                   weather, mood, generation_status, target_duration_seconds,
                   actual_duration_seconds, total_shots, completed_shots,
                   final_video_path, created_at,
                   audio_track_id, audio_track_name, audio_track_artist,
                   audio_preview_url, audio_fade_in, audio_fade_out, audio_start_offset,
                   audio_auto_duck, audio_generation_mode, audio_source_playlist_id
            FROM scenes WHERE project_id = $1
            ORDER BY scene_number NULLS LAST, created_at
        """, project_id)
        scenes = []
        for r in rows:
            shot_count = await conn.fetchval(
                "SELECT COUNT(*) FROM shots WHERE scene_id = $1", r["id"])
            scene_data = {
                "id": str(r["id"]), "project_id": r["project_id"],
                "title": r["title"], "description": r["description"],
                "location": r["location"], "time_of_day": r["time_of_day"],
                "weather": r["weather"], "mood": r["mood"],
                "generation_status": r["generation_status"] or "draft",
                "target_duration_seconds": r["target_duration_seconds"],
                "actual_duration_seconds": r["actual_duration_seconds"],
                "total_shots": shot_count,
                "completed_shots": r["completed_shots"] or 0,
                "final_video_path": r["final_video_path"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            if r["audio_track_id"]:
                scene_data["audio"] = {
                    "track_id": r["audio_track_id"],
                    "track_name": r["audio_track_name"],
                    "track_artist": r["audio_track_artist"],
                    "preview_url": r["audio_preview_url"],
                    "fade_in": r["audio_fade_in"],
                    "fade_out": r["audio_fade_out"],
                    "start_offset": r["audio_start_offset"],
                    "auto_duck": r["audio_auto_duck"] or False,
                    "generation_mode": r["audio_generation_mode"],
                    "source_playlist_id": r["audio_source_playlist_id"],
                }
            scenes.append(scene_data)
        return {"scenes": scenes}
    finally:
        await conn.close()


@router.post("/scenes")
async def create_scene(body: SceneCreateRequest):
    """Create a new scene."""
    conn = await connect_direct()
    try:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", body.project_id)
            max_num = await conn.fetchval(
                "SELECT COALESCE(MAX(scene_number), 0) FROM scenes WHERE project_id = $1",
                body.project_id)
            scene_num = (max_num or 0) + 1
            row = await conn.fetchrow("""
                INSERT INTO scenes (project_id, title, description, location, time_of_day,
                                    weather, mood, target_duration_seconds, scene_number, generation_status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'draft')
                RETURNING id, created_at
            """, body.project_id, body.title, body.description, body.location,
                body.time_of_day, body.weather, body.mood, body.target_duration_seconds,
                scene_num)
        return {
            "id": str(row["id"]), "scene_number": scene_num,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
    finally:
        await conn.close()


@router.post("/scenes/generate-from-story")
async def generate_scenes_from_story_endpoint(project_id: int, episode_id: str | None = None):
    """Auto-generate scene breakdowns from project storyline using AI.

    Persists generated scenes AND their shots to the database.
    If episode_id is provided, generates scenes for that specific episode and
    links them via episode_scenes junction table.
    """
    from .story_to_scenes import generate_scenes_from_story
    try:
        scenes = await generate_scenes_from_story(project_id, episode_id=episode_id)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"AI returned invalid JSON: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Story-to-scenes generation failed: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}" or "Unknown error")

    # Persist scenes + shots to DB
    saved = await _persist_scenes_and_shots(project_id, scenes, episode_id=episode_id)
    return {"project_id": project_id, "scenes": saved, "count": len(saved)}


def _name_to_slug(name: str) -> str:
    """Convert character name to slug: 'Bowser Jr.' → 'bowser_jr'."""
    import re
    return re.sub(r'[^a-z0-9_-]', '', name.lower().replace(' ', '_'))


async def _persist_scenes_and_shots(
    project_id: int, scenes: list[dict], episode_id: str | None = None,
) -> list[dict]:
    """Insert AI-generated scenes and their suggested_shots into the DB.

    Uses advisory lock for atomic scene numbering.
    If episode_id is provided, links scenes to episode via episode_scenes table.

    Returns list of saved scenes with their DB ids and shot ids.
    """
    conn = await connect_direct()
    try:
        # Build character name→slug map for dialogue assignment
        chars = await conn.fetch(
            "SELECT name FROM characters WHERE project_id = $1", project_id)
        char_slug_map = {c["name"].lower(): _name_to_slug(c["name"]) for c in chars}

        ep_uuid = None
        if episode_id:
            ep_uuid = uuid.UUID(episode_id)

        saved = []
        async with conn.transaction():
            # Lock to prevent concurrent calls from getting the same scene_number
            await conn.execute("SELECT pg_advisory_xact_lock($1)", project_id)

            max_num = await conn.fetchval(
                "SELECT COALESCE(MAX(scene_number), 0) FROM scenes WHERE project_id = $1",
                project_id)

            # Get max position in episode if linking
            max_pos = 0
            if ep_uuid:
                max_pos = await conn.fetchval(
                    "SELECT COALESCE(MAX(position), 0) FROM episode_scenes WHERE episode_id = $1",
                    ep_uuid) or 0

            for i, scene in enumerate(scenes):
                scene_num = (max_num or 0) + i + 1
                row = await conn.fetchrow("""
                    INSERT INTO scenes (project_id, title, description, location,
                                        time_of_day, mood, target_duration_seconds,
                                        scene_number, generation_status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'draft')
                    RETURNING id
                """, project_id, scene.get("title"), scene.get("description"),
                    scene.get("location"), scene.get("time_of_day"),
                    scene.get("mood"), None, scene_num)

                scene_id = row["id"]
                shot_ids = []
                # Resolve scene-level character names to slugs for all shots
                raw_chars = scene.get("characters") or []
                chars_as_slugs = [
                    char_slug_map.get(c.lower(), _name_to_slug(c))
                    for c in raw_chars
                ] if raw_chars else None

                for j, shot in enumerate(scene.get("suggested_shots", [])):
                    dial_char = shot.get("dialogue_character")
                    dial_slug = None
                    if dial_char:
                        dial_slug = char_slug_map.get(dial_char.lower(), _name_to_slug(dial_char))

                    shot_row = await conn.fetchrow("""
                        INSERT INTO shots (scene_id, shot_number, shot_type,
                                           duration_seconds, motion_prompt,
                                           characters_present, status,
                                           dialogue_text, dialogue_character_slug)
                        VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7, $8)
                        RETURNING id
                    """, scene_id, j + 1, shot.get("shot_type", "medium"),
                        shot.get("duration_seconds", 3),
                        shot.get("motion_prompt") or shot.get("description", ""),
                        chars_as_slugs,
                        shot.get("dialogue_text"), dial_slug)
                    shot_ids.append(str(shot_row["id"]))

                # Update total_shots on scene
                await conn.execute(
                    "UPDATE scenes SET total_shots = $2 WHERE id = $1",
                    scene_id, len(shot_ids))

                # Link to episode if provided
                if ep_uuid:
                    await conn.execute("""
                        INSERT INTO episode_scenes (episode_id, scene_id, position)
                        VALUES ($1, $2, $3)
                    """, ep_uuid, scene_id, max_pos + i + 1)

                saved.append({
                    "scene_id": str(scene_id), "scene_number": scene_num,
                    "title": scene.get("title"), "shots_created": len(shot_ids),
                    "shot_ids": shot_ids,
                })

        logger.info(f"Persisted {len(saved)} scenes with shots for project {project_id}"
                     + (f" (episode {episode_id})" if episode_id else ""))
        return saved
    finally:
        await conn.close()


@router.post("/scenes/{scene_id}/generate-shots")
async def generate_shots_for_scene(scene_id: str):
    """Auto-generate shot breakdowns for an existing scene that has 0 shots.

    Uses the scene description + project characters to plan shots via Ollama.
    """
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow(
            "SELECT s.*, p.name as project_name, p.id as pid, p.genre "
            "FROM scenes s JOIN projects p ON p.id = s.project_id "
            "WHERE s.id = $1", sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")

        existing = await conn.fetchval(
            "SELECT COUNT(*) FROM shots WHERE scene_id = $1", sid)
        if existing > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Scene already has {existing} shots. Delete them first to regenerate.")

        chars = await conn.fetch(
            "SELECT name, design_prompt FROM characters WHERE project_id = $1",
            scene["pid"])
        char_list = "\n".join(
            f"- {c['name']}: {c['design_prompt'] or 'no description'}"
            for c in chars) if chars else "No characters defined."
    finally:
        await conn.close()

    # Build prompt for shot breakdown
    import httpx
    from packages.core.config import OLLAMA_URL

    prompt = f"""You are a professional anime scene planner. Break this scene into 3-5 concrete production shots.

Scene: {scene['title']}
Description: {scene['description'] or 'No description'}
Mood: {scene['mood'] or 'not specified'}
Location: {scene['location'] or 'not specified'}
Genre: {scene['genre'] or 'anime'}

Characters available:
{char_list}

For each shot provide:
- shot_type: establishing/wide/medium/close-up/action
- description: What this shot shows (1 sentence)
- motion_prompt: FramePack motion description — what moves/happens (1-2 sentences)
- duration_seconds: 2-5
- dialogue_character: Character name who speaks (null if no dialogue)
- dialogue_text: What the character says (null if no dialogue)

Respond with ONLY a valid JSON array. No markdown, no explanation."""

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": "gemma3:12b",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 2048},
            },
        )
        resp.raise_for_status()
        result = resp.json()

    raw_text = result.get("response", "").strip()
    if "```" in raw_text:
        parts = raw_text.split("```")
        for part in parts:
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("["):
                raw_text = cleaned
                break

    shots_plan = json.loads(raw_text)
    if not isinstance(shots_plan, list):
        raise HTTPException(status_code=502, detail="AI returned non-array response")

    # Build char slug map
    conn = await connect_direct()
    try:
        char_slug_map = {c["name"].lower(): _name_to_slug(c["name"])
                         for c in chars}

        shot_ids = []
        for j, shot in enumerate(shots_plan):
            dial_char = shot.get("dialogue_character")
            dial_slug = None
            if dial_char:
                dial_slug = char_slug_map.get(dial_char.lower(), _name_to_slug(dial_char))

            shot.setdefault("shot_type", "medium")
            shot.setdefault("duration_seconds", 3)
            shot.setdefault("motion_prompt", shot.get("description", ""))

            row = await conn.fetchrow("""
                INSERT INTO shots (scene_id, shot_number, shot_type,
                                   duration_seconds, motion_prompt,
                                   status, dialogue_text, dialogue_character_slug)
                VALUES ($1, $2, $3, $4, $5, 'pending', $6, $7)
                RETURNING id
            """, sid, j + 1, shot["shot_type"],
                shot["duration_seconds"],
                shot.get("motion_prompt") or shot.get("description", ""),
                shot.get("dialogue_text"), dial_slug)
            shot_ids.append(str(row["id"]))

        await conn.execute(
            "UPDATE scenes SET total_shots = $2 WHERE id = $1", sid, len(shot_ids))
    finally:
        await conn.close()

    return {
        "scene_id": scene_id, "title": scene["title"],
        "shots_created": len(shot_ids), "shot_ids": shot_ids,
    }


@router.post("/scenes/generate-shots-all")
async def generate_shots_for_all_empty_scenes(project_id: int):
    """Generate shot breakdowns for ALL scenes in a project that have 0 shots."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT s.id, s.title
            FROM scenes s
            WHERE s.project_id = $1
              AND (SELECT COUNT(*) FROM shots WHERE scene_id = s.id) = 0
            ORDER BY s.scene_number NULLS LAST
        """, project_id)
    finally:
        await conn.close()

    if not rows:
        return {"message": "All scenes already have shots", "generated": 0}

    results = []
    errors = []
    for scene_row in rows:
        try:
            result = await generate_shots_for_scene(str(scene_row["id"]))
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to generate shots for scene {scene_row['title']}: {e}")
            errors.append({"scene_id": str(scene_row["id"]),
                          "title": scene_row["title"], "error": str(e)})

    return {
        "message": f"Generated shots for {len(results)} scenes",
        "generated": len(results), "scenes": results,
        "errors": errors if errors else None,
    }


@router.get("/scenes/motion-presets")
async def get_motion_presets(shot_type: str | None = None):
    """Get motion prompt presets, optionally filtered by shot type."""
    if shot_type:
        presets = MOTION_PRESETS.get(shot_type, [])
        return {"shot_type": shot_type, "presets": presets}
    return {"presets": MOTION_PRESETS}


@router.get("/scenes/{scene_id}/shot-recommendations")
async def get_shot_recommendations(scene_id: str, top_n: int = 5):
    """Get smart image recommendations for each shot in a scene."""
    from .image_recommender import recommend_for_scene

    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow(
            "SELECT project_id FROM scenes WHERE id = $1", sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        shots = await conn.fetch(
            "SELECT id, shot_number, shot_type, camera_angle, "
            "characters_present, source_image_path "
            "FROM shots WHERE scene_id = $1 ORDER BY shot_number", sid)
        shot_list = [{
            "id": str(sh["id"]),
            "shot_number": sh["shot_number"],
            "shot_type": sh["shot_type"],
            "camera_angle": sh["camera_angle"],
            "characters_present": sh["characters_present"] or [],
            "source_image_path": sh["source_image_path"],
        } for sh in shots]

        char_map = await get_char_project_map()
        approved: dict[str, list[str]] = {}
        for slug, info in char_map.items():
            approval_file = BASE_PATH / slug / "approval_status.json"
            images_dir = BASE_PATH / slug / "images"
            if not images_dir.exists():
                continue
            if approval_file.exists():
                with open(approval_file) as f:
                    statuses = json.load(f)
                imgs = [
                    name for name, st in statuses.items()
                    if (st == "approved" or (isinstance(st, dict) and st.get("status") == "approved"))
                    and (images_dir / name).exists()
                ]
                if imgs:
                    approved[slug] = sorted(imgs)

        recommendations = recommend_for_scene(BASE_PATH, shot_list, approved, top_n)
        return {"scene_id": scene_id, "shots": recommendations}
    finally:
        await conn.close()


@router.get("/scenes/{scene_id}")
async def get_scene(scene_id: str):
    """Get scene detail with all shots."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow("""
            SELECT s.*, p.name as project_name
            FROM scenes s LEFT JOIN projects p ON s.project_id = p.id
            WHERE s.id = $1
        """, sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        shots = await conn.fetch(
            "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number", sid)
        shot_list = []
        for sh in shots:
            shot_list.append({
                "id": str(sh["id"]), "shot_number": sh["shot_number"],
                "shot_type": sh["shot_type"], "camera_angle": sh["camera_angle"],
                "duration_seconds": float(sh["duration_seconds"]) if sh["duration_seconds"] else 3.0,
                "characters_present": sh["characters_present"] or [],
                "motion_prompt": sh["motion_prompt"] or sh["generation_prompt"],
                "source_image_path": sh["source_image_path"],
                "first_frame_path": sh["first_frame_path"],
                "last_frame_path": sh["last_frame_path"],
                "output_video_path": sh["output_video_path"],
                "comfyui_prompt_id": sh["comfyui_prompt_id"],
                "status": sh["status"] or "pending",
                "seed": sh["seed"], "steps": sh["steps"],
                "use_f1": sh["use_f1"] or False,
                "quality_score": sh["quality_score"],
                "error_message": sh["error_message"],
                "generation_time_seconds": sh["generation_time_seconds"],
                "dialogue_text": sh.get("dialogue_text"),
                "dialogue_character_slug": sh.get("dialogue_character_slug"),
                "video_engine": sh.get("video_engine") or "framepack",
                "transition_type": sh.get("transition_type") or "dissolve",
                "transition_duration": float(sh.get("transition_duration") or 0.3),
            })
        return {
            "id": str(scene["id"]), "project_id": scene["project_id"],
            "project_name": scene["project_name"],
            "title": scene["title"], "description": scene["description"],
            "location": scene["location"], "time_of_day": scene["time_of_day"],
            "weather": scene["weather"], "mood": scene["mood"],
            "generation_status": scene["generation_status"] or "draft",
            "target_duration_seconds": scene["target_duration_seconds"],
            "actual_duration_seconds": scene["actual_duration_seconds"],
            "total_shots": len(shot_list),
            "completed_shots": scene["completed_shots"] or 0,
            "final_video_path": scene["final_video_path"],
            "current_generating_shot_id": str(scene["current_generating_shot_id"]) if scene["current_generating_shot_id"] else None,
            "narrative_text": scene["narrative_text"],
            "emotional_tone": scene["emotional_tone"],
            "camera_directions": scene["camera_directions"],
            "audio": {
                "track_id": scene["audio_track_id"],
                "track_name": scene["audio_track_name"],
                "track_artist": scene["audio_track_artist"],
                "preview_url": scene["audio_preview_url"],
                "fade_in": scene["audio_fade_in"],
                "fade_out": scene["audio_fade_out"],
                "start_offset": scene["audio_start_offset"],
                "auto_duck": scene.get("audio_auto_duck", False),
                "generation_mode": scene.get("audio_generation_mode"),
                "source_playlist_id": scene.get("audio_source_playlist_id"),
            } if scene["audio_track_id"] else None,
            "shots": shot_list,
        }
    finally:
        await conn.close()


@router.patch("/scenes/{scene_id}")
async def update_scene(scene_id: str, body: SceneUpdateRequest):
    """Update scene metadata."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        updates, params, idx = [], [], 2
        for field in ["title", "description", "location", "time_of_day", "weather", "mood", "target_duration_seconds", "post_interpolate_fps", "post_upscale_factor"]:
            val = getattr(body, field, None)
            if val is not None:
                updates.append(f"{field} = ${idx}")
                params.append(val)
                idx += 1
        if not updates:
            return {"message": "No fields to update"}
        updates.append("updated_at = NOW()")
        await conn.execute(f"UPDATE scenes SET {', '.join(updates)} WHERE id = $1", sid, *params)

        # Emit scene updated event for NSM propagation
        changed_fields = [f for f in ["title", "description", "location", "time_of_day", "weather", "mood"] if getattr(body, f, None) is not None]
        if changed_fields:
            await event_bus.emit(SCENE_UPDATED, {
                "scene_id": str(sid),
                "changed_fields": changed_fields,
            })

        return {"message": "Scene updated"}
    finally:
        await conn.close()


@router.delete("/scenes/{scene_id}")
async def delete_scene(scene_id: str):
    """Delete a scene and its shots."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        await conn.execute("DELETE FROM shots WHERE scene_id = $1", sid)
        await conn.execute("DELETE FROM scenes WHERE id = $1", sid)
        return {"message": "Scene deleted"}
    finally:
        await conn.close()


@router.post("/scenes/{scene_id}/shots")
async def create_shot(scene_id: str, body: ShotCreateRequest):
    """Add a shot to a scene."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        row = await conn.fetchrow("""
            INSERT INTO shots (scene_id, shot_number, source_image_path, shot_type,
                               camera_angle, duration_seconds, motion_prompt,
                               characters_present, seed, steps, use_f1, status,
                               dialogue_text, dialogue_character_slug,
                               transition_type, transition_duration, video_engine)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'pending', $12, $13, $14, $15, $16)
            RETURNING id
        """, sid, body.shot_number, body.source_image_path, body.shot_type,
            body.camera_angle, body.duration_seconds, body.motion_prompt,
            body.characters_present if body.characters_present else None,
            body.seed, body.steps, body.use_f1,
            body.dialogue_text, body.dialogue_character_slug,
            body.transition_type, body.transition_duration, body.video_engine)
        return {"id": str(row["id"]), "shot_number": body.shot_number}
    finally:
        await conn.close()


@router.patch("/scenes/{scene_id}/shots/{shot_id}")
async def update_shot(scene_id: str, shot_id: str, body: ShotUpdateRequest):
    """Update a shot."""
    shid = uuid.UUID(shot_id)
    conn = await connect_direct()
    try:
        updates, params, idx = [], [], 2
        for field, col in [
            ("shot_number", "shot_number"), ("source_image_path", "source_image_path"),
            ("shot_type", "shot_type"), ("camera_angle", "camera_angle"),
            ("duration_seconds", "duration_seconds"), ("motion_prompt", "motion_prompt"),
            ("characters_present", "characters_present"),
            ("seed", "seed"), ("steps", "steps"), ("use_f1", "use_f1"),
            ("dialogue_text", "dialogue_text"), ("dialogue_character_slug", "dialogue_character_slug"),
            ("transition_type", "transition_type"), ("transition_duration", "transition_duration"),
            ("video_engine", "video_engine"),
        ]:
            val = getattr(body, field, None)
            if val is not None:
                updates.append(f"{col} = ${idx}")
                params.append(val)
                idx += 1
        if not updates:
            return {"message": "No fields to update"}
        await conn.execute(f"UPDATE shots SET {', '.join(updates)} WHERE id = $1", shid, *params)

        # Emit shot updated event for NSM
        changed_fields = [f for f, _ in [
            ("motion_prompt", "motion_prompt"), ("characters_present", "characters_present"),
            ("shot_type", "shot_type"), ("camera_angle", "camera_angle"),
        ] if getattr(body, f, None) is not None]
        if changed_fields:
            await event_bus.emit(SHOT_UPDATED, {
                "shot_id": str(shid),
                "scene_id": scene_id,
                "changed_fields": changed_fields,
            })

        return {"message": "Shot updated"}
    finally:
        await conn.close()


@router.delete("/scenes/{scene_id}/shots/{shot_id}")
async def delete_shot(scene_id: str, shot_id: str):
    """Delete a shot."""
    shid = uuid.UUID(shot_id)
    conn = await connect_direct()
    try:
        await conn.execute("DELETE FROM shots WHERE id = $1", shid)
        return {"message": "Shot deleted"}
    finally:
        await conn.close()


# --- Audio Assignment Endpoints ---

@router.post("/scenes/{scene_id}/audio")
async def set_scene_audio(scene_id: str, body: SceneAudioRequest):
    """Assign an Apple Music track to a scene for audio overlay during assembly."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        exists = await conn.fetchval("SELECT 1 FROM scenes WHERE id = $1", sid)
        if not exists:
            raise HTTPException(status_code=404, detail="Scene not found")
        await conn.execute("""
            UPDATE scenes SET audio_track_id = $2, audio_track_name = $3,
                   audio_track_artist = $4, audio_preview_url = $5,
                   audio_fade_in = $6, audio_fade_out = $7, audio_start_offset = $8,
                   audio_auto_duck = $9, audio_generation_mode = $10,
                   audio_source_playlist_id = $11
            WHERE id = $1
        """, sid, body.track_id, body.track_name, body.track_artist,
            body.preview_url, body.fade_in, body.fade_out, body.start_offset,
            body.auto_duck, body.generation_mode, body.source_playlist_id)
        return {
            "message": "Audio track assigned to scene",
            "scene_id": scene_id,
            "track": {"name": body.track_name, "artist": body.track_artist},
        }
    finally:
        await conn.close()


@router.delete("/scenes/{scene_id}/audio")
async def remove_scene_audio(scene_id: str):
    """Remove audio track assignment from a scene."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        exists = await conn.fetchval("SELECT 1 FROM scenes WHERE id = $1", sid)
        if not exists:
            raise HTTPException(status_code=404, detail="Scene not found")
        await conn.execute("""
            UPDATE scenes SET audio_track_id = NULL, audio_track_name = NULL,
                   audio_track_artist = NULL, audio_preview_url = NULL,
                   audio_preview_path = NULL, audio_fade_in = 1.0,
                   audio_fade_out = 2.0, audio_start_offset = 0,
                   audio_auto_duck = FALSE, audio_generation_mode = NULL,
                   audio_source_playlist_id = NULL
            WHERE id = $1
        """, sid)
        return {"message": "Audio track removed from scene", "scene_id": scene_id}
    finally:
        await conn.close()


@router.post("/scenes/{scene_id}/generate-music")
async def generate_scene_music(scene_id: str):
    """Generate AI music for a scene based on its mood via ACE-Step."""
    import urllib.request as _req
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow(
            "SELECT mood, target_duration_seconds, title FROM scenes WHERE id = $1", sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")

        mood = (scene["mood"] or "ambient").split(",")[0].strip().lower()
        duration = scene["target_duration_seconds"] or 30

        from packages.audio_composition.router import MOOD_PROMPTS, _build_music_caption
        caption = _build_music_caption(mood, "orchestral anime soundtrack")

        payload = json.dumps({
            "prompt": caption,
            "lyrics": "",
            "duration": float(duration),
            "format": "wav",
            "instrumental": True,
            "infer_steps": 60,
            "guidance_scale": 15.0,
        }).encode()
        req = _req.Request(
            "http://localhost:8440/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = _req.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        task_id = result.get("task_id")

        await conn.execute(
            "UPDATE scenes SET generated_music_task_id = $2 WHERE id = $1",
            sid, task_id,
        )

        return {
            "task_id": task_id,
            "scene_id": scene_id,
            "scene_title": scene["title"],
            "mood": mood,
            "caption": caption,
            "duration": duration,
            "status": "pending",
            "poll_url": f"/api/audio/generate-music/{task_id}/status",
        }
    except urllib.error.URLError as e:
        raise HTTPException(status_code=503, detail=f"ACE-Step unavailable: {e}")
    finally:
        await conn.close()


@router.post("/scenes/{scene_id}/attach-music")
async def attach_scene_music(scene_id: str, body: dict):
    """Attach a generated or uploaded music file to a scene."""
    import urllib.request as _req
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        music_path = body.get("path")

        if not music_path and body.get("task_id"):
            try:
                poll_req = _req.Request(f"http://localhost:8440/status/{body['task_id']}")
                poll_resp = _req.urlopen(poll_req, timeout=10)
                status = json.loads(poll_resp.read())
                if status.get("status") == "completed" and status.get("output_path"):
                    music_path = status["output_path"]
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Cannot resolve ACE-Step task: {e}")

        if not music_path or not Path(music_path).exists():
            raise HTTPException(status_code=400, detail="No valid music path provided")

        from .builder import MUSIC_CACHE
        dest = MUSIC_CACHE / f"scene_{scene_id}_{Path(music_path).name}"
        if not dest.exists():
            import shutil
            shutil.copy2(music_path, str(dest))

        await conn.execute(
            "UPDATE scenes SET generated_music_path = $2 WHERE id = $1",
            sid, str(dest),
        )

        return {"scene_id": scene_id, "music_path": str(dest), "status": "attached"}
    finally:
        await conn.close()


# --- Generation Endpoints ---

@router.post("/scenes/{scene_id}/generate")
async def generate_scene_endpoint(scene_id: str):
    """Start scene generation (background task)."""
    sid = uuid.UUID(scene_id)
    if scene_id in _scene_generation_tasks:
        task = _scene_generation_tasks[scene_id]
        if not task.done():
            raise HTTPException(status_code=409, detail="Scene is already generating")
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow("SELECT * FROM scenes WHERE id = $1", sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        shot_count = await conn.fetchval(
            "SELECT COUNT(*) FROM shots WHERE scene_id = $1", sid)
        if shot_count == 0:
            raise HTTPException(status_code=400, detail="Scene has no shots")
        await conn.execute(
            "UPDATE shots SET status = 'pending', error_message = NULL WHERE scene_id = $1", sid)
        await conn.execute(
            "UPDATE scenes SET completed_shots = 0, current_generating_shot_id = NULL WHERE id = $1", sid)
        shots = await conn.fetch(
            "SELECT duration_seconds FROM shots WHERE scene_id = $1 ORDER BY shot_number", sid)
        est_minutes = 0
        for sh in shots:
            dur = float(sh["duration_seconds"] or 3)
            if dur <= 2: est_minutes += 20
            elif dur <= 3: est_minutes += 13
            elif dur <= 5: est_minutes += 25
            else: est_minutes += 30
    finally:
        await conn.close()

    async def _guarded_generate(scene_uuid):
        async with _scene_gen_semaphore:
            await generate_scene(scene_uuid)

    task = asyncio.create_task(_guarded_generate(sid))
    _scene_generation_tasks[scene_id] = task
    return {"message": "Scene generation started", "total_shots": shot_count, "estimated_minutes": est_minutes}


@router.get("/scenes/{scene_id}/status")
async def get_scene_status(scene_id: str):
    """Poll generation progress for a scene."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow("""
            SELECT generation_status, total_shots, completed_shots,
                   current_generating_shot_id, final_video_path, actual_duration_seconds
            FROM scenes WHERE id = $1
        """, sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        shots = await conn.fetch(
            "SELECT id, shot_number, status, output_video_path, error_message, "
            "comfyui_prompt_id, generation_time_seconds, quality_score, motion_prompt "
            "FROM shots WHERE scene_id = $1 ORDER BY shot_number", sid)
        shot_statuses = [{
            "id": str(sh["id"]), "shot_number": sh["shot_number"],
            "status": sh["status"] or "pending",
            "output_video_path": sh["output_video_path"],
            "error_message": sh["error_message"],
            "comfyui_prompt_id": sh["comfyui_prompt_id"],
            "generation_time_seconds": sh["generation_time_seconds"],
            "quality_score": sh["quality_score"],
            "motion_prompt": sh["motion_prompt"],
        } for sh in shots]
        return {
            "generation_status": scene["generation_status"] or "draft",
            "total_shots": scene["total_shots"] or len(shots),
            "completed_shots": scene["completed_shots"] or 0,
            "current_generating_shot_id": str(scene["current_generating_shot_id"]) if scene["current_generating_shot_id"] else None,
            "final_video_path": scene["final_video_path"],
            "actual_duration_seconds": scene["actual_duration_seconds"],
            "shots": shot_statuses,
        }
    finally:
        await conn.close()


@router.post("/scenes/{scene_id}/shots/{shot_id}/regenerate")
async def regenerate_shot(scene_id: str, shot_id: str):
    """Regenerate a single failed shot."""
    shid = uuid.UUID(shot_id)
    sid = uuid.UUID(scene_id)
    if scene_id in _scene_generation_tasks:
        task = _scene_generation_tasks[scene_id]
        if not task.done():
            raise HTTPException(status_code=409, detail="Scene is currently generating")
    conn = await connect_direct()
    try:
        shot = await conn.fetchrow("SELECT * FROM shots WHERE id = $1 AND scene_id = $2", shid, sid)
        if not shot:
            raise HTTPException(status_code=404, detail="Shot not found")
        await conn.execute(
            "UPDATE shots SET status = 'pending', error_message = NULL WHERE id = $1", shid)
        prev = await conn.fetchrow(
            "SELECT last_frame_path FROM shots WHERE scene_id = $1 AND shot_number < $2 "
            "ORDER BY shot_number DESC LIMIT 1", sid, shot["shot_number"])
        if prev and prev["last_frame_path"] and Path(prev["last_frame_path"]).exists():
            image_filename = await copy_to_comfyui_input(prev["last_frame_path"])
            first_frame = prev["last_frame_path"]
        else:
            image_filename = await copy_to_comfyui_input(shot["source_image_path"])
            src_p = shot["source_image_path"]
            first_frame = str(BASE_PATH / src_p) if not Path(src_p).is_absolute() else src_p
        prompt_text = shot["motion_prompt"] or shot["generation_prompt"] or ""
        workflow_data, _, _ = build_framepack_workflow(
            prompt_text=prompt_text, image_path=image_filename,
            total_seconds=float(shot["duration_seconds"] or 3),
            steps=shot["steps"] or 25, use_f1=shot["use_f1"] or False,
            seed=shot["seed"], gpu_memory_preservation=6.0)
        comfyui_prompt_id = _submit_comfyui_workflow(workflow_data["prompt"])
        await conn.execute(
            "UPDATE shots SET status = 'generating', comfyui_prompt_id = $2, first_frame_path = $3 WHERE id = $1",
            shid, comfyui_prompt_id, first_frame)
    finally:
        await conn.close()

    async def _regen_single():
        import time as _time
        start = _time.time()
        result = await poll_comfyui_completion(comfyui_prompt_id)
        c = await connect_direct()
        try:
            if result["status"] == "completed" and result["output_files"]:
                vpath = str(COMFYUI_OUTPUT_DIR / result["output_files"][0])
                last_frame = await extract_last_frame(vpath)
                await c.execute("""
                    UPDATE shots SET status = 'completed', output_video_path = $2,
                           last_frame_path = $3, generation_time_seconds = $4
                    WHERE id = $1
                """, shid, vpath, last_frame, _time.time() - start)
            else:
                await c.execute(
                    "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                    shid, f"ComfyUI {result['status']}")
        finally:
            await c.close()
    asyncio.create_task(_regen_single())
    return {"message": "Shot regeneration started", "comfyui_prompt_id": comfyui_prompt_id}


@router.post("/scenes/{scene_id}/assemble")
async def assemble_scene(scene_id: str):
    """Re-concatenate completed shots into scene video."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        shots = await conn.fetch(
            "SELECT output_video_path FROM shots WHERE scene_id = $1 AND status = 'completed' "
            "ORDER BY shot_number", sid)
        if not shots:
            raise HTTPException(status_code=400, detail="No completed shots to assemble")
        video_paths = [sh["output_video_path"] for sh in shots if sh["output_video_path"]]
        if not video_paths:
            raise HTTPException(status_code=400, detail="No video files found")
        scene_video_path = str(SCENE_OUTPUT_DIR / f"scene_{scene_id}.mp4")
        await concat_videos(video_paths, scene_video_path)

        await apply_scene_audio(conn, sid, scene_video_path)

        probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", scene_video_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await probe.communicate()
        duration = float(stdout.decode().strip()) if stdout.decode().strip() else None
        await conn.execute("""
            UPDATE scenes SET final_video_path = $2, actual_duration_seconds = $3,
                   generation_status = CASE WHEN completed_shots = total_shots THEN 'completed' ELSE 'partial' END
            WHERE id = $1
        """, sid, scene_video_path, duration)
        return {"message": "Scene assembled", "video_path": scene_video_path,
                "duration_seconds": duration, "shots_included": len(video_paths)}
    finally:
        await conn.close()


@router.get("/scenes/{scene_id}/video")
async def serve_scene_video(scene_id: str):
    """Serve assembled scene video."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        path = await conn.fetchval("SELECT final_video_path FROM scenes WHERE id = $1", sid)
    finally:
        await conn.close()
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Scene video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"scene_{scene_id}.mp4")


@router.get("/scenes/{scene_id}/shots/{shot_id}/video")
async def serve_shot_video(scene_id: str, shot_id: str):
    """Serve individual shot video."""
    shid = uuid.UUID(shot_id)
    conn = await connect_direct()
    try:
        path = await conn.fetchval("SELECT output_video_path FROM shots WHERE id = $1", shid)
    finally:
        await conn.close()
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Shot video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"shot_{shot_id}.mp4")


@router.get("/scenes/{scene_id}/approved-images")
async def get_approved_images_for_scene(
    scene_id: str, project_id: int = 0, include_metadata: bool = False,
):
    """Get approved images for characters in a project (for shot source image picker)."""
    char_map = await get_char_project_map()
    results = {}
    for slug, info in char_map.items():
        if project_id and info.get("project_name"):
            pass
        approval_file = BASE_PATH / slug / "approval_status.json"
        images_dir = BASE_PATH / slug / "images"
        if not images_dir.exists():
            continue
        approved = []
        if approval_file.exists():
            with open(approval_file) as f:
                statuses = json.load(f)
            for name, st in statuses.items():
                if st == "approved" or (isinstance(st, dict) and st.get("status") == "approved"):
                    if (images_dir / name).exists():
                        approved.append(name)
        if not approved:
            continue
        approved.sort()

        if include_metadata:
            from .image_recommender import batch_read_metadata
            meta_map = batch_read_metadata(BASE_PATH, slug, approved)
            enriched = []
            for name in approved:
                meta = meta_map.get(name, {})
                vr = meta.get("vision_review", {})
                vision_parts = []
                if isinstance(vr, dict):
                    if vr.get("solo") is not None:
                        vision_parts.append("solo" if vr["solo"] else "multi")
                    if vr.get("completeness"):
                        vision_parts.append(vr["completeness"])
                enriched.append({
                    "name": name,
                    "pose": meta.get("pose"),
                    "quality_score": meta.get("quality_score"),
                    "vision_summary": ", ".join(vision_parts) if vision_parts else None,
                })
            results[slug] = {
                "character_name": info.get("name", slug),
                "images": enriched,
            }
        else:
            results[slug] = {
                "character_name": info.get("name", slug),
                "images": approved,
            }
    return {"characters": results}


# --- Batch Dialogue Generation ---

@router.post("/scenes/{scene_id}/generate-dialogue")
async def generate_dialogue_for_scene(scene_id: str):
    """Auto-generate dialogue for all shots in a scene that have characters but no dialogue."""
    from packages.voice_pipeline.synthesis import generate_dialogue_from_story
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow(
            "SELECT title, description, mood FROM scenes WHERE id = $1", sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")

        shots = await conn.fetch(
            "SELECT id, shot_number, characters_present, dialogue_text, "
            "dialogue_character_slug, motion_prompt "
            "FROM shots WHERE scene_id = $1 ORDER BY shot_number", sid)

        if not shots:
            return {"scene_id": scene_id, "generated": 0, "dialogue": []}

        # Gather all characters present across shots
        all_chars = set()
        for sh in shots:
            if sh["characters_present"]:
                for c in sh["characters_present"]:
                    all_chars.add(c)

        if not all_chars:
            return {"scene_id": scene_id, "generated": 0, "dialogue": [],
                    "message": "No characters present in any shots"}

        # Generate dialogue for the whole scene
        desc = f"{scene['title'] or 'Untitled'}: {scene['description'] or ''}"
        if scene["mood"]:
            desc += f" (mood: {scene['mood']})"
        dialogue_lines = await generate_dialogue_from_story(
            scene_id, desc, list(all_chars))

        if not dialogue_lines:
            return {"scene_id": scene_id, "generated": 0, "dialogue": [],
                    "message": "AI returned no dialogue"}

        # Assign dialogue to shots that have matching characters
        generated = 0
        results = []
        line_idx = 0
        for sh in shots:
            # Skip shots that already have dialogue
            if sh["dialogue_text"]:
                continue
            chars_present = sh["characters_present"] or []
            if not chars_present:
                continue
            # Find a dialogue line for a character in this shot
            while line_idx < len(dialogue_lines):
                line = dialogue_lines[line_idx]
                line_idx += 1
                slug = line["character_slug"]
                if slug in chars_present:
                    await conn.execute(
                        "UPDATE shots SET dialogue_text = $2, dialogue_character_slug = $3 "
                        "WHERE id = $1",
                        sh["id"], line["text"], slug)
                    generated += 1
                    results.append({
                        "shot_id": str(sh["id"]),
                        "shot_number": sh["shot_number"],
                        "character_slug": slug,
                        "character_name": line.get("character_name", slug),
                        "text": line["text"],
                    })
                    break

        return {"scene_id": scene_id, "generated": generated, "dialogue": results}
    finally:
        await conn.close()


@router.get("/scenes/source-image-stats")
async def source_image_stats(project_id: int):
    """Get source image effectiveness stats per character for a project."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT sie.character_slug,
                   sie.image_name,
                   AVG(sie.video_quality_score) as avg_video_quality,
                   COUNT(*) as times_used,
                   AVG(sie.character_match) as avg_character_match,
                   AVG(sie.style_match) as avg_style_match
            FROM source_image_effectiveness sie
            JOIN shots sh ON sie.shot_id = sh.id
            JOIN scenes sc ON sh.scene_id = sc.id
            WHERE sc.project_id = $1
              AND sie.video_quality_score IS NOT NULL
            GROUP BY sie.character_slug, sie.image_name
            ORDER BY sie.character_slug, avg_video_quality DESC
        """, project_id)

        auto_counts = await conn.fetch("""
            SELECT UNNEST(sh.characters_present) as character_slug,
                   COUNT(*) FILTER (WHERE sh.source_image_auto_assigned = TRUE) as auto_assigned,
                   COUNT(*) as total_shots
            FROM shots sh
            JOIN scenes sc ON sh.scene_id = sc.id
            WHERE sc.project_id = $1
            GROUP BY character_slug
        """, project_id)
        auto_map = {r["character_slug"]: dict(r) for r in auto_counts}

        # Group by character
        from collections import defaultdict
        by_char: dict[str, list] = defaultdict(list)
        for r in rows:
            by_char[r["character_slug"]].append({
                "image_name": r["image_name"],
                "avg_video_quality": round(float(r["avg_video_quality"]), 3),
                "times_used": r["times_used"],
                "avg_character_match": round(float(r["avg_character_match"]), 3) if r["avg_character_match"] else None,
                "avg_style_match": round(float(r["avg_style_match"]), 3) if r["avg_style_match"] else None,
            })

        result = []
        all_slugs = set(by_char.keys()) | set(auto_map.keys())
        for slug in sorted(all_slugs):
            images = by_char.get(slug, [])
            counts = auto_map.get(slug, {})
            result.append({
                "character_slug": slug,
                "top_images": images[:5],
                "worst_images": images[-3:] if len(images) > 5 else [],
                "total_shots": counts.get("total_shots", 0),
                "auto_assigned": counts.get("auto_assigned", 0),
            })

        return {"project_id": project_id, "characters": result}
    finally:
        await conn.close()


@router.post("/scenes/generate-all")
async def generate_all_scenes(project_id: int):
    """Queue generation for all scenes that have shots but no final video.

    Scenes are generated sequentially in scene_number order to maintain
    narrative continuity (each scene's last frame feeds the next).
    """
    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT s.id, s.title, s.scene_number, s.generation_status,
                   (SELECT COUNT(*) FROM shots WHERE scene_id = s.id) as shot_count
            FROM scenes s
            WHERE s.project_id = $1
              AND s.generation_status NOT IN ('generating', 'completed')
            ORDER BY s.scene_number NULLS LAST, s.created_at
        """, project_id)

        eligible = [r for r in rows if r["shot_count"] > 0]
        if not eligible:
            return {"message": "No scenes to generate", "queued": 0}

        # Check if a generate-all pipeline is already running for this project
        pipeline_key = f"pipeline_{project_id}"
        if pipeline_key in _scene_generation_tasks:
            task = _scene_generation_tasks[pipeline_key]
            if not task.done():
                return {"message": "Generation pipeline already running for this project",
                        "queued": 0}

        # Reset all eligible shots to pending
        for scene_row in eligible:
            sid = scene_row["id"]
            await conn.execute(
                "UPDATE shots SET status = 'pending', error_message = NULL "
                "WHERE scene_id = $1", sid)
            await conn.execute(
                "UPDATE scenes SET completed_shots = 0, "
                "current_generating_shot_id = NULL WHERE id = $1", sid)

        scene_ids = [r["id"] for r in eligible]
        queued = [{"scene_id": str(r["id"]), "title": r["title"],
                   "scene_number": r["scene_number"],
                   "shot_count": r["shot_count"]} for r in eligible]

        async def _sequential_pipeline(ordered_scene_ids):
            """Generate scenes one at a time in order."""
            for sid in ordered_scene_ids:
                scene_id_str = str(sid)
                try:
                    async with _scene_gen_semaphore:
                        logger.info(f"generate-all: starting scene {scene_id_str}")
                        await generate_scene(sid)
                        logger.info(f"generate-all: completed scene {scene_id_str}")
                except Exception as e:
                    logger.error(f"generate-all: scene {scene_id_str} failed: {e}")
                    # Continue to next scene on failure
                _scene_generation_tasks.pop(scene_id_str, None)
            _scene_generation_tasks.pop(pipeline_key, None)
            logger.info(f"generate-all: pipeline finished for project {project_id}")

        task = asyncio.create_task(_sequential_pipeline(scene_ids))
        _scene_generation_tasks[pipeline_key] = task

        return {
            "message": f"Queued {len(queued)} scenes for sequential generation",
            "queued": len(queued),
            "scenes": queued,
        }
    finally:
        await conn.close()


class SelectEngineRequest(BaseModel):
    video_engine: str
    lora_name: str | None = None
    lora_strength: float = 0.8


KNOWN_ENGINES = {"framepack", "framepack_f1", "ltx", "wan"}


@router.post("/scenes/{scene_id}/shots/{shot_id}/select-engine")
async def select_engine_for_shot(scene_id: str, shot_id: str, body: SelectEngineRequest):
    """Manually override the video engine for a specific shot."""
    if body.video_engine not in KNOWN_ENGINES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown engine '{body.video_engine}'. Valid: {sorted(KNOWN_ENGINES)}",
        )

    sid = uuid.UUID(scene_id)
    shot_uuid = uuid.UUID(shot_id)
    conn = await connect_direct()
    try:
        shot = await conn.fetchrow(
            "SELECT id FROM shots WHERE id = $1 AND scene_id = $2", shot_uuid, sid,
        )
        if not shot:
            raise HTTPException(status_code=404, detail="Shot not found in this scene")

        await conn.execute(
            "UPDATE shots SET video_engine = $1, lora_name = $2, lora_strength = $3 WHERE id = $4",
            body.video_engine, body.lora_name, body.lora_strength, shot_uuid,
        )
        return {
            "shot_id": shot_id,
            "video_engine": body.video_engine,
            "lora_name": body.lora_name,
            "lora_strength": body.lora_strength,
        }
    finally:
        await conn.close()


@router.get("/continuity-frames")
async def get_continuity_frames(project_id: int):
    """View current continuity frames for all characters in a project."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT ccf.character_slug, ccf.frame_path,
                   ccf.scene_number, ccf.shot_number,
                   s.title as scene_title, ccf.created_at
            FROM character_continuity_frames ccf
            LEFT JOIN scenes s ON s.id = ccf.scene_id
            WHERE ccf.project_id = $1
            ORDER BY ccf.character_slug
        """, project_id)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@router.delete("/continuity-frames")
async def clear_continuity_frames(project_id: int):
    """Clear all continuity frames for a project (forces cold start from approved images)."""
    conn = await connect_direct()
    try:
        result = await conn.execute(
            "DELETE FROM character_continuity_frames WHERE project_id = $1", project_id
        )
        count = int(result.split()[-1])
        return {"deleted": count, "project_id": project_id}
    finally:
        await conn.close()
