"""Shared batch generation — single entry point for all generation callers.

Replaces the subprocess-based path through generate_training_images.py with
in-process calls to the visual pipeline's workflow builder, adding:
- Learned negatives from model_selector.recommend_params()
- Feedback negatives from feedback.get_feedback_negatives()
- Character negatives from build_character_negatives()
- EventBus events + audit logging
- Pose variation from POSE_VARIATIONS

Callers:
    1. POST /regenerate/{slug}  (Characters tab "Generate X More")
    2. queue_regeneration()     (rejection auto-regen)
    3. replenishment._generate_and_review()  (autonomous loop)
"""

import asyncio
import json
import logging
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

from packages.core.config import BASE_PATH, COMFYUI_OUTPUT_DIR, normalize_sampler
from packages.core.db import get_char_project_map, log_model_change
from packages.core.events import event_bus, GENERATION_SUBMITTED
from packages.core.audit import log_generation
from packages.core.model_selector import recommend_params
from packages.core.model_profiles import get_model_profile, translate_prompt
from packages.lora_training.feedback import get_feedback_negatives, register_pending_image
from packages.visual_pipeline.comfyui import (
    build_comfyui_workflow,
    submit_comfyui_workflow,
    get_comfyui_progress,
)

logger = logging.getLogger(__name__)

# --- Concurrency control ---
# Only allow 2 ComfyUI jobs in-flight at once (1 rendering + 1 queued).
# This prevents queue flooding and poll timeouts when multiple generate_batch
# calls run concurrently (e.g. multi-checkpoint comparison).
_comfyui_slot = asyncio.Semaphore(2)

# --- Constants moved from src/generate_training_images.py ---

POSE_VARIATIONS = [
    "standing pose, front view",
    "three-quarter view, confident stance",
    "side profile, looking ahead",
    "upper body portrait, neutral expression",
    "full body, relaxed pose",
    "close-up portrait, detailed face",
    "dynamic pose, action stance",
    "sitting pose, casual",
    "walking pose, slight movement",
    "arms crossed, assertive stance",
    "looking over shoulder, back turned slightly",
    "leaning forward, curious expression",
    "hands on hips, wide stance",
    "crouching pose, low angle",
    "looking up, low camera angle",
    "looking down, high camera angle",
    "running pose, mid-stride",
    "head tilt, playful expression",
    "dramatic lighting, cinematic angle",
    "from behind, looking back",
]


def build_character_negatives(appearance_data) -> str:
    """Build per-character negative prompt terms from appearance_data.

    For non-human characters, adds species-correcting negatives.
    For all characters, converts common_errors into negative terms.
    """
    if not appearance_data:
        return ""

    if isinstance(appearance_data, str):
        try:
            appearance_data = json.loads(appearance_data)
        except (json.JSONDecodeError, TypeError):
            return ""

    negatives = []
    species = appearance_data.get("species", "")

    if "NOT human" in species:
        negatives.extend(["human", "human face", "human skin", "realistic person",
                          "humanoid body", "human proportions"])

    if "star-shaped" in species.lower():
        negatives.extend(["child", "boy", "girl", "humanoid", "arms", "legs",
                          "human child", "toddler"])

    if "mushroom" in species.lower():
        negatives.extend(["human child", "boy wearing hat", "normal human head"])

    for err in appearance_data.get("common_errors", []):
        err_lower = err.lower()
        if "letter m" in err_lower and "instead of l" in err_lower:
            negatives.append("letter M on cap")
        if "depicted as child" in err_lower or "generates as human child" in err_lower:
            negatives.extend(["child", "teenager", "young boy"])
        if "too short" in err_lower or "too stocky" in err_lower:
            negatives.append("short stocky")

    return ", ".join(dict.fromkeys(negatives))  # dedupe preserving order


# --- Main entry point ---

async def _get_style_override(style_name: str) -> dict | None:
    """Fetch a generation style by name from the DB."""
    from packages.core.db import connect_direct
    try:
        conn = await connect_direct()
        row = await conn.fetchrow(
            "SELECT * FROM generation_styles WHERE style_name = $1", style_name
        )
        await conn.close()
        if not row:
            logger.warning(f"style_override '{style_name}' not found in generation_styles")
            return None
        return dict(row)
    except Exception as e:
        logger.error(f"Failed to fetch style '{style_name}': {e}")
        return None


async def generate_batch(
    character_slug: str,
    count: int = 1,
    seed: int | None = None,
    prompt_override: str | None = None,
    pose_variation: bool = True,
    include_feedback_negatives: bool = True,
    include_learned_negatives: bool = True,
    fire_events: bool = True,
    style_override: str | None = None,
    checkpoint_override: str | None = None,
    custom_poses: list[str] | None = None,
) -> list[dict]:
    """Generate N images using the full visual pipeline, poll, copy to dataset, register.

    This is the single shared generation function that all callers use.
    When style_override is provided, overrides checkpoint/cfg/steps/sampler/resolution
    from the named generation_styles row (e.g. "pony_nsfw_xl").
    When checkpoint_override is provided, swaps just the checkpoint model (keeps
    all other params from the project style).
    Returns a list of result dicts, one per submitted job.
    """
    # 1. Get DB info
    char_map = await get_char_project_map()
    db_info = char_map.get(character_slug)
    if not db_info:
        raise ValueError(f"Character '{character_slug}' not found in DB")

    # style_override is deprecated — use checkpoint_override instead.
    # Named styles clobber project-tuned params (resolution, sampler, negatives).
    if style_override:
        logger.warning(
            f"generate_batch: style_override='{style_override}' is DEPRECATED — "
            f"use checkpoint_override instead. Ignoring."
        )

    # Direct checkpoint swap — use profile defaults instead of DB project params
    # (DB params are tuned for the project's default checkpoint, not the override)
    using_override = bool(checkpoint_override)
    if checkpoint_override:
        original_checkpoint = db_info.get("checkpoint_model")
        db_info["checkpoint_model"] = checkpoint_override
        logger.info(f"generate_batch: checkpoint_override -> {checkpoint_override}")
        await log_model_change(
            action="override",
            checkpoint_model=checkpoint_override,
            previous_model=original_checkpoint,
            project_name=db_info.get("project_name"),
            reason=f"generate_batch checkpoint_override for {character_slug}",
            metadata={"character_slug": character_slug, "count": count},
        )

    checkpoint = db_info.get("checkpoint_model")
    if not checkpoint:
        raise ValueError(f"No checkpoint model configured for {character_slug}")

    project_name = db_info.get("project_name")
    design_prompt = prompt_override or db_info.get("design_prompt", "")

    # 2. Get model profile for checkpoint-aware pipeline
    profile = get_model_profile(
        checkpoint,
        db_architecture=db_info.get("model_architecture"),
        db_prompt_format=db_info.get("prompt_format"),
    )
    logger.info(f"generate_batch: using profile '{profile['style_label']}' for {checkpoint}")

    # 3. Build negative prompt: profile defaults > DB template, + learned + feedback + character
    # When checkpoint_override is used, always use profile negatives (DB negatives may use
    # wrong tags e.g. score_1 for PonyXL won't work on NoobAI)
    if using_override:
        base_negative = profile["quality_negative"]
    else:
        base_negative = (
            db_info.get("negative_prompt_template")
            or profile["quality_negative"]
        )

    # Get recommendations and apply if confidence >= medium
    # When checkpoint_override is active, start from profile defaults not DB values
    if using_override:
        use_cfg = None
        use_steps = None
        use_sampler = None
        use_scheduler = None
    else:
        use_cfg = db_info.get("cfg_scale")
        use_steps = db_info.get("steps")
        use_sampler = db_info.get("sampler")
        use_scheduler = db_info.get("scheduler")

    if include_learned_negatives:
        try:
            rec = await recommend_params(
                character_slug, project_name=project_name,
                checkpoint_model=checkpoint,
            )
            learned_neg = rec.get("learned_negatives", "")
            if learned_neg:
                base_negative = f"{base_negative}, {learned_neg}"
                logger.info(f"generate_batch: added learned negatives for {character_slug}")

            # Apply recommended params when confidence >= medium
            if rec.get("confidence") in ("medium", "high"):
                if rec.get("cfg_scale") and not style_override:
                    use_cfg = rec["cfg_scale"]
                if rec.get("steps") and not style_override:
                    use_steps = rec["steps"]
                if rec.get("sampler") and not style_override:
                    use_sampler = rec["sampler"]
                if rec.get("scheduler") and not style_override:
                    use_scheduler = rec["scheduler"]
                logger.info(
                    f"generate_batch: applying learned params for {character_slug} "
                    f"(confidence={rec['confidence']}, cfg={use_cfg}, steps={use_steps})"
                )
        except Exception:
            pass

    if include_feedback_negatives:
        feedback_neg = get_feedback_negatives(character_slug)
        if feedback_neg:
            base_negative = f"{base_negative}, {feedback_neg}"
            logger.info(f"generate_batch: added feedback negatives for {character_slug}")

    char_neg = build_character_negatives(db_info.get("appearance_data"))
    if char_neg:
        base_negative = f"{base_negative}, {char_neg}"

    # Sampler normalization — cascade: recommend_params > DB > profile defaults
    use_cfg = use_cfg or profile.get("default_cfg") or 7.0
    use_steps = use_steps or profile.get("default_steps") or 25
    use_sampler = use_sampler or profile.get("default_sampler")
    use_scheduler = use_scheduler or profile.get("default_scheduler")
    norm_sampler, norm_scheduler = normalize_sampler(use_sampler, use_scheduler)

    # Prepare pose pool
    if custom_poses:
        # Caller-supplied poses (e.g. scene-derived) — use them in order, cycling if needed
        poses = [custom_poses[i % len(custom_poses)] for i in range(count)]
    elif pose_variation:
        if count <= len(POSE_VARIATIONS):
            poses = random.sample(POSE_VARIATIONS, count)
        else:
            repeats = count // len(POSE_VARIATIONS) or 1
            remainder = count % len(POSE_VARIATIONS)
            poses = POSE_VARIATIONS * repeats + random.sample(POSE_VARIATIONS, remainder)
            random.shuffle(poses)
    else:
        poses = [""] * count

    # 3. Submit, poll, and copy ONE job at a time under the concurrency semaphore.
    # This prevents ComfyUI queue flooding when multiple generate_batch calls
    # run concurrently (e.g. multi-checkpoint comparison).
    results = []
    for i in range(count):
        pose = poses[i] if i < len(poses) else random.choice(POSE_VARIATIONS)

        # Build full prompt: model-aware translation
        if prompt_override:
            # Manual override: still add solo/background but skip translation
            full_prompt = f"{prompt_override}, {pose}, {profile['solo_suffix']}, {profile['background_suffix']}" if pose else f"{prompt_override}, {profile['solo_suffix']}, {profile['background_suffix']}"
        else:
            full_prompt = translate_prompt(
                design_prompt=design_prompt,
                appearance_data=db_info.get("appearance_data"),
                profile=profile,
                pose=pose,
            )

        use_seed = (seed + i) if seed is not None else None

        workflow = build_comfyui_workflow(
            design_prompt=full_prompt,
            checkpoint_model=checkpoint,
            cfg_scale=use_cfg,
            steps=use_steps,
            sampler=norm_sampler,
            scheduler=norm_scheduler,
            width=db_info.get("width") or 512,
            height=db_info.get("height") or 768,
            negative_prompt=base_negative,
            generation_type="image",
            seed=use_seed,
            character_slug=character_slug,
            project_name=project_name,
            pose=pose,
        )

        # Acquire semaphore slot before submitting — limits ComfyUI queue depth
        async with _comfyui_slot:
            try:
                prompt_id = submit_comfyui_workflow(workflow)
            except Exception as e:
                logger.error(f"generate_batch: ComfyUI submission failed for {character_slug}: {e}")
                continue

            actual_seed = workflow["3"]["inputs"]["seed"]

            # Audit log
            gen_id = await log_generation(
                character_slug=character_slug,
                project_name=project_name,
                comfyui_prompt_id=prompt_id,
                generation_type="image",
                checkpoint_model=checkpoint,
                prompt=full_prompt,
                negative_prompt=base_negative,
                seed=actual_seed,
                cfg_scale=use_cfg,
                steps=use_steps,
                sampler=norm_sampler,
                scheduler=norm_scheduler,
                width=db_info.get("width"),
                height=db_info.get("height"),
            )

            if fire_events:
                await event_bus.emit(GENERATION_SUBMITTED, {
                    "character_slug": character_slug,
                    "prompt_id": prompt_id,
                    "generation_history_id": gen_id,
                    "project_name": project_name,
                })

            logger.info(
                f"generate_batch: submitted {character_slug} [{i+1}/{count}] "
                f"prompt_id={prompt_id} seed={actual_seed}"
            )

            # Poll until this specific job completes before releasing the slot
            filenames = await _poll_until_complete(prompt_id)

        # --- Slot released, process results outside semaphore ---
        if not filenames:
            logger.warning(f"generate_batch: timeout waiting for {prompt_id}")
            results.append({
                "prompt_id": prompt_id, "seed": actual_seed, "pose": pose,
                "gen_id": gen_id, "status": "timeout", "images": [],
            })
            continue

        copied_images = _copy_to_dataset(
            character_slug=character_slug,
            filenames=filenames,
            design_prompt=design_prompt,
            job_params={
                "seed": actual_seed,
                "full_prompt": full_prompt,
                "negative_prompt": base_negative,
                "checkpoint_model": checkpoint,
                "model_profile": profile["style_label"],
                "cfg_scale": use_cfg,
                "steps": use_steps,
                "sampler": norm_sampler,
                "scheduler": norm_scheduler,
                "width": db_info.get("width"),
                "height": db_info.get("height"),
                "comfyui_prompt_id": prompt_id,
                "generation_history_id": gen_id,
            },
            project_name=project_name,
            character_name=db_info.get("name"),
            pose=pose,
        )

        for img_name in copied_images:
            register_pending_image(character_slug, img_name)

        results.append({
            "prompt_id": prompt_id, "seed": actual_seed, "pose": pose,
            "gen_id": gen_id, "status": "completed", "images": copied_images,
        })

        logger.info(
            f"generate_batch: completed {character_slug} prompt_id={prompt_id} "
            f"-> {len(copied_images)} image(s)"
        )

    return results


async def _poll_until_complete(
    prompt_id: str, timeout: int = 300, interval: float = 3.0
) -> list[str] | None:
    """Poll ComfyUI until a job completes. Returns output filenames or None on timeout."""
    import time
    start = time.time()
    while time.time() - start < timeout:
        progress = get_comfyui_progress(prompt_id)
        if progress.get("status") == "completed":
            return progress.get("images", [])
        if progress.get("status") == "error":
            logger.warning(f"ComfyUI error for {prompt_id}: {progress.get('error')}")
            return None
        await asyncio.sleep(interval)
    return None


def _copy_to_dataset(
    character_slug: str,
    filenames: list[str],
    design_prompt: str,
    job_params: dict,
    project_name: str = None,
    character_name: str = None,
    pose: str = None,
) -> list[str]:
    """Copy generated images from ComfyUI output to dataset directory.

    Returns list of new image filenames (for registration as pending).
    """
    dataset_images = BASE_PATH / character_slug / "images"
    dataset_images.mkdir(parents=True, exist_ok=True)
    copied = []

    for fname in filenames:
        src = COMFYUI_OUTPUT_DIR / fname
        if not src.exists():
            continue

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        rand_suffix = f"{random.randint(1000, 9999)}"
        unique_name = f"gen_{character_slug}_{ts}_{rand_suffix}.png"
        dest = dataset_images / unique_name

        shutil.copy2(src, dest)

        # Write caption — use full_prompt (includes pose, quality, solo suffix)
        # so LoRA training learns pose/action conditioning, not just identity
        caption = job_params.get("full_prompt") or design_prompt
        dest.with_suffix(".txt").write_text(caption)

        # Write metadata sidecar
        meta = {
            **job_params,
            "design_prompt": design_prompt,
            "pose": pose or "",
            "project_name": project_name or "",
            "character_name": character_name or "",
            "source": "generate_batch",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))

        copied.append(unique_name)

        # Keep images in ComfyUI output so they show in the UI

    return copied
