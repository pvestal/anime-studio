"""Full production pipeline — end-to-end episode production from shots to published video.

Chains: shot generation → auto-approve → voice synthesis → music gen →
audio mixing → scene assembly → episode assembly → optional Jellyfin publish.

Usage:
    POST /api/scenes/produce-episode?project_id=24&episode_number=1
    POST /api/scenes/produce-episode?project_id=24&episode_number=1&publish=true
"""

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from packages.core.db import connect_direct
from packages.core.events import event_bus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/scenes/produce-episode")
async def produce_episode(
    project_id: int,
    episode_number: int,
    publish: bool = False,
):
    """End-to-end episode production pipeline.

    Orchestrates the full pipeline from shot generation to assembled episode:
    1. Verify episode exists and has scenes with shots
    2. Generate missing shots (auto-approve so downstream fires)
    3. Wait for all scenes to complete (voice + music + assembly happen inside)
    4. Assemble episode from completed scene videos
    5. Optionally publish to Jellyfin

    Auto-approve is enabled so the full downstream pipeline fires:
    - Voice synthesis (edge-tts / RVC / SoVITS / XTTS)
    - Music generation (ACE-Step from scene mood)
    - Audio mixing with ducking (dialogue + music)
    - Scene video assembly with crossfade transitions

    Args:
        project_id: Project ID
        episode_number: Episode number to produce
        publish: If True, publish to Jellyfin after assembly
    """
    conn = await connect_direct()
    try:
        # 1. Find the episode
        episode = await conn.fetchrow("""
            SELECT e.id, e.title, e.story_arc, e.status
            FROM episodes e
            WHERE e.project_id = $1 AND e.episode_number = $2
        """, project_id, episode_number)

        if not episode:
            raise HTTPException(
                status_code=404,
                detail=f"Episode {episode_number} not found for project {project_id}",
            )

        episode_id = episode["id"]

        # 2. Get all scenes for this episode, ordered by position
        scene_rows = await conn.fetch("""
            SELECT s.id, s.title, s.scene_number, s.generation_status,
                   s.final_video_path, s.mood,
                   es.position,
                   (SELECT COUNT(*) FROM shots WHERE scene_id = s.id) as shot_count,
                   (SELECT COUNT(*) FROM shots WHERE scene_id = s.id
                    AND status = 'completed') as completed_shots
            FROM scenes s
            JOIN episode_scenes es ON es.scene_id = s.id
            WHERE es.episode_id = $1
            ORDER BY es.position
        """, episode_id)

        if not scene_rows:
            raise HTTPException(
                status_code=400,
                detail=f"Episode {episode_number} has no scenes. "
                       f"Run POST /scenes/generate-from-story?project_id={project_id}&episode_id={episode_id} first.",
            )

        # Check for scenes without shots
        empty_scenes = [r for r in scene_rows if r["shot_count"] == 0]
        if empty_scenes:
            raise HTTPException(
                status_code=400,
                detail=f"{len(empty_scenes)} scene(s) have no shots. "
                       f"Run POST /scenes/generate-shots-all?project_id={project_id} first. "
                       f"Empty: {[r['title'] for r in empty_scenes]}",
            )

        # 3. Determine which scenes need generation
        needs_generation = [
            r for r in scene_rows
            if r["generation_status"] not in ("completed", "assembled")
            or not r["final_video_path"]
            or not Path(r["final_video_path"]).exists()
        ]

        already_done = [
            r for r in scene_rows
            if r["generation_status"] in ("completed", "assembled")
            and r["final_video_path"]
            and Path(r["final_video_path"]).exists()
        ]

    finally:
        await conn.close()

    # 4. Generate scenes that need it (auto-approve enabled)
    if needs_generation:
        logger.info(
            f"produce-episode: generating {len(needs_generation)} scenes "
            f"for ep{episode_number} ({len(already_done)} already done)"
        )

        from .builder import generate_scene, _scene_generation_lock

        for scene_row in needs_generation:
            scene_id = str(scene_row["id"])
            logger.info(
                f"produce-episode: generating scene '{scene_row['title']}' "
                f"({scene_row['shot_count']} shots)"
            )

            # Reset shots to pending for this scene
            conn = await connect_direct()
            try:
                await conn.execute(
                    "UPDATE shots SET status = 'pending', error_message = NULL "
                    "WHERE scene_id = $1 AND status NOT IN ('completed', 'accepted_best')",
                    scene_row["id"],
                )
                await conn.execute(
                    "UPDATE scenes SET completed_shots = 0, "
                    "current_generating_shot_id = NULL WHERE id = $1",
                    scene_row["id"],
                )
            finally:
                await conn.close()

            # Generate with auto_approve=True so voice/music/assembly fires
            await generate_scene(scene_id, auto_approve=True)

    # 5. Verify all scenes completed
    conn = await connect_direct()
    try:
        final_scenes = await conn.fetch("""
            SELECT s.id, s.title, s.generation_status, s.final_video_path
            FROM scenes s
            JOIN episode_scenes es ON es.scene_id = s.id
            WHERE es.episode_id = $1
            ORDER BY es.position
        """, episode_id)

        completed = [
            r for r in final_scenes
            if r["final_video_path"] and Path(r["final_video_path"]).exists()
        ]
        failed = [
            r for r in final_scenes
            if not r["final_video_path"] or not Path(r["final_video_path"]).exists()
        ]

        if not completed:
            return {
                "status": "failed",
                "message": "No scenes completed successfully",
                "failed_scenes": [r["title"] for r in failed],
            }

        # 6. Assemble episode
        video_paths = []
        transitions = []
        for sr in final_scenes:
            vp = sr["final_video_path"]
            if vp and Path(vp).exists():
                video_paths.append(vp)
                transitions.append("fadeblack")  # default transition
            else:
                logger.warning(f"produce-episode: skipping scene '{sr['title']}' (no video)")

        from packages.episode_assembly.builder import (
            assemble_episode as _assemble_episode,
            get_video_duration,
            extract_thumbnail,
            EPISODE_OUTPUT_DIR,
        )
        from packages.episode_assembly.router import _apply_episode_music

        episode_path = await _assemble_episode(
            str(episode_id), video_paths, transitions,
        )

        # Apply episode-level background music
        episode_path = await _apply_episode_music(
            conn, episode_id, episode_path, episode["story_arc"],
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
        """, episode_id, episode_path, duration,
            thumb_path if Path(thumb_path).exists() else None)

        logger.info(
            f"produce-episode: ep{episode_number} assembled — "
            f"{len(completed)} scenes, {duration:.1f}s, "
            f"{len(failed)} failed"
        )

        # 7. Optionally publish to Jellyfin
        publish_result = None
        if publish and episode_path:
            try:
                from packages.episode_assembly.publish import publish_episode as _publish
                publish_result = await _publish(
                    project_id=project_id,
                    episode_id=str(episode_id),
                    video_path=episode_path,
                    episode_number=episode_number,
                    title=episode["title"],
                )
                await conn.execute(
                    "UPDATE episodes SET status = 'published', updated_at = NOW() WHERE id = $1",
                    episode_id,
                )
                logger.info(f"produce-episode: ep{episode_number} published to Jellyfin")
            except Exception as e:
                logger.warning(f"produce-episode: Jellyfin publish failed (non-fatal): {e}")
                publish_result = {"error": str(e)}

        return {
            "status": "completed",
            "episode_id": str(episode_id),
            "episode_number": episode_number,
            "title": episode["title"],
            "video_path": episode_path,
            "duration_seconds": duration,
            "scenes_completed": len(completed),
            "scenes_failed": len(failed),
            "failed_scenes": [r["title"] for r in failed] if failed else [],
            "published": publish_result,
        }

    finally:
        await conn.close()
