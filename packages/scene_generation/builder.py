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
                review_status = "approved" if best_quality >= 0.75 else "pending_review"
                await conn.execute("""
                    UPDATE shots SET status = $2, output_video_path = $3,
                           last_frame_path = $4, generation_time_seconds = $5,
                           quality_score = $6, review_status = $7
                    WHERE id = $1
                """, shot_id, shot_status, best_video, best_last_frame,
                    gen_time, best_quality, review_status)
            else:
                await conn.execute(
                    "UPDATE shots SET status = 'failed', error_message = 'All attempts failed' WHERE id = $1",
                    shot_id,
                )

            await conn.execute(
                "UPDATE scenes SET completed_shots = $2 WHERE id = $1",
                scene_id, completed_count,
            )

        # Assemble final video with crossfade transitions
        if completed_videos:
            scene_video_path = str(SCENE_OUTPUT_DIR / f"scene_{scene_id}.mp4")
            try:
                # Read transition settings from completed shots
                transitions = []
                for shot in shots[1:]:  # transitions between pairs, so skip first
                    transitions.append({
                        "type": shot.get("transition_type", "dissolve") or "dissolve",
                        "duration": float(shot.get("transition_duration", 0.3) or 0.3),
                    })
                await concat_videos(completed_videos, scene_video_path, transitions=transitions)

                # Optional post-processing: frame interpolation then upscaling
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

                final_status = "completed" if completed_count == len(shots) else "partial"
                await conn.execute("""
                    UPDATE scenes SET generation_status = $2, final_video_path = $3,
                           actual_duration_seconds = $4, current_generating_shot_id = NULL
                    WHERE id = $1
                """, scene_id, final_status, scene_video_path, duration)
            except Exception as e:
                logger.error(f"Scene assembly failed: {e}")
                await conn.execute(
                    "UPDATE scenes SET generation_status = 'partial', current_generating_shot_id = NULL WHERE id = $1",
                    scene_id,
                )
        else:
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
