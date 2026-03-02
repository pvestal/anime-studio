"""Episode CRUD, assembly, and publishing endpoints."""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from packages.core.db import connect_direct
from packages.core.events import event_bus, EPISODE_UPDATED
from packages.core.models import (
    EpisodeCreateRequest, EpisodeUpdateRequest,
    EpisodeAddSceneRequest, EpisodeReorderRequest,
)
from .builder import assemble_episode, get_video_duration, extract_thumbnail, EPISODE_OUTPUT_DIR
from .publish import publish_episode
from packages.scene_generation.scene_audio import _auto_generate_scene_music, overlay_audio

logger = logging.getLogger(__name__)

router = APIRouter()

# Mood keywords for deriving episode mood from story_arc text
_MOOD_KEYWORDS = {
    "action": ["fight", "battle", "chase", "attack", "war", "combat", "escape"],
    "tense": ["danger", "threat", "suspense", "dark", "trapped", "risk", "betrayal"],
    "romantic": ["love", "romance", "kiss", "heart", "together", "embrace"],
    "melancholy": ["sad", "loss", "grief", "death", "farewell", "alone", "tears"],
    "comedic": ["funny", "comedy", "joke", "prank", "silly", "laugh", "humor"],
    "powerful": ["power", "epic", "hero", "triumph", "victory", "glory"],
    "peaceful": ["calm", "peace", "rest", "quiet", "morning", "nature"],
}


def _derive_mood(story_arc: str | None) -> str:
    """Derive a mood keyword from episode story_arc text for music generation."""
    if not story_arc:
        return "ambient"
    text_lower = story_arc.lower()
    scores = {}
    for mood, keywords in _MOOD_KEYWORDS.items():
        scores[mood] = sum(1 for kw in keywords if kw in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "ambient"


async def _apply_episode_music(
    conn, episode_id: uuid.UUID, episode_path: str, story_arc: str | None,
) -> str:
    """Optionally generate and overlay background music on an assembled episode.

    Only applied when zero scenes in the episode have their own music (avoids double-layering).
    Returns the (possibly updated) episode video path.
    """
    # Check if any scene already has music
    has_scene_music = await conn.fetchval("""
        SELECT COUNT(*) FROM episode_scenes es
        JOIN scenes s ON es.scene_id = s.id
        WHERE es.episode_id = $1
          AND (s.generated_music_path IS NOT NULL
               OR s.audio_preview_path IS NOT NULL
               OR s.audio_preview_url IS NOT NULL)
    """, episode_id)

    if has_scene_music and has_scene_music > 0:
        logger.info(f"Episode {episode_id}: {has_scene_music} scenes have music, skipping episode-level music")
        return episode_path

    mood = _derive_mood(story_arc)
    logger.info(f"Episode {episode_id}: generating background music (mood={mood})")

    # Get episode duration for music length
    from .builder import get_video_duration as _get_dur
    duration = await _get_dur(episode_path) or 60.0

    try:
        music_path = await _auto_generate_scene_music(
            scene_id=str(episode_id),  # reuses scene music gen with episode UUID
            mood=mood,
            duration=min(duration, 180.0),  # cap at 3 minutes
        )
    except Exception as e:
        logger.warning(f"Episode music generation failed (non-fatal): {e}")
        music_path = None

    if not music_path:
        return episode_path

    # Overlay with fade-in/out
    output = episode_path.rsplit(".", 1)[0] + "_music.mp4"
    try:
        await overlay_audio(
            video_path=episode_path,
            audio_path=music_path,
            output_path=output,
            fade_in=2.0,
            fade_out=3.0,
            start_offset=0,
        )
        import os
        os.replace(output, episode_path)
    except Exception as e:
        logger.warning(f"Episode music overlay failed (non-fatal): {e}")
        return episode_path

    # Persist to DB
    await conn.execute(
        "UPDATE episodes SET episode_music_path = $2, episode_mood = $3 WHERE id = $1",
        episode_id, music_path, mood,
    )
    logger.info(f"Episode {episode_id}: background music applied (mood={mood})")
    return episode_path


@router.get("/episodes")
async def list_episodes(project_id: int):
    """List episodes for a project."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT e.*, p.name as project_name,
                   (SELECT COUNT(*) FROM episode_scenes es WHERE es.episode_id = e.id) as scene_count
            FROM episodes e
            JOIN projects p ON e.project_id = p.id
            WHERE e.project_id = $1
            ORDER BY e.episode_number
        """, project_id)
        return {"episodes": [
            {
                "id": str(r["id"]),
                "project_id": r["project_id"],
                "project_name": r["project_name"],
                "episode_number": r["episode_number"],
                "title": r["title"],
                "description": r["description"],
                "story_arc": r["story_arc"],
                "status": r["status"] or "draft",
                "final_video_path": r["final_video_path"],
                "thumbnail_path": r["thumbnail_path"],
                "actual_duration_seconds": r["actual_duration_seconds"],
                "scene_count": r["scene_count"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]}
    finally:
        await conn.close()


@router.post("/episodes")
async def create_episode(body: EpisodeCreateRequest):
    """Create a new episode."""
    conn = await connect_direct()
    try:
        row = await conn.fetchrow("""
            INSERT INTO episodes (project_id, episode_number, title, description, story_arc)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, created_at
        """, body.project_id, body.episode_number, body.title,
            body.description, body.story_arc)
        return {
            "id": str(row["id"]),
            "episode_number": body.episode_number,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
    finally:
        await conn.close()


@router.get("/episodes/{episode_id}")
async def get_episode(episode_id: str):
    """Get episode detail with its scenes."""
    eid = uuid.UUID(episode_id)
    conn = await connect_direct()
    try:
        ep = await conn.fetchrow("""
            SELECT e.*, p.name as project_name
            FROM episodes e
            JOIN projects p ON e.project_id = p.id
            WHERE e.id = $1
        """, eid)
        if not ep:
            raise HTTPException(status_code=404, detail="Episode not found")

        scene_rows = await conn.fetch("""
            SELECT es.position, es.transition, es.scene_id,
                   s.title, s.description, s.generation_status,
                   s.actual_duration_seconds, s.final_video_path, s.total_shots
            FROM episode_scenes es
            JOIN scenes s ON es.scene_id = s.id
            WHERE es.episode_id = $1
            ORDER BY es.position
        """, eid)

        return {
            "id": str(ep["id"]),
            "project_id": ep["project_id"],
            "project_name": ep["project_name"],
            "episode_number": ep["episode_number"],
            "title": ep["title"],
            "description": ep["description"],
            "story_arc": ep["story_arc"],
            "status": ep["status"] or "draft",
            "final_video_path": ep["final_video_path"],
            "thumbnail_path": ep["thumbnail_path"],
            "actual_duration_seconds": ep["actual_duration_seconds"],
            "created_at": ep["created_at"].isoformat() if ep["created_at"] else None,
            "scenes": [
                {
                    "scene_id": str(sr["scene_id"]),
                    "position": sr["position"],
                    "transition": sr["transition"],
                    "title": sr["title"],
                    "description": sr["description"],
                    "generation_status": sr["generation_status"] or "draft",
                    "actual_duration_seconds": sr["actual_duration_seconds"],
                    "final_video_path": sr["final_video_path"],
                    "total_shots": sr["total_shots"],
                }
                for sr in scene_rows
            ],
        }
    finally:
        await conn.close()


@router.patch("/episodes/{episode_id}")
async def update_episode(episode_id: str, body: EpisodeUpdateRequest):
    """Update episode metadata."""
    eid = uuid.UUID(episode_id)
    conn = await connect_direct()
    try:
        updates, params, idx = [], [], 2
        for field in ["episode_number", "title", "description", "story_arc"]:
            val = getattr(body, field, None)
            if val is not None:
                updates.append(f"{field} = ${idx}")
                params.append(val)
                idx += 1
        if not updates:
            return {"message": "No fields to update"}
        updates.append("updated_at = NOW()")
        await conn.execute(
            f"UPDATE episodes SET {', '.join(updates)} WHERE id = $1", eid, *params)

        # Emit episode updated event for NSM
        await event_bus.emit(EPISODE_UPDATED, {
            "episode_id": str(eid),
        })

        return {"message": "Episode updated"}
    finally:
        await conn.close()


@router.delete("/episodes/{episode_id}")
async def delete_episode(episode_id: str):
    """Delete an episode (scenes are NOT deleted, only unlinked)."""
    eid = uuid.UUID(episode_id)
    conn = await connect_direct()
    try:
        await conn.execute("DELETE FROM episode_scenes WHERE episode_id = $1", eid)
        await conn.execute("DELETE FROM episodes WHERE id = $1", eid)
        return {"message": "Episode deleted"}
    finally:
        await conn.close()


@router.post("/episodes/{episode_id}/scenes")
async def add_scene_to_episode(episode_id: str, body: EpisodeAddSceneRequest):
    """Add a scene to an episode at a given position."""
    eid = uuid.UUID(episode_id)
    scene_id = uuid.UUID(body.scene_id)
    conn = await connect_direct()
    try:
        # Verify episode exists
        exists = await conn.fetchval("SELECT 1 FROM episodes WHERE id = $1", eid)
        if not exists:
            raise HTTPException(status_code=404, detail="Episode not found")

        # Verify scene exists
        exists = await conn.fetchval("SELECT 1 FROM scenes WHERE id = $1", scene_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Scene not found")

        # Shift existing positions >= target position
        await conn.execute("""
            UPDATE episode_scenes SET position = position + 1
            WHERE episode_id = $1 AND position >= $2
        """, eid, body.position)

        await conn.execute("""
            INSERT INTO episode_scenes (episode_id, scene_id, position, transition)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (episode_id, scene_id) DO UPDATE
            SET position = $3, transition = $4
        """, eid, scene_id, body.position, body.transition)

        return {"message": "Scene added to episode", "position": body.position}
    finally:
        await conn.close()


@router.delete("/episodes/{episode_id}/scenes/{scene_id}")
async def remove_scene_from_episode(episode_id: str, scene_id: str):
    """Remove a scene from an episode (scene itself is preserved)."""
    eid = uuid.UUID(episode_id)
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        pos = await conn.fetchval(
            "SELECT position FROM episode_scenes WHERE episode_id = $1 AND scene_id = $2",
            eid, sid)
        if pos is None:
            raise HTTPException(status_code=404, detail="Scene not in this episode")

        await conn.execute(
            "DELETE FROM episode_scenes WHERE episode_id = $1 AND scene_id = $2", eid, sid)

        # Compact positions
        await conn.execute("""
            UPDATE episode_scenes SET position = position - 1
            WHERE episode_id = $1 AND position > $2
        """, eid, pos)

        return {"message": "Scene removed from episode"}
    finally:
        await conn.close()


@router.put("/episodes/{episode_id}/reorder")
async def reorder_episode_scenes(episode_id: str, body: EpisodeReorderRequest):
    """Reorder scenes in an episode."""
    eid = uuid.UUID(episode_id)
    conn = await connect_direct()
    try:
        for pos, scene_id_str in enumerate(body.scene_order, start=1):
            sid = uuid.UUID(scene_id_str)
            await conn.execute("""
                UPDATE episode_scenes SET position = $3
                WHERE episode_id = $1 AND scene_id = $2
            """, eid, sid, pos)
        return {"message": "Episode scenes reordered", "count": len(body.scene_order)}
    finally:
        await conn.close()


@router.post("/episodes/{episode_id}/assemble")
async def assemble_episode_endpoint(episode_id: str):
    """Assemble all completed scenes into an episode video."""
    eid = uuid.UUID(episode_id)
    conn = await connect_direct()
    try:
        # Get scenes in order
        scene_rows = await conn.fetch("""
            SELECT es.scene_id, es.transition, s.final_video_path, s.title
            FROM episode_scenes es
            JOIN scenes s ON es.scene_id = s.id
            WHERE es.episode_id = $1
            ORDER BY es.position
        """, eid)

        if not scene_rows:
            raise HTTPException(status_code=400, detail="Episode has no scenes")

        video_paths = []
        transitions = []
        missing = []
        for sr in scene_rows:
            vp = sr["final_video_path"]
            if vp and Path(vp).exists():
                video_paths.append(vp)
                transitions.append(sr["transition"] or "cut")
            else:
                missing.append(sr["title"] or str(sr["scene_id"]))

        if not video_paths:
            raise HTTPException(
                status_code=400,
                detail=f"No completed scene videos found. Missing: {', '.join(missing)}")

        # Assemble
        episode_path = await assemble_episode(episode_id, video_paths, transitions)

        # Optionally add episode-level background music
        ep_row = await conn.fetchrow("SELECT story_arc FROM episodes WHERE id = $1", eid)
        episode_path = await _apply_episode_music(
            conn, eid, episode_path, ep_row["story_arc"] if ep_row else None,
        )

        duration = await get_video_duration(episode_path)

        # Generate thumbnail
        thumb_path = str(EPISODE_OUTPUT_DIR / f"episode_{episode_id}_thumb.jpg")
        await extract_thumbnail(episode_path, thumb_path)

        # Update DB
        await conn.execute("""
            UPDATE episodes SET status = 'assembled', final_video_path = $2,
                   actual_duration_seconds = $3, thumbnail_path = $4, updated_at = NOW()
            WHERE id = $1
        """, eid, episode_path, duration, thumb_path if Path(thumb_path).exists() else None)

        return {
            "message": "Episode assembled",
            "video_path": episode_path,
            "duration_seconds": duration,
            "scenes_included": len(video_paths),
            "scenes_missing": missing,
        }
    finally:
        await conn.close()


@router.get("/episodes/{episode_id}/video")
async def serve_episode_video(episode_id: str):
    """Serve assembled episode video."""
    eid = uuid.UUID(episode_id)
    conn = await connect_direct()
    try:
        path = await conn.fetchval("SELECT final_video_path FROM episodes WHERE id = $1", eid)
    finally:
        await conn.close()
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Episode video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"episode_{episode_id}.mp4")


@router.post("/episodes/{episode_id}/publish")
async def publish_episode_endpoint(episode_id: str, season: int = 1):
    """Publish episode to Jellyfin-compatible directory structure."""
    eid = uuid.UUID(episode_id)
    conn = await connect_direct()
    try:
        ep = await conn.fetchrow("""
            SELECT e.*, p.name as project_name
            FROM episodes e JOIN projects p ON e.project_id = p.id
            WHERE e.id = $1
        """, eid)
        if not ep:
            raise HTTPException(status_code=404, detail="Episode not found")
        if not ep["final_video_path"] or not Path(ep["final_video_path"]).exists():
            raise HTTPException(status_code=400, detail="Episode not assembled yet")

        result = await publish_episode(
            project_name=ep["project_name"],
            episode_number=ep["episode_number"],
            episode_title=ep["title"],
            video_path=ep["final_video_path"],
            season=season,
            thumbnail_path=ep["thumbnail_path"],
        )

        await conn.execute(
            "UPDATE episodes SET status = 'published', updated_at = NOW() WHERE id = $1", eid)

        return {
            "message": "Episode published to Jellyfin",
            "episode": f"S{season:02d}E{ep['episode_number']:02d} - {ep['title']}",
            **result,
        }
    finally:
        await conn.close()
