"""Scene builder helper functions — ComfyUI polling, generation orchestrator, and re-exports.

Video utilities split into scene_video_utils.py.
Audio functions split into scene_audio.py.
All original exports remain available from this module.
"""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

from packages.core.config import BASE_PATH, COMFYUI_URL, COMFYUI_OUTPUT_DIR, COMFYUI_INPUT_DIR
from packages.core.db import connect_direct
from packages.core.audit import log_decision

from .framepack import build_framepack_workflow, _submit_comfyui_workflow
from .ltx_video import build_ltx_workflow, _submit_comfyui_workflow as _submit_ltx_workflow
from .wan_video import build_wan_t2v_workflow, _submit_comfyui_workflow as _submit_wan_workflow
from .image_recommender import recommend_for_scene, batch_read_metadata

# Re-export from sub-modules so existing imports keep working
from .scene_video_utils import (  # noqa: F401
    extract_last_frame,
    _probe_duration,
    concat_videos,
    _concat_videos_hardcut,
    interpolate_video,
    upscale_video,
)
from .scene_audio import (  # noqa: F401
    ACE_STEP_URL,
    MUSIC_CACHE,
    AUDIO_CACHE_DIR,
    download_preview,
    overlay_audio,
    mix_scene_audio,
    build_scene_dialogue,
    _auto_generate_scene_music,
    apply_scene_audio,
)

logger = logging.getLogger(__name__)

# Scene output directory (canonical location — also set in scene_audio.py)
SCENE_OUTPUT_DIR = BASE_PATH.parent / "output" / "scenes"
SCENE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Track active scene generation tasks
_scene_generation_tasks: dict[str, asyncio.Task] = {}

# Semaphore: only 1 scene generates at a time (GPU memory constraint)
_scene_generation_lock = asyncio.Semaphore(1)



async def _assemble_scene(conn, scene_id, video_paths: list[str] | None = None, shots=None):
    """Assemble approved shot videos into final scene with transitions + audio.

    Called after all shots are approved (either auto or manual).
    If video_paths/shots not provided, fetches approved shots from DB.
    """
    scene_video_path = str(SCENE_OUTPUT_DIR / f"scene_{scene_id}.mp4")
    try:
        # Fetch shots + video paths from DB if not provided
        if shots is None or video_paths is None:
            shots = await conn.fetch(
                "SELECT * FROM shots WHERE scene_id = $1 AND review_status = 'approved' "
                "ORDER BY shot_number", scene_id,
            )
            video_paths = [s["output_video_path"] for s in shots if s["output_video_path"]]

        if not video_paths:
            logger.warning(f"Scene {scene_id}: no approved videos to assemble")
            return

        transitions = []
        for shot in (shots[1:] if len(shots) > 1 else []):
            t_type = shot["transition_type"] if "transition_type" in shot.keys() else "dissolve"
            t_dur = shot["transition_duration"] if "transition_duration" in shot.keys() else 0.3
            transitions.append({
                "type": t_type or "dissolve",
                "duration": float(t_dur or 0.3),
            })
        await concat_videos(video_paths, scene_video_path, transitions=transitions)

        # Optional post-processing
        scene_meta = await conn.fetchrow(
            "SELECT post_interpolate_fps, post_upscale_factor FROM scenes WHERE id = $1",
            scene_id,
        )
        if scene_meta:
            interp_fps = scene_meta["post_interpolate_fps"]
            if interp_fps and interp_fps > 30:
                interp_path = scene_video_path.rsplit(".", 1)[0] + f"_{interp_fps}fps.mp4"
                result_path = await interpolate_video(
                    scene_video_path, interp_path, target_fps=interp_fps
                )
                if result_path != scene_video_path:
                    os.replace(result_path, scene_video_path)

            upscale_factor = scene_meta["post_upscale_factor"]
            if upscale_factor and upscale_factor > 1:
                upscale_path = scene_video_path.rsplit(".", 1)[0] + f"_{upscale_factor}x.mp4"
                result_path = await upscale_video(
                    scene_video_path, upscale_path, scale_factor=upscale_factor
                )
                if result_path != scene_video_path:
                    os.replace(result_path, scene_video_path)

        # Apply audio (dialogue + music) — non-fatal wrapper
        await apply_scene_audio(conn, scene_id, scene_video_path)

        # Get duration
        probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", scene_video_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await probe.communicate()
        duration = float(stdout.decode().strip()) if stdout.decode().strip() else None

        await conn.execute("""
            UPDATE scenes SET generation_status = 'completed', final_video_path = $2,
                   actual_duration_seconds = $3, current_generating_shot_id = NULL
            WHERE id = $1
        """, scene_id, scene_video_path, duration)

        logger.info(f"Scene {scene_id}: assembled {len(video_paths)} shots → {scene_video_path} ({duration:.1f}s)")
    except Exception as e:
        logger.error(f"Scene assembly failed: {e}")
        await conn.execute(
            "UPDATE scenes SET generation_status = 'assembly_failed', current_generating_shot_id = NULL WHERE id = $1",
            scene_id,
        )


async def assemble_approved_scene(scene_id) -> dict:
    """Public entry point — assemble a scene if all shots are approved.

    Called by the review endpoint when the last shot gets approved.
    Returns status dict.
    """
    conn = await connect_direct()
    try:
        counts = await conn.fetchrow("""
            SELECT COUNT(*) as total,
                   COUNT(*) FILTER (WHERE review_status = 'approved') as approved,
                   COUNT(*) FILTER (WHERE output_video_path IS NOT NULL) as with_video
            FROM shots WHERE scene_id = $1
        """, scene_id)

        if counts["approved"] < counts["total"]:
            return {
                "assembled": False,
                "reason": f"{counts['approved']}/{counts['total']} shots approved",
            }

        if counts["with_video"] < counts["total"]:
            return {
                "assembled": False,
                "reason": f"{counts['with_video']}/{counts['total']} shots have video",
            }

        await _assemble_scene(conn, scene_id)
        return {"assembled": True, "scene_id": str(scene_id)}
    finally:
        await conn.close()


async def copy_to_comfyui_input(image_path: str) -> str:
    """Copy source image to ComfyUI input dir, return the filename."""
    src = Path(image_path)
    if not src.is_absolute():
        src = BASE_PATH / image_path
    dest = COMFYUI_INPUT_DIR / src.name
    if not dest.exists():
        shutil.copy2(str(src), str(dest))
    return src.name


async def poll_comfyui_completion(prompt_id: str, timeout_seconds: int = 1800) -> dict:
    """Poll ComfyUI /history until the prompt completes or times out."""
    import urllib.request
    import time as _time
    start = _time.time()
    while (_time.time() - start) < timeout_seconds:
        try:
            req = urllib.request.Request(f"{COMFYUI_URL}/history/{prompt_id}")
            resp = urllib.request.urlopen(req, timeout=10)
            history = json.loads(resp.read())
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                videos = []
                for node_output in outputs.values():
                    for key in ("videos", "gifs", "images"):
                        for item in node_output.get(key, []):
                            fn = item.get("filename")
                            if fn:
                                videos.append(fn)
                return {"status": "completed", "output_files": videos}
        except Exception:
            pass
        await asyncio.sleep(5)
    return {"status": "timeout", "output_files": []}


async def recover_interrupted_generations():
    """On startup, find shots stuck in 'generating' and re-queue their scenes.

    Orderly: waits for ComfyUI, resets stuck shots to pending,
    then re-triggers scene generation one at a time via existing lock.
    """
    conn = await connect_direct()
    try:
        # 1. Find all stuck shots (status = 'generating')
        stuck = await conn.fetch("""
            SELECT sh.id, sh.scene_id, s.title, s.project_id
            FROM shots sh
            JOIN scenes s ON sh.scene_id = s.id
            WHERE sh.status = 'generating'
        """)
        if not stuck:
            logger.info("Recovery: no stuck shots found")
            return

        logger.warning(f"Recovery: found {len(stuck)} stuck shot(s) in 'generating' state")

        # 2. Collect unique scene IDs (preserve order)
        scene_ids = list(dict.fromkeys(row["scene_id"] for row in stuck))

        # 3. Reset stuck shots to pending
        reset_count = await conn.execute("""
            UPDATE shots SET status = 'pending', error_message = 'reset by startup recovery'
            WHERE status = 'generating'
        """)
        logger.info(f"Recovery: reset {reset_count} shot(s) to pending")

        # 4. Reset their scenes' generation_status and current_generating_shot_id
        for sid in scene_ids:
            await conn.execute("""
                UPDATE scenes SET generation_status = 'pending',
                       current_generating_shot_id = NULL
                WHERE id = $1 AND generation_status = 'generating'
            """, sid)

        # 5. Wait for ComfyUI to be reachable before re-queuing
        import urllib.request
        comfyui_ready = False
        for attempt in range(30):  # up to 30 x 2s = 60s
            try:
                req = urllib.request.Request(f"{COMFYUI_URL}/system_stats")
                urllib.request.urlopen(req, timeout=5)
                comfyui_ready = True
                break
            except Exception:
                await asyncio.sleep(2)

        if not comfyui_ready:
            logger.error("Recovery: ComfyUI not reachable after 60s, skipping re-queue")
            return

        # 6. Re-queue each scene via existing generate_scene() (uses _scene_generation_lock)
        for sid in scene_ids:
            scene_title = next((r["title"] for r in stuck if r["scene_id"] == sid), "?")
            logger.info(f"Recovery: re-queuing scene '{scene_title}' ({sid})")
            task = asyncio.create_task(generate_scene(str(sid)))
            _scene_generation_tasks[str(sid)] = task

        logger.info(f"Recovery: re-queued {len(scene_ids)} scene(s) for generation")
    finally:
        await conn.close()


async def generate_scene(scene_id: str):
    """Background task: generate all shots sequentially with continuity chaining.

    Uses _scene_generation_lock to ensure only one scene generates at a time,
    so scenes complete fully (all shots in order) before the next scene starts.
    """
    await _scene_generation_lock.acquire()
    try:
        await _generate_scene_impl(scene_id)
    finally:
        _scene_generation_lock.release()


async def ensure_source_images(conn, scene_id: str, shots: list) -> int:
    """Auto-assign best source images to shots that have NULL source_image_path.

    Uses the image recommender to score and rank approved images per character.
    Skips shots using text-only engines (wan).

    Returns the number of shots that were auto-assigned.
    """
    null_shots = [
        s for s in shots
        if not s["source_image_path"]
        and (s.get("video_engine") or "framepack") != "wan"
    ]
    if not null_shots:
        return 0

    # Build approved image map from approval_status.json
    all_slugs: set[str] = set()
    for shot in null_shots:
        chars = shot.get("characters_present")
        if chars and isinstance(chars, list):
            all_slugs.update(chars)

    if not all_slugs:
        logger.warning(f"Scene {scene_id}: shots need source images but no characters_present set")
        return 0

    approved: dict[str, list[str]] = {}
    for slug in all_slugs:
        approval_file = BASE_PATH / slug / "approval_status.json"
        images_dir = BASE_PATH / slug / "images"
        if not images_dir.exists():
            continue
        if approval_file.exists():
            try:
                with open(approval_file) as f:
                    statuses = json.load(f)
                imgs = [
                    name for name, st in statuses.items()
                    if (st == "approved" or (isinstance(st, dict) and st.get("status") == "approved"))
                    and (images_dir / name).exists()
                ]
                if imgs:
                    approved[slug] = sorted(imgs)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read approval_status.json for {slug}: {e}")

    if not approved:
        # Mark all null shots as failed — no images available
        for shot in null_shots:
            await conn.execute(
                "UPDATE shots SET status = 'failed', "
                "error_message = 'No approved images available for auto-assignment' "
                "WHERE id = $1", shot["id"],
            )
        logger.error(f"Scene {scene_id}: no approved images for any character — {len(null_shots)} shots failed")
        return 0

    # Batch-fetch video effectiveness scores (one query per character, not per image)
    video_scores: dict[str, dict[str, float]] = {}
    for slug in all_slugs:
        try:
            rows = await conn.fetch(
                "SELECT image_name, AVG(video_quality_score) as avg_score "
                "FROM source_image_effectiveness "
                "WHERE character_slug = $1 AND video_quality_score IS NOT NULL "
                "GROUP BY image_name",
                slug,
            )
            if rows:
                video_scores[slug] = {r["image_name"]: float(r["avg_score"]) for r in rows}
        except Exception as e:
            logger.debug(f"Video effectiveness lookup for {slug}: {e}")

    # Build shot dicts for recommender (include motion_prompt for description matching)
    shot_list = [{
        "id": str(s["id"]),
        "shot_number": s["shot_number"],
        "shot_type": s["shot_type"],
        "camera_angle": s["camera_angle"],
        "characters_present": s["characters_present"] or [],
        "source_image_path": s["source_image_path"],
        "motion_prompt": s.get("motion_prompt"),
    } for s in shots]  # Pass ALL shots for diversity tracking

    recommendations = recommend_for_scene(
        BASE_PATH, shot_list, approved, top_n=1, video_scores=video_scores,
    )

    assigned_count = 0
    for rec in recommendations:
        shot_id = rec["shot_id"]
        # Only assign to shots that actually need it
        if rec["current_source"]:
            continue
        top_recs = rec.get("recommendations", [])
        if not top_recs:
            # No recommendation available for this shot's character
            await conn.execute(
                "UPDATE shots SET status = 'failed', "
                "error_message = 'No approved images for character(s) in this shot' "
                "WHERE id = $1", shot_id,
            )
            continue

        best = top_recs[0]
        image_path = f"{best['slug']}/images/{best['image_name']}"

        await conn.execute(
            "UPDATE shots SET source_image_path = $2, source_image_auto_assigned = TRUE WHERE id = $1",
            shot_id, image_path,
        )
        assigned_count += 1

        await log_decision(
            decision_type="source_image_auto_assign",
            input_context={
                "shot_id": str(shot_id),
                "scene_id": str(scene_id),
                "character_slug": best["slug"],
                "image_name": best["image_name"],
                "score": best["score"],
                "reason": best["reason"],
            },
            decision_made="auto_assigned",
            confidence_score=best["score"],
            reasoning=f"Auto-assigned {best['image_name']} (score={best['score']:.3f}, {best['reason']})",
        )
        logger.info(
            f"Shot {shot_id}: auto-assigned {image_path} "
            f"(score={best['score']:.3f}, {best['reason']})"
        )

    if assigned_count:
        logger.info(f"Scene {scene_id}: auto-assigned source images for {assigned_count}/{len(null_shots)} shots")

    return assigned_count


async def _get_continuity_frame(conn, project_id: int, character_slug: str, current_scene_id) -> str | None:
    """Look up the most recent generated frame for this character from a prior scene.

    Returns the frame path if it exists and the file is on disk, else None.
    Only returns frames from OTHER scenes (not the current one) to avoid
    self-referencing within the same scene's shot loop.
    """
    row = await conn.fetchrow("""
        SELECT frame_path FROM character_continuity_frames
        WHERE project_id = $1 AND character_slug = $2 AND scene_id != $3
    """, project_id, character_slug, current_scene_id)
    if row and row["frame_path"] and Path(row["frame_path"]).exists():
        return row["frame_path"]
    return None


async def _save_continuity_frame(
    conn, project_id: int, character_slug: str,
    scene_id, shot_id, frame_path: str,
    scene_number: int | None = None, shot_number: int | None = None,
):
    """Save/update the most recent frame for a character in this project.

    Uses UPSERT — one row per (project_id, character_slug), always the latest.
    """
    await conn.execute("""
        INSERT INTO character_continuity_frames
            (project_id, character_slug, scene_id, shot_id, frame_path,
             scene_number, shot_number, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, now())
        ON CONFLICT (project_id, character_slug) DO UPDATE SET
            scene_id = EXCLUDED.scene_id,
            shot_id = EXCLUDED.shot_id,
            frame_path = EXCLUDED.frame_path,
            scene_number = EXCLUDED.scene_number,
            shot_number = EXCLUDED.shot_number,
            created_at = now()
    """, project_id, character_slug, scene_id, shot_id, frame_path,
         scene_number, shot_number)


async def _generate_scene_impl(scene_id: str):
    """Inner implementation — do not call directly, use generate_scene()."""
    import time as _time
    conn = None
    try:
        conn = await connect_direct()

        shots = await conn.fetch(
            "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number",
            scene_id,
        )
        if not shots:
            await conn.execute(
                "UPDATE scenes SET generation_status = 'failed' WHERE id = $1", scene_id
            )
            return

        # Get project_id and scene_number for continuity tracking
        scene_row = await conn.fetchrow(
            "SELECT project_id, scene_number FROM scenes WHERE id = $1", scene_id
        )
        project_id = scene_row["project_id"] if scene_row else None
        scene_number = scene_row["scene_number"] if scene_row else None

        await conn.execute(
            "UPDATE scenes SET generation_status = 'generating', total_shots = $2 WHERE id = $1",
            scene_id, len(shots),
        )

        # Auto-assign source images for shots that don't have one
        auto_assigned = await ensure_source_images(conn, scene_id, shots)
        if auto_assigned:
            # Re-fetch shots to get updated source_image_path values
            shots = await conn.fetch(
                "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number",
                scene_id,
            )

        completed_videos = []
        completed_count = 0
        prev_last_frame = None
        prev_character = None

        for shot in shots:
            shot_id = shot["id"]

            # Skip already-completed shots (e.g., after a service restart)
            if (shot["status"] in ("completed", "accepted_best")
                    and shot["output_video_path"]
                    and Path(shot["output_video_path"]).exists()):
                completed_videos.append(shot["output_video_path"])
                completed_count += 1
                prev_last_frame = shot["last_frame_path"]
                skip_chars = shot.get("characters_present")
                prev_character = skip_chars[0] if skip_chars and isinstance(skip_chars, list) else None
                # Backfill continuity frame from already-completed shots
                if prev_character and prev_last_frame and project_id:
                    try:
                        await _save_continuity_frame(
                            conn, project_id, prev_character,
                            scene_id, shot_id, prev_last_frame,
                            scene_number=scene_number,
                            shot_number=shot.get("shot_number"),
                        )
                    except Exception:
                        pass
                logger.info(f"Shot {shot_id}: already completed, skipping")
                continue

            await conn.execute(
                "UPDATE shots SET status = 'generating' WHERE id = $1", shot_id
            )
            await conn.execute(
                "UPDATE scenes SET current_generating_shot_id = $2 WHERE id = $1",
                scene_id, shot_id,
            )

            # Single-pass generation — no QC vision review, all shots go to manual review
            try:
                from .video_qc import check_engine_blacklist
                from .framepack import build_framepack_workflow, _submit_comfyui_workflow
                from .ltx_video import build_ltx_workflow, _submit_comfyui_workflow as _submit_ltx_workflow
                from .wan_video import build_wan_t2v_workflow, _submit_comfyui_workflow as _submit_wan_workflow
                import time as _time_inner

                shot_dict = dict(shot)
                shot_engine = shot_dict.get("video_engine") or "framepack"
                character_slug = None
                chars = shot_dict.get("characters_present")
                if chars and isinstance(chars, list) and len(chars) > 0:
                    character_slug = chars[0]

                # Engine blacklist check
                if character_slug:
                    project_id = None
                    try:
                        scene_row = await conn.fetchrow("SELECT project_id FROM scenes WHERE id = $1", scene_id)
                        if scene_row:
                            project_id = scene_row["project_id"]
                    except Exception:
                        pass
                    bl = await check_engine_blacklist(conn, character_slug, project_id, shot_engine)
                    if bl:
                        logger.warning(f"Shot {shot_id}: engine '{shot_engine}' blacklisted for '{character_slug}'")
                        await conn.execute(
                            "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                            shot_id, f"Engine '{shot_engine}' blacklisted: {bl.get('reason', '')}",
                        )
                        continue

                # Build identity-anchored prompt
                motion_prompt = shot_dict["motion_prompt"] or shot_dict.get("generation_prompt") or ""
                current_prompt = motion_prompt
                if character_slug and shot_engine in ("framepack", "framepack_f1"):
                    try:
                        char_row = await conn.fetchrow(
                            "SELECT design_prompt FROM characters "
                            "WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1",
                            character_slug,
                        )
                        if char_row and char_row["design_prompt"]:
                            design = char_row["design_prompt"].strip().rstrip(",. ")
                            current_prompt = f"{design}, {motion_prompt}, consistent character appearance"
                            logger.info(f"Shot {shot_id}: identity-anchored prompt for '{character_slug}'")
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: design_prompt lookup failed: {e}")

                current_negative = "low quality, blurry, distorted, watermark"
                shot_steps = shot_dict.get("steps") or 25
                shot_guidance = shot_dict.get("guidance_scale") or 6.0
                shot_seconds = float(shot_dict.get("duration_seconds") or 3)
                shot_use_f1 = shot_dict.get("use_f1") or False
                shot_seed = shot_dict.get("seed")

                # Determine first frame source — priority order:
                # 1. Previous shot's last frame (same character, same scene) — intra-scene continuity
                # 2. Cross-scene continuity frame (same character, prior scene) — inter-scene continuity
                # 3. Auto-assigned source image from approved pool — cold start
                same_char_prev_shot = (
                    prev_last_frame
                    and prev_character
                    and character_slug == prev_character
                    and Path(prev_last_frame).exists()
                )
                if same_char_prev_shot:
                    # Priority 1: chain from previous shot in this scene
                    first_frame_path = prev_last_frame
                    image_filename = await copy_to_comfyui_input(first_frame_path)
                    logger.info(f"Shot {shot_id}: continuity chain from previous shot (same character: {character_slug})")
                else:
                    # Priority 2: check for cross-scene continuity frame
                    cross_scene_frame = None
                    if character_slug and project_id:
                        cross_scene_frame = await _get_continuity_frame(
                            conn, project_id, character_slug, scene_id
                        )

                    if cross_scene_frame:
                        first_frame_path = cross_scene_frame
                        image_filename = await copy_to_comfyui_input(first_frame_path)
                        logger.info(
                            f"Shot {shot_id}: cross-scene continuity frame for '{character_slug}' "
                            f"(from prior scene)"
                        )
                    else:
                        # Priority 3: fall back to auto-assigned source image
                        source_path = shot_dict.get("source_image_path")
                        if not source_path:
                            logger.error(f"Shot {shot_id}: no source image and no continuity frame available")
                            await conn.execute(
                                "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                                shot_id, "No source image available (auto-assignment failed or no characters_present)")
                            continue
                        image_filename = await copy_to_comfyui_input(source_path)
                        first_frame_path = str(BASE_PATH / source_path) if not Path(source_path).is_absolute() else source_path
                        if prev_character and character_slug != prev_character:
                            logger.info(f"Shot {shot_id}: character switch {prev_character} → {character_slug}, using source image")

                attempt_start = _time_inner.time()

                # Dispatch to video engine
                if shot_engine == "wan":
                    fps = 16
                    num_frames = max(9, int(shot_seconds * fps) + 1)
                    workflow, prefix = build_wan_t2v_workflow(
                        prompt_text=current_prompt, num_frames=num_frames, fps=fps,
                        steps=shot_steps, seed=shot_seed, use_gguf=True,
                    )
                    comfyui_prompt_id = _submit_wan_workflow(workflow)
                elif shot_engine == "ltx":
                    fps = 24
                    num_frames = max(9, int(shot_seconds * fps) + 1)
                    workflow, prefix = build_ltx_workflow(
                        prompt_text=current_prompt,
                        image_path=image_filename if image_filename else None,
                        num_frames=num_frames, fps=fps, steps=shot_steps,
                        seed=shot_seed,
                        lora_name=shot_dict.get("lora_name"),
                        lora_strength=shot_dict.get("lora_strength", 0.8),
                    )
                    comfyui_prompt_id = _submit_ltx_workflow(workflow)
                else:
                    use_f1 = shot_engine == "framepack_f1" or shot_use_f1
                    workflow_data, sampler_node_id, prefix = build_framepack_workflow(
                        prompt_text=current_prompt, image_path=image_filename,
                        total_seconds=shot_seconds, steps=shot_steps, use_f1=use_f1,
                        seed=shot_seed, negative_text=current_negative,
                        gpu_memory_preservation=6.0, guidance_scale=shot_guidance,
                    )
                    comfyui_prompt_id = _submit_comfyui_workflow(workflow_data["prompt"])

                await conn.execute(
                    "UPDATE shots SET comfyui_prompt_id = $2, first_frame_path = $3 WHERE id = $1",
                    shot_id, comfyui_prompt_id, first_frame_path,
                )

                result = await poll_comfyui_completion(comfyui_prompt_id)
                gen_time = _time_inner.time() - attempt_start

                if result["status"] != "completed" or not result["output_files"]:
                    await conn.execute(
                        "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                        shot_id, f"ComfyUI {result['status']}",
                    )
                    continue

                video_filename = result["output_files"][0]
                video_path = str(COMFYUI_OUTPUT_DIR / video_filename)
                last_frame = await extract_last_frame(video_path)

                # Record source image effectiveness for the feedback loop
                source_path = shot_dict.get("source_image_path")
                if source_path:
                    parts = source_path.replace("\\", "/").split("/")
                    if len(parts) >= 3 and parts[-2] == "images":
                        eff_slug = parts[0] if len(parts) == 3 else parts[-3]
                        try:
                            await conn.execute("""
                                INSERT INTO source_image_effectiveness
                                    (character_slug, image_name, shot_id, video_quality_score, video_engine)
                                VALUES ($1, $2, $3, NULL, $4)
                            """, eff_slug, parts[-1], shot_id, shot_engine)
                        except Exception:
                            pass

                completed_count += 1
                completed_videos.append(video_path)
                prev_last_frame = last_frame
                prev_character = character_slug

                await conn.execute("""
                    UPDATE shots SET status = 'completed', output_video_path = $2,
                           last_frame_path = $3, generation_time_seconds = $4,
                           review_status = 'pending_review'
                    WHERE id = $1
                """, shot_id, video_path, last_frame, gen_time)

                # Save continuity frame for cross-scene reuse
                if character_slug and last_frame and project_id:
                    try:
                        await _save_continuity_frame(
                            conn, project_id, character_slug,
                            scene_id, shot_id, last_frame,
                            scene_number=scene_number,
                            shot_number=shot_dict.get("shot_number"),
                        )
                        logger.info(
                            f"Shot {shot_id}: saved continuity frame for '{character_slug}' "
                            f"(scene {scene_number})"
                        )
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: failed to save continuity frame: {e}")

                logger.info(f"Shot {shot_id}: generated in {gen_time:.0f}s → pending_review")

            except Exception as e:
                logger.error(f"Shot {shot_id} generation failed: {e}")
                await conn.execute(
                    "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                    shot_id, str(e)[:500],
                )

            await conn.execute(
                "UPDATE scenes SET completed_shots = $2 WHERE id = $1",
                scene_id, completed_count,
            )

        # Check if all shots are approved — only then assemble
        all_approved = False
        if completed_videos:
            review_counts = await conn.fetchrow("""
                SELECT COUNT(*) as total,
                       COUNT(*) FILTER (WHERE review_status = 'approved') as approved,
                       COUNT(*) FILTER (WHERE review_status = 'rejected') as rejected,
                       COUNT(*) FILTER (WHERE review_status = 'pending_review') as pending
                FROM shots WHERE scene_id = $1
            """, scene_id)

            all_approved = (
                review_counts["approved"] == review_counts["total"]
                and review_counts["total"] > 0
            )

            if review_counts["pending"] > 0:
                logger.info(
                    f"Scene {scene_id}: {review_counts['pending']} shots awaiting review — "
                    f"assembly deferred until all approved"
                )
                await conn.execute("""
                    UPDATE scenes SET generation_status = 'awaiting_review',
                           current_generating_shot_id = NULL
                    WHERE id = $1
                """, scene_id)
            elif review_counts["rejected"] > 0 and not all_approved:
                logger.info(
                    f"Scene {scene_id}: {review_counts['rejected']} shots rejected — "
                    f"scene needs regeneration of rejected shots"
                )
                await conn.execute("""
                    UPDATE scenes SET generation_status = 'needs_regen',
                           current_generating_shot_id = NULL
                    WHERE id = $1
                """, scene_id)

        if all_approved:
            await _assemble_scene(conn, scene_id, completed_videos, shots)
        elif not completed_videos:
            await conn.execute(
                "UPDATE scenes SET generation_status = 'failed', current_generating_shot_id = NULL WHERE id = $1",
                scene_id,
            )

    except Exception as e:
        logger.error(f"Scene generation task failed: {e}")
        if conn:
            await conn.execute(
                "UPDATE scenes SET generation_status = 'failed', current_generating_shot_id = NULL WHERE id = $1",
                scene_id,
            )
    finally:
        if conn:
            await conn.close()
        _scene_generation_tasks.pop(scene_id, None)
