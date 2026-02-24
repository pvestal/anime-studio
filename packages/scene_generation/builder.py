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

# Progressive quality gate thresholds
# Each retry loosens the gate so we don't loop forever
_QUALITY_GATES = [
    {"threshold": 0.6, "label": "high"},     # Attempt 1: aim high
    {"threshold": 0.45, "label": "medium"},   # Attempt 2: acceptable
    {"threshold": 0.3, "label": "low"},       # Attempt 3: minimum viable
]
_MAX_RETRIES = len(_QUALITY_GATES)
_SHOT_QUALITY_THRESHOLD = _QUALITY_GATES[-1]["threshold"]  # absolute floor

# Video shot auto-review thresholds (loaded from DB, fallback to these)
_DEFAULT_VIDEO_AUTO_APPROVE = 0.65
_DEFAULT_VIDEO_AUTO_REJECT = 0.35


async def _auto_review_shot(conn, quality_score: float) -> str:
    """Determine review_status for a shot based on quality gates from DB.

    Returns: 'approved', 'rejected', or 'pending_review'.
    """
    try:
        approve_row = await conn.fetchrow(
            "SELECT threshold_value FROM quality_gates "
            "WHERE gate_name = 'auto_approve_threshold' AND is_active = true"
        )
        reject_row = await conn.fetchrow(
            "SELECT threshold_value FROM quality_gates "
            "WHERE gate_name = 'auto_reject_threshold' AND is_active = true"
        )
        # Video thresholds are lower than image thresholds — video is harder
        # Use 80% of image thresholds as video thresholds
        approve_thresh = (approve_row["threshold_value"] * 0.8) if approve_row else _DEFAULT_VIDEO_AUTO_APPROVE
        reject_thresh = (reject_row["threshold_value"] * 0.8) if reject_row else _DEFAULT_VIDEO_AUTO_REJECT
    except Exception:
        approve_thresh = _DEFAULT_VIDEO_AUTO_APPROVE
        reject_thresh = _DEFAULT_VIDEO_AUTO_REJECT

    if quality_score >= approve_thresh:
        return "approved"
    elif quality_score < reject_thresh:
        return "rejected"
    return "pending_review"


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

        await conn.execute(
            "UPDATE scenes SET generation_status = 'generating', total_shots = $2 WHERE id = $1",
            scene_id, len(shots),
        )

        completed_videos = []
        completed_count = 0
        prev_last_frame = None

        for shot in shots:
            shot_id = shot["id"]

            # Skip already-completed shots (e.g., after a service restart)
            if (shot["status"] in ("completed", "accepted_best")
                    and shot["output_video_path"]
                    and Path(shot["output_video_path"]).exists()):
                completed_videos.append(shot["output_video_path"])
                completed_count += 1
                prev_last_frame = shot["last_frame_path"]
                logger.info(f"Shot {shot_id}: already completed, skipping")
                continue

            shot_accepted = False
            best_video = None
            best_quality = 0.0
            best_last_frame = None

            await conn.execute(
                "UPDATE shots SET status = 'generating' WHERE id = $1", shot_id
            )
            await conn.execute(
                "UPDATE scenes SET current_generating_shot_id = $2 WHERE id = $1",
                scene_id, shot_id,
            )

            # QC loop: multi-frame review with prompt refinement
            try:
                from .video_qc import run_qc_loop

                # Pass previous shot's last frame for continuity chaining
                shot_dict = dict(shot)
                shot_dict["_prev_last_frame"] = prev_last_frame

                qc_result = await run_qc_loop(
                    shot_data=shot_dict,
                    conn=conn,
                    max_attempts=_MAX_RETRIES,
                    accept_threshold=_QUALITY_GATES[0]["threshold"],
                    min_threshold=_QUALITY_GATES[-1]["threshold"],
                )

                best_video = qc_result.get("video_path")
                best_last_frame = qc_result.get("last_frame_path")
                best_quality = qc_result.get("quality_score", 0.0)
                shot_accepted = qc_result.get("accepted", False)
                gen_time = qc_result.get("generation_time", 0.0)

            except Exception as e:
                logger.error(f"Shot {shot_id} QC loop failed: {e}")
                await conn.execute(
                    "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                    shot_id, str(e)[:500],
                )

            # Use best result even if no attempt fully passed
            if best_video:
                completed_count += 1
                completed_videos.append(best_video)
                prev_last_frame = best_last_frame
                shot_status = "completed" if shot_accepted else "accepted_best"

                # Auto-approve/reject based on quality gates from DB
                review_status = await _auto_review_shot(conn, best_quality)
                await conn.execute("""
                    UPDATE shots SET status = $2, output_video_path = $3,
                           last_frame_path = $4, generation_time_seconds = $5,
                           quality_score = $6, review_status = $7
                    WHERE id = $1
                """, shot_id, shot_status, best_video, best_last_frame,
                    gen_time, best_quality, review_status)
                logger.info(
                    f"Shot {shot_id}: quality={best_quality:.2f} → {review_status}"
                )
            else:
                await conn.execute(
                    "UPDATE shots SET status = 'failed', error_message = 'All attempts failed' WHERE id = $1",
                    shot_id,
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
