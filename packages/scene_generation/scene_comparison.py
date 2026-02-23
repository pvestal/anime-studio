"""Video A/B comparison endpoints — run multiple engines against same source.

Split from router.py for readability.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from packages.core.config import COMFYUI_OUTPUT_DIR
from packages.core.db import connect_direct, log_model_change
from packages.core.audit import log_decision, log_generation, update_generation_quality
from packages.core.models import VideoCompareRequest
from .builder import (
    SCENE_OUTPUT_DIR, extract_last_frame, copy_to_comfyui_input,
    poll_comfyui_completion,
)
from .framepack import build_framepack_workflow, _submit_comfyui_workflow
from .ltx_video import (
    build_ltx_workflow,
    _submit_comfyui_workflow as _submit_ltx_workflow,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_video_compare_task: dict = {}  # single comparison at a time

_ENGINE_LABELS = {
    "framepack": "FramePack (standard)",
    "framepack_f1": "FramePack F1",
    "ltx": "LTX-Video 2B",
    "wan": "Wan 2.1 T2V 1.3B",
}


async def _run_video_compare(request: VideoCompareRequest, image_filename: str):
    """Background coroutine: run each engine sequentially, score results."""
    results = []
    _video_compare_task["status"] = "running"
    _video_compare_task["total"] = len(request.engines)
    _video_compare_task["completed"] = 0
    _video_compare_task["results"] = results

    for i, eng in enumerate(request.engines):
        engine_name = eng.engine
        label = _ENGINE_LABELS.get(engine_name, engine_name)
        _video_compare_task["current_engine"] = label
        entry = {
            "engine": engine_name, "label": label,
            "status": "running", "video_path": None,
            "quality_score": None, "generation_time": None,
            "file_size_mb": None, "error": None,
        }
        results.append(entry)

        try:
            t0 = time.time()

            if engine_name in ("framepack", "framepack_f1"):
                use_f1 = engine_name == "framepack_f1"
                workflow_data, _, prefix = build_framepack_workflow(
                    prompt_text=request.prompt,
                    image_path=image_filename,
                    total_seconds=request.total_seconds,
                    steps=eng.steps,
                    use_f1=use_f1,
                    seed=eng.seed,
                    negative_text=request.negative_prompt,
                    gpu_memory_preservation=eng.gpu_memory_preservation,
                )
                prompt_id = _submit_comfyui_workflow(workflow_data["prompt"])

            elif engine_name == "ltx":
                fps = 24
                num_frames = max(9, int(request.total_seconds * fps) + 1)
                workflow, prefix = build_ltx_workflow(
                    prompt_text=request.prompt,
                    steps=eng.steps,
                    seed=eng.seed,
                    negative_text=request.negative_prompt,
                    image_path=image_filename,
                    num_frames=num_frames,
                    fps=fps,
                    lora_name=eng.lora_name,
                    lora_strength=eng.lora_strength,
                )
                prompt_id = _submit_ltx_workflow(workflow)

            else:
                entry["status"] = "error"
                entry["error"] = f"Unknown engine: {engine_name}"
                _video_compare_task["completed"] = i + 1
                continue

            gen_id = await log_generation(
                character_slug=request.character_slug,
                project_name=request.project_name,
                comfyui_prompt_id=prompt_id,
                generation_type="video",
                checkpoint_model=engine_name,
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                seed=eng.seed,
                steps=eng.steps,
            )
            entry["generation_history_id"] = gen_id

            poll_result = await poll_comfyui_completion(prompt_id)
            gen_time = round(time.time() - t0, 1)
            entry["generation_time"] = gen_time

            if poll_result["status"] == "completed" and poll_result.get("output_files"):
                video_path = str(COMFYUI_OUTPUT_DIR / poll_result["output_files"][0])
                entry["video_path"] = video_path
                entry["status"] = "completed"

                if os.path.exists(video_path):
                    entry["file_size_mb"] = round(os.path.getsize(video_path) / (1024 * 1024), 2)

                # Multi-frame QC review (comparative against source image)
                try:
                    from .video_qc import extract_review_frames, review_video_frames
                    last_frame = await extract_last_frame(video_path)
                    frames = await extract_review_frames(video_path, count=3)
                    if frames:
                        review = await review_video_frames(
                            frames, request.prompt, request.character_slug,
                            source_image_path=request.source_image_path,
                        )
                        entry["quality_score"] = review["overall_score"]
                        entry["qc_issues"] = review.get("issues", [])
                        entry["category_averages"] = review.get("category_averages", {})
                    elif last_frame:
                        from .video_qc import _vision_review_single_frame
                        result = await _vision_review_single_frame(
                            last_frame, request.prompt, request.character_slug,
                            source_image_path=request.source_image_path,
                        )
                        raw = sum(result[k] for k in ("character_match", "style_match", "motion_execution", "technical_quality")) / 4
                        entry["quality_score"] = round((raw - 1) / 9, 2)
                except Exception as e:
                    logger.warning(f"Quality scoring failed for {engine_name}: {e}")

                if gen_id:
                    await update_generation_quality(
                        gen_id=gen_id,
                        quality_score=entry["quality_score"] or 0,
                        status="completed",
                        artifact_path=video_path,
                    )
                    try:
                        from packages.core.db import get_pool
                        pool = await get_pool()
                        async with pool.acquire() as conn:
                            await conn.execute(
                                "UPDATE generation_history SET video_engine = $2, "
                                "generation_time_ms = $3 WHERE id = $1",
                                gen_id, engine_name, int(gen_time * 1000),
                            )
                    except Exception as e:
                        logger.warning(f"Failed to set video_engine on gen {gen_id}: {e}")

            else:
                entry["status"] = "failed"
                entry["error"] = f"ComfyUI returned: {poll_result['status']}"
                if gen_id:
                    await update_generation_quality(
                        gen_id=gen_id, quality_score=0, status="failed",
                    )

        except Exception as e:
            entry["status"] = "error"
            entry["error"] = str(e)
            logger.error(f"Video compare engine {engine_name} failed: {e}")

        _video_compare_task["completed"] = i + 1

    scored = [r for r in results if r["quality_score"] is not None]
    scored.sort(key=lambda r: (-r["quality_score"], r["generation_time"] or 9999))
    for rank, r in enumerate(scored, 1):
        r["rank"] = rank

    _video_compare_task["status"] = "completed"
    _video_compare_task["current_engine"] = None
    _video_compare_task["finished_at"] = datetime.now().isoformat()

    try:
        summary = {
            "engines": [r["engine"] for r in results],
            "scores": {r["engine"]: r["quality_score"] for r in results},
            "times": {r["engine"]: r["generation_time"] for r in results},
            "winner": scored[0]["engine"] if scored else None,
        }
        await log_model_change(
            action="video_compare",
            checkpoint_model=scored[0]["engine"] if scored else "none",
            project_name=request.project_name,
            reason=json.dumps(summary),
        )
        await log_decision(
            decision_type="video_compare",
            character_slug=request.character_slug,
            project_name=request.project_name,
            input_context={"prompt": request.prompt, "engines": [e.engine for e in request.engines]},
            decision_made=f"Winner: {scored[0]['engine']}" if scored else "No valid results",
            confidence_score=scored[0]["quality_score"] if scored else 0,
            reasoning=f"Compared {len(request.engines)} engines, ranked by quality then speed",
        )
    except Exception as e:
        logger.warning(f"Failed to log video compare results: {e}")


@router.post("/scenes/video-compare")
async def start_video_compare(body: VideoCompareRequest):
    """Start a video engine A/B comparison (background task)."""
    if _video_compare_task.get("status") == "running":
        raise HTTPException(status_code=409, detail="A video comparison is already running")

    if not body.engines or len(body.engines) > 5:
        raise HTTPException(status_code=400, detail="Provide 1-5 engine configs")

    valid_engines = set(_ENGINE_LABELS.keys())
    for eng in body.engines:
        if eng.engine not in valid_engines:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown engine '{eng.engine}'. Valid: {sorted(valid_engines)}",
            )

    src = Path(body.source_image_path)
    if not src.exists():
        raise HTTPException(status_code=400, detail=f"Source image not found: {body.source_image_path}")

    image_filename = await copy_to_comfyui_input(body.source_image_path)

    _video_compare_task.clear()
    _video_compare_task["status"] = "starting"
    _video_compare_task["started_at"] = datetime.now().isoformat()
    _video_compare_task["request"] = {
        "prompt": body.prompt,
        "source_image": body.source_image_path,
        "total_seconds": body.total_seconds,
        "engines": [e.engine for e in body.engines],
    }

    asyncio.create_task(_run_video_compare(body, image_filename))

    return {
        "message": "Video comparison started",
        "engines": [{"engine": e.engine, "label": _ENGINE_LABELS.get(e.engine, e.engine)} for e in body.engines],
        "total_engines": len(body.engines),
        "poll_url": "/api/scenes/video-compare/status",
    }


@router.get("/scenes/video-compare/status")
async def get_video_compare_status():
    """Poll video comparison progress."""
    if not _video_compare_task:
        return {"status": "idle", "message": "No comparison running or completed"}

    return {
        "status": _video_compare_task.get("status", "unknown"),
        "total": _video_compare_task.get("total", 0),
        "completed": _video_compare_task.get("completed", 0),
        "current_engine": _video_compare_task.get("current_engine"),
        "started_at": _video_compare_task.get("started_at"),
        "finished_at": _video_compare_task.get("finished_at"),
        "results": [
            {k: v for k, v in r.items()}
            for r in _video_compare_task.get("results", [])
        ],
    }


@router.get("/scenes/video-compare/results")
async def get_video_compare_results():
    """Get ranked video comparison results (only available after completion)."""
    if not _video_compare_task:
        raise HTTPException(status_code=404, detail="No comparison data available")

    if _video_compare_task.get("status") != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Comparison is {_video_compare_task.get('status', 'unknown')}, not yet completed",
        )

    results = _video_compare_task.get("results", [])
    ranked = sorted(
        [r for r in results if r.get("quality_score") is not None],
        key=lambda r: (-r["quality_score"], r.get("generation_time") or 9999),
    )
    failed = [r for r in results if r.get("quality_score") is None]

    return {
        "status": "completed",
        "started_at": _video_compare_task.get("started_at"),
        "finished_at": _video_compare_task.get("finished_at"),
        "request": _video_compare_task.get("request"),
        "ranked": ranked,
        "failed": failed,
        "winner": ranked[0] if ranked else None,
    }
