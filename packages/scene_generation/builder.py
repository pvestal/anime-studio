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
from packages.core.events import event_bus, SHOT_GENERATED

from .framepack import build_framepack_workflow, _submit_comfyui_workflow
from .ltx_video import build_ltx_workflow, _submit_comfyui_workflow as _submit_ltx_workflow
from .wan_video import build_wan_t2v_workflow, build_wan22_workflow, _submit_comfyui_workflow as _submit_wan_workflow
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

# ---------------------------------------------------------------------------
# Genre-aware video prompt profiles
# ---------------------------------------------------------------------------
# Tag categories — superset of classification keywords across all genres.
# Used by both FramePack (reorder) and Wan (condense) paths.
TAG_CATEGORIES: dict[str, set[str]] = {
    "identity": {"male", "man", "woman", "female", "young", "old", "japanese",
                 "boy", "girl", "adult", "teen", "child", "elderly"},
    "face": {"expression", "smirk", "smile", "frown", "eyes", "eye", "face",
             "scar", "menacing", "nervous", "confident", "worried", "aggressive",
             "gentle", "stern", "gaze", "look", "glasses", "eyepatch", "mask",
             "beard", "mustache"},
    "hair": {"hair", "bald", "ponytail", "braid", "bangs", "twintail",
             "short hair", "long hair", "mohawk"},
    "skin": {"tan", "pale", "skin", "dark skin", "fair", "rough", "smooth",
             "tattoo", "freckle"},
    "body": {"body", "build", "muscular", "slim", "athletic", "toned",
             "shoulder", "chest", "pec", "waist", "abs", "thigh", "leg",
             "butt", "hip", "tall", "short", "lean", "broad", "narrow",
             "flat male chest", "wide", "underfed", "stocky", "petite"},
    "anatomy": {"penis", "testicle", "vagina", "breast", "nipple", "areola",
                "cock", "b-cup", "c-cup", "d-cup", "perky", "nude", "naked",
                "genitals"},
    "equipment": {"sword", "shield", "armor", "helmet", "weapon", "gun",
                  "blade", "staff", "bow", "axe", "spear", "dagger", "gauntlet",
                  "scabbard", "holster"},
    "clothing": {"clothing", "dress", "shirt", "pants", "skirt", "jacket",
                 "coat", "boots", "gloves", "cape", "cloak", "hat", "uniform",
                 "suit", "scarf", "belt", "collar", "bikini", "underwear",
                 "overalls", "vest"},
    "cybernetics": {"cybernetic", "augment", "prosthetic", "implant", "visor",
                    "neon", "circuit", "chrome", "mechanical arm", "bionic"},
    "proportions": {"proportions", "chibi", "stylized", "exaggerated",
                    "realistic proportions", "cartoonish", "round", "plump"},
    "style": {"3d render", "cel-shaded", "pixel", "watercolor", "painterly",
              "illumination", "pixar", "disney", "ghibli"},
}

# Each genre profile specifies how to condense/reorder design_prompt tags.
GENRE_VIDEO_PROFILES: dict[str, dict] = {
    "explicit": {
        "keep_categories": {"identity", "hair", "skin", "body", "anatomy"},
        "reorder_priority": ["identity", "face", "hair", "skin", "body", "anatomy"],
        "negative_additions": "malformed genitals, distorted genitals, malformed penis",
        "include_scene_desc": True,
    },
    "cyberpunk": {
        "keep_categories": {"identity", "hair", "skin", "body", "face",
                            "equipment", "clothing", "cybernetics"},
        "reorder_priority": ["identity", "face", "hair", "equipment",
                             "cybernetics", "clothing", "body", "skin"],
        "negative_additions": "modern casual, peaceful, bright cheerful",
        "include_scene_desc": True,
    },
    "action": {
        "keep_categories": {"identity", "hair", "skin", "body", "face",
                            "equipment", "clothing"},
        "reorder_priority": ["identity", "face", "hair", "equipment",
                             "clothing", "body", "skin"],
        "negative_additions": "peaceful, static, boring",
        "include_scene_desc": True,
    },
    "3d_animation": {
        "keep_categories": {"identity", "hair", "face", "clothing",
                            "proportions", "style"},
        "reorder_priority": ["style", "identity", "face", "hair",
                             "clothing", "proportions"],
        "negative_additions": "photorealistic, anime, 2d, flat shading",
        "include_scene_desc": True,
    },
    "anime": {
        "keep_categories": {"identity", "hair", "face", "skin", "body",
                            "clothing"},
        "reorder_priority": ["identity", "face", "hair", "clothing",
                             "body", "skin"],
        "negative_additions": "photorealistic, 3d render, live action",
        "include_scene_desc": True,
    },
    "default": {
        "keep_categories": {"identity", "hair", "face", "skin", "body",
                            "clothing", "equipment"},
        "reorder_priority": ["identity", "face", "hair", "clothing",
                             "equipment", "body", "skin"],
        "negative_additions": "",
        "include_scene_desc": True,
    },
}


def _get_genre_profile(genre: str | None, content_rating: str | None) -> dict:
    """Resolve project genre + content_rating → video profile dict."""
    # Explicit content rating overrides genre completely
    if content_rating:
        cr = content_rating.lower()
        if any(kw in cr for kw in ("xxx", "adult", "nsfw", "hentai")):
            return GENRE_VIDEO_PROFILES["explicit"]

    if not genre:
        return GENRE_VIDEO_PROFILES["default"]

    g = genre.lower().strip()
    # Direct match
    if g in GENRE_VIDEO_PROFILES:
        return GENRE_VIDEO_PROFILES[g]
    # Keyword-based fallback
    if any(kw in g for kw in ("cyber", "sci-fi", "scifi", "dystop")):
        return GENRE_VIDEO_PROFILES["cyberpunk"]
    if any(kw in g for kw in ("action", "shonen", "battle", "fight", "martial")):
        return GENRE_VIDEO_PROFILES["action"]
    if any(kw in g for kw in ("3d", "pixar", "cg", "illumination", "cartoon")):
        return GENRE_VIDEO_PROFILES["3d_animation"]
    if any(kw in g for kw in ("anime", "manga", "slice of life", "romance")):
        return GENRE_VIDEO_PROFILES["anime"]
    return GENRE_VIDEO_PROFILES["default"]


def _classify_tag(tag_lower: str) -> str:
    """Classify a single prompt tag into a TAG_CATEGORIES bucket."""
    for cat, keywords in TAG_CATEGORIES.items():
        if any(kw in tag_lower for kw in keywords):
            return cat
    return "other"


def _condense_for_video(design_prompt: str, genre_profile: dict,
                        engine: str) -> str:
    """Replace both _video_safe_appearance and _condensed_appearance.

    FramePack: reorder tags by genre priority (keeps all meaningful tags).
    Wan: aggressive condense — only keep tags matching genre keep_categories.
    """
    strip_tags = {"solo", "1boy", "1girl", "full body", "score_9", "score_8_up"}
    parts = [p.strip() for p in design_prompt.split(",") if p.strip()]
    parts = [p for p in parts if p.lower().strip() not in strip_tags]

    if engine in ("framepack", "framepack_f1"):
        # Reorder by genre priority, keep all categorised tags
        priority = genre_profile.get("reorder_priority",
                                     GENRE_VIDEO_PROFILES["default"]["reorder_priority"])
        buckets: dict[str, list[str]] = {cat: [] for cat in priority}
        buckets["other"] = []
        for p in parts:
            cat = _classify_tag(p.lower().strip())
            if cat in buckets:
                buckets[cat].append(p)
            else:
                buckets["other"].append(p)
        ordered = []
        for cat in priority:
            ordered.extend(buckets.get(cat, []))
        ordered.extend(buckets["other"])
        return ", ".join(ordered) if ordered else design_prompt
    else:
        # Wan T2V: aggressive condense — only keep_categories tags
        keep_cats = genre_profile.get("keep_categories",
                                      GENRE_VIDEO_PROFILES["default"]["keep_categories"])
        # Flatten all keywords from kept categories
        keep_keywords: set[str] = set()
        for cat in keep_cats:
            if cat in TAG_CATEGORIES:
                keep_keywords.update(TAG_CATEGORIES[cat])
        kept = []
        for p in parts:
            low = p.lower().strip()
            if any(kw in low for kw in keep_keywords):
                kept.append(p)
        return ", ".join(kept) if kept else design_prompt


def _build_video_negative(style_anchor: str, genre_profile: dict,
                          nsm_negative: str = "") -> str:
    """Build negative prompt from base + style exclusions + genre additions."""
    parts = ["low quality, blurry, watermark, deformed face, distorted face, "
             "bad hands, extra limbs"]
    # Style-aware exclusions
    if style_anchor:
        if "photorealistic" in style_anchor:
            parts.append("anime, cartoon, illustration, drawing, painted, "
                         "cel-shaded, 3d render")
        elif "anime" in style_anchor:
            parts.append("photorealistic, photograph, live action, real person")
        elif "Pixar" in style_anchor:
            parts.append("anime, photorealistic, photograph, live action, 2d, flat")
    # Genre-specific additions
    genre_neg = genre_profile.get("negative_additions", "")
    if genre_neg:
        parts.append(genre_neg)
    # NSM state additions
    if nsm_negative:
        parts.append(nsm_negative)
    return ", ".join(parts)


# --- Slug resolver: maps short slugs (rina) to dataset dir slugs (rina_suzuki) ---
_slug_cache: dict[str, str] = {}


def resolve_slug(short_slug: str) -> str:
    """Resolve a possibly-short character slug to the actual dataset directory name.

    Tries exact match first, then prefix match (short_slug + '_*').
    Caches results for the lifetime of the process.
    """
    if short_slug in _slug_cache:
        return _slug_cache[short_slug]
    # Exact match
    if (BASE_PATH / short_slug).is_dir():
        _slug_cache[short_slug] = short_slug
        return short_slug
    # Prefix match: rina -> rina_suzuki
    candidates = sorted(BASE_PATH.glob(f"{short_slug}_*"))
    dirs = [c for c in candidates if c.is_dir()]
    if dirs:
        resolved = dirs[0].name
        _slug_cache[short_slug] = resolved
        return resolved
    # No match — return as-is
    _slug_cache[short_slug] = short_slug
    return short_slug


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
                entry = history[prompt_id]
                # Check execution status
                status_info = entry.get("status", {})
                status_str = status_info.get("status_str", "unknown")
                if status_str == "error":
                    # Extract error details from messages
                    msgs = status_info.get("messages", [])
                    err_detail = ""
                    for msg in msgs:
                        if isinstance(msg, list) and len(msg) >= 2 and "error" in str(msg[0]).lower():
                            err_detail = str(msg[1])[:200]
                    return {"status": "error", "output_files": [], "error": err_detail or "ComfyUI execution error"}
                outputs = entry.get("outputs", {})
                videos = []
                for node_output in outputs.values():
                    for key in ("videos", "gifs", "images"):
                        for item in node_output.get(key, []):
                            fn = item.get("filename")
                            if fn:
                                videos.append(fn)
                    # Also check 'video' (singular) used by some Wan nodes
                    if "video" in node_output:
                        v = node_output["video"]
                        if isinstance(v, dict) and v.get("filename"):
                            videos.append(v["filename"])
                        elif isinstance(v, list):
                            for item in v:
                                fn = item.get("filename") if isinstance(item, dict) else None
                                if fn:
                                    videos.append(fn)
                if not videos and status_str == "success":
                    # Scan output dir for files matching prefix (fallback)
                    try:
                        import glob as _glob
                        prompt_files = _glob.glob(str(COMFYUI_OUTPUT_DIR / f"*{prompt_id[:8]}*"))
                        videos = [Path(f).name for f in prompt_files if f.endswith((".mp4", ".webm"))]
                    except Exception:
                        pass
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


async def generate_scene(scene_id: str, auto_approve: bool = False):
    """Background task: generate all shots sequentially with continuity chaining.

    Uses _scene_generation_lock to ensure only one scene generates at a time,
    so scenes complete fully (all shots in order) before the next scene starts.

    Args:
        auto_approve: If True, shots are auto-approved after generation so the
            full downstream pipeline (voice → music → assembly) fires without
            manual review. Also enabled by project metadata auto_approve_shots=true.
    """
    await _scene_generation_lock.acquire()
    try:
        await _generate_scene_impl(scene_id, auto_approve=auto_approve)
    finally:
        _scene_generation_lock.release()


async def ensure_source_videos(conn, scene_id: str, shots: list) -> int:
    """Auto-assign best source video clips to solo shots from character_clips table.

    Mirrors ensure_source_images but assigns video clips for V2V style transfer.
    Only assigns to solo character shots that don't already have a source_video_path
    and weren't manually assigned. Returns the number of shots auto-assigned.
    """
    null_shots = [
        s for s in shots
        if not s.get("source_video_path")
        and not s.get("source_video_auto_assigned")
        and len(s.get("characters_present") or []) == 1
    ]
    if not null_shots:
        return 0

    assigned = 0
    for shot in null_shots:
        chars = shot.get("characters_present") or []
        slug = chars[0] if chars else None
        if not slug:
            continue

        try:
            clip_row = await conn.fetchrow(
                "SELECT clip_path FROM character_clips "
                "WHERE character_slug = $1 ORDER BY similarity DESC NULLS LAST LIMIT 1",
                slug,
            )
            if clip_row and clip_row["clip_path"] and Path(clip_row["clip_path"]).exists():
                await conn.execute(
                    "UPDATE shots SET source_video_path = $2, source_video_auto_assigned = TRUE WHERE id = $1",
                    shot["id"], clip_row["clip_path"],
                )
                assigned += 1
                logger.info(
                    f"Shot {shot['id']}: auto-assigned source video clip for '{slug}' "
                    f"({clip_row['clip_path']})"
                )
        except Exception as e:
            logger.debug(f"Source video lookup for {slug}: {e}")

    return assigned


async def ensure_source_images(conn, scene_id: str, shots: list) -> int:
    """Auto-assign best source images to shots that have NULL source_image_path.

    Uses the image recommender to score and rank approved images per character.
    Assigns images to ALL solo character shots (1 character) regardless of current
    engine — the engine selector runs AFTER this and will pick FramePack when a
    source image is available. Multi-char shots (>1 character) are skipped since
    they use Wan T2V (text-to-video) which doesn't need a source image.

    Returns the number of shots that were auto-assigned.
    """
    null_shots = [
        s for s in shots
        if not s["source_image_path"]
        and len(s.get("characters_present") or []) == 1
    ]
    if not null_shots:
        return 0

    # Priority 0: Check continuity frames from previously completed shots
    # These are the last frames from prior scenes — best for visual consistency
    assigned_from_continuity = 0
    scene_row = await conn.fetchrow("SELECT project_id FROM scenes WHERE id = $1", scene_id)
    _project_id = scene_row["project_id"] if scene_row else None
    if _project_id:
        remaining_null = []
        for shot in null_shots:
            chars = shot.get("characters_present") or []
            slug = chars[0] if chars else None
            if not slug:
                remaining_null.append(shot)
                continue
            try:
                cont_row = await conn.fetchrow(
                    "SELECT frame_path FROM character_continuity_frames "
                    "WHERE project_id = $1 AND character_slug = $2 AND scene_id != $3",
                    _project_id, slug, scene_id,
                )
                if cont_row and cont_row["frame_path"] and Path(cont_row["frame_path"]).exists():
                    await conn.execute(
                        "UPDATE shots SET source_image_path = $2, source_image_auto_assigned = TRUE WHERE id = $1",
                        shot["id"], cont_row["frame_path"],
                    )
                    assigned_from_continuity += 1
                    logger.info(
                        f"Shot {shot['id']}: continuity frame for '{slug}' from prior scene"
                    )
                    continue
            except Exception as _e:
                logger.debug(f"Continuity frame lookup for {slug}: {_e}")
            remaining_null.append(shot)
        null_shots = remaining_null
        if not null_shots:
            return assigned_from_continuity

    # Build approved image map from approval_status.json
    all_slugs: set[str] = set()
    for shot in null_shots:
        chars = shot.get("characters_present")
        if chars and isinstance(chars, list):
            all_slugs.update(chars)

    if not all_slugs:
        logger.warning(f"Scene {scene_id}: shots need source images but no characters_present set")
        return assigned_from_continuity

    approved: dict[str, list[str]] = {}
    for slug in all_slugs:
        dir_slug = resolve_slug(slug)
        approval_file = BASE_PATH / dir_slug / "approval_status.json"
        images_dir = BASE_PATH / dir_slug / "images"
        if not images_dir.exists():
            logger.debug(f"No dataset dir for slug '{slug}' (resolved: '{dir_slug}')")
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
                    # Store under BOTH short and dir slug so lookups work either way
                    approved[slug] = sorted(imgs)
                    approved[dir_slug] = approved[slug]
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read approval_status.json for {dir_slug}: {e}")

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
        dir_slug = resolve_slug(slug)
        try:
            # Try both short and resolved slug in effectiveness table
            rows = await conn.fetch(
                "SELECT image_name, AVG(video_quality_score) as avg_score "
                "FROM source_image_effectiveness "
                "WHERE character_slug IN ($1, $2) AND video_quality_score IS NOT NULL "
                "GROUP BY image_name",
                slug, dir_slug,
            )
            if rows:
                video_scores[slug] = {r["image_name"]: float(r["avg_score"]) for r in rows}
                video_scores[dir_slug] = video_scores[slug]
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

    # Fetch narrative state and image tags for state-aware selection (NSM Phase 1b)
    character_states = None
    character_image_tags = None
    try:
        state_rows = await conn.fetch(
            "SELECT character_slug, clothing, hair_state, emotional_state, "
            "body_state, energy_level FROM character_scene_state WHERE scene_id = $1",
            scene_id,
        )
        if state_rows:
            character_states = {
                r["character_slug"]: dict(r) for r in state_rows
            }
            # Fetch image tags for all characters that have states
            character_image_tags = {}
            for slug in character_states:
                tag_rows = await conn.fetch(
                    "SELECT image_name, clothing, hair_state, expression, "
                    "body_state, pose FROM image_visual_tags "
                    "WHERE character_slug = $1",
                    slug,
                )
                if tag_rows:
                    character_image_tags[slug] = {
                        r["image_name"]: dict(r) for r in tag_rows
                    }
    except Exception as e:
        logger.debug(f"NSM state lookup for scene {scene_id}: {e}")

    recommendations = recommend_for_scene(
        BASE_PATH, shot_list, approved, top_n=1, video_scores=video_scores,
        character_states=character_states,
        character_image_tags=character_image_tags,
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
        dir_slug = resolve_slug(best['slug'])
        image_path = f"{dir_slug}/images/{best['image_name']}"

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

    total_assigned = assigned_count + assigned_from_continuity
    if total_assigned:
        logger.info(
            f"Scene {scene_id}: auto-assigned source images for {total_assigned} shots "
            f"({assigned_from_continuity} from continuity, {assigned_count} from approved pool)"
        )

    return total_assigned


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


async def _generate_scene_impl(scene_id: str, auto_approve: bool = False):
    """Inner implementation — do not call directly, use generate_scene().

    Args:
        scene_id: UUID of the scene to generate.
        auto_approve: If True, auto-approve all completed shots so the full
            downstream pipeline (voice synthesis → music → audio mixing →
            scene assembly) fires automatically without manual review.
    """
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

        # Get project_id, scene_number, and episode info for continuity tracking + filenames
        scene_row = await conn.fetchrow("""
            SELECT s.project_id, s.scene_number, e.episode_number,
                   REGEXP_REPLACE(LOWER(REPLACE(p.name, ' ', '_')), '[^a-z0-9_]', '', 'g') as project_slug,
                   p.genre, p.content_rating, p.video_lora
            FROM scenes s
            LEFT JOIN episodes e ON s.episode_id = e.id
            LEFT JOIN projects p ON s.project_id = p.id
            WHERE s.id = $1
        """, scene_id)
        project_id = scene_row["project_id"] if scene_row else None
        scene_number = scene_row["scene_number"] if scene_row else None
        episode_number = scene_row["episode_number"] if scene_row else None
        project_slug = scene_row["project_slug"] if scene_row else "proj"
        project_video_lora = scene_row.get("video_lora") if scene_row else None
        genre_profile = _get_genre_profile(
            scene_row.get("genre") if scene_row else None,
            scene_row.get("content_rating") if scene_row else None,
        )

        # Check project-level auto_approve setting if not explicitly passed
        if not auto_approve and project_id:
            try:
                proj_meta = await conn.fetchval(
                    "SELECT metadata->>'auto_approve_shots' FROM projects WHERE id = $1",
                    project_id,
                )
                if proj_meta == "true":
                    auto_approve = True
            except Exception:
                pass

        await conn.execute(
            "UPDATE scenes SET generation_status = 'generating', total_shots = $2 WHERE id = $1",
            scene_id, len(shots),
        )

        # Step 0: Auto-assign source VIDEO clips (for V2V reference pipeline)
        video_assigned = await ensure_source_videos(conn, scene_id, shots)
        if video_assigned:
            shots = await conn.fetch(
                "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number",
                scene_id,
            )

        # Step 1: Auto-assign source images FIRST (before engine selection)
        # This ensures solo shots get images, then engine selector sees
        # has_source_image=True and picks FramePack instead of falling back to Wan
        auto_assigned = await ensure_source_images(conn, scene_id, shots)
        if auto_assigned:
            shots = await conn.fetch(
                "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number",
                scene_id,
            )

        # Step 2: Run engine selector with source image + video info available
        from .engine_selector import select_engine as _pre_select_engine
        _pre_wan_lora = project_video_lora  # From projects.video_lora column (project-scoped)
        for _s in shots:
            _s_chars = _s.get("characters_present")
            _s_char_list = list(_s_chars) if isinstance(_s_chars, list) else []
            _s_has_source = bool(_s.get("source_image_path"))
            _s_has_video = bool(_s.get("source_video_path"))
            _s_type = _s.get("shot_type") or "medium"
            _sel = _pre_select_engine(
                shot_type=_s_type,
                characters_present=_s_char_list,
                has_source_image=_s_has_source,
                has_source_video=_s_has_video,
                project_wan_lora=_pre_wan_lora,
            )
            if _sel.engine != (_s.get("video_engine") or "framepack"):
                await conn.execute(
                    "UPDATE shots SET video_engine = $2 WHERE id = $1",
                    _s["id"], _sel.engine,
                )
                logger.info(f"Shot {_s['id']}: pre-assigned engine={_sel.engine} ({_sel.reason})")
        # Re-fetch to pick up engine updates
        shots = await conn.fetch(
            "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number",
            scene_id,
        )

        # Pre-fetch narrative states for this scene (Phase 4)
        _nsm_shot_states = {}
        try:
            from packages.narrative_state.continuity import get_shot_state_context
            for _s in shots:
                _s_ctx = await get_shot_state_context(conn, scene_id, dict(_s))
                if _s_ctx:
                    _nsm_shot_states[str(_s["id"])] = _s_ctx
        except Exception as _e:
            logger.debug(f"NSM state context pre-fetch: {_e}")

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
                from .wan_video import build_wan_t2v_workflow, build_wan22_workflow, _submit_comfyui_workflow as _submit_wan_workflow
                import time as _time_inner

                shot_dict = dict(shot)
                character_slug = None
                chars = shot_dict.get("characters_present")
                if chars and isinstance(chars, list) and len(chars) > 0:
                    character_slug = chars[0]

                # Use project-level video_lora from DB (project-scoped, not global)
                _project_wan_lora = project_video_lora

                # Auto-select engine based on shot characteristics
                from .engine_selector import select_engine
                has_source = bool(shot_dict.get("source_image_path"))
                has_source_video = bool(shot_dict.get("source_video_path"))
                shot_type = shot_dict.get("shot_type") or "medium"
                char_list = chars if isinstance(chars, list) else []
                engine_sel = select_engine(
                    shot_type=shot_type,
                    characters_present=char_list,
                    has_source_image=has_source,
                    has_source_video=has_source_video,
                    project_wan_lora=_project_wan_lora,
                )
                shot_engine = engine_sel.engine
                # Persist engine selection to DB
                await conn.execute(
                    "UPDATE shots SET video_engine = $2 WHERE id = $1",
                    shot_id, shot_engine,
                )
                logger.info(f"Shot {shot_id}: engine={shot_engine} reason='{engine_sel.reason}'")

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

                # Helper: look up character by short or full slug
                async def _find_character(slug):
                    return await conn.fetchrow(
                        "SELECT name, design_prompt FROM characters "
                        "WHERE project_id = $2 AND ("
                        "  REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1 "
                        "  OR REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') LIKE $1 || '_%'"
                        ")", slug, project_id,
                    )

                # Fetch scene context for richer prompts
                scene_desc = ""
                scene_location = ""
                scene_mood = ""
                scene_time = ""
                try:
                    _scene_ctx = await conn.fetchrow(
                        "SELECT description, location, time_of_day, mood FROM scenes WHERE id = $1",
                        scene_id,
                    )
                    if _scene_ctx:
                        scene_desc = _scene_ctx["description"] or ""
                        scene_location = _scene_ctx["location"] or ""
                        scene_mood = _scene_ctx["mood"] or ""
                        scene_time = _scene_ctx["time_of_day"] or ""
                except Exception:
                    pass

                # Fetch project style for visual anchoring
                style_anchor = ""
                _project_width = None
                _project_height = None
                try:
                    _style_row = await conn.fetchrow(
                        "SELECT gs.checkpoint_model, gs.prompt_format, gs.width, gs.height FROM projects p "
                        "JOIN generation_styles gs ON p.default_style = gs.style_name "
                        "WHERE p.id = $1", project_id,
                    )
                    if _style_row:
                        ckpt = (_style_row["checkpoint_model"] or "").lower()
                        if "realistic" in ckpt or "cyber" in ckpt or "basil" in ckpt or "lazymix" in ckpt:
                            style_anchor = "photorealistic, live action film, cinematic lighting"
                        elif "cartoon" in ckpt or "pixar" in ckpt:
                            style_anchor = "3D animated, Pixar style, cinematic lighting"
                        elif "counterfeit" in ckpt or "noob" in ckpt:
                            style_anchor = "anime style, detailed animation, cinematic"
                        # Store project resolution for Wan T2V aspect ratio
                        _project_width = _style_row["width"]
                        _project_height = _style_row["height"]
                except Exception:
                    pass

                current_prompt = motion_prompt
                if character_slug and shot_engine in ("framepack", "framepack_f1"):
                    try:
                        char_row = await _find_character(character_slug)
                        if char_row and char_row["design_prompt"]:
                            appearance = _condense_for_video(char_row["design_prompt"], genre_profile, shot_engine)
                            # Build FramePack prompt with same structure as Wan:
                            # style anchor → scene context → character → motion
                            fp_parts = []
                            if style_anchor:
                                fp_parts.append(style_anchor)
                            if scene_location:
                                setting = scene_location
                                if scene_time:
                                    setting += f", {scene_time}"
                                fp_parts.append(setting)
                            if scene_desc:
                                fp_parts.append(scene_desc)
                            fp_parts.append(appearance)
                            if motion_prompt and motion_prompt.lower() != "static":
                                fp_parts.append(motion_prompt)
                            fp_parts.append("consistent character appearance, maintain all physical features")
                            if scene_mood:
                                fp_parts.append(f"{scene_mood} mood")
                            current_prompt = ", ".join(fp_parts)
                            logger.info(f"Shot {shot_id}: FramePack prompt ({len(current_prompt)} chars): {current_prompt[:120]}...")
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: design_prompt lookup failed: {e}")
                elif shot_engine == "wan22" and chars:
                    # Wan 2.2 5B: richer prompt capacity than 1.3B.
                    # Character → action → scene context → style (5B handles longer prompts well).
                    try:
                        char_descriptions = []
                        for cslug in chars:
                            char_row = await _find_character(cslug)
                            if char_row and char_row["design_prompt"]:
                                cname = char_row["name"]
                                appearance = _condense_for_video(char_row["design_prompt"], genre_profile, shot_engine)
                                char_descriptions.append(f"{cname} ({appearance})")
                        prompt_parts = []
                        # 1. Character descriptions (5B has enough attention for full descriptions)
                        if char_descriptions:
                            prompt_parts.append("; ".join(char_descriptions))
                        # 2. Action/motion
                        if motion_prompt and motion_prompt.lower() != "static":
                            prompt_parts.append(motion_prompt)
                        # 3. Scene description (more room with 5B)
                        if scene_desc and genre_profile.get("include_scene_desc", True):
                            prompt_parts.append(scene_desc[:200])
                        # 4. Scene context
                        if scene_location:
                            setting = scene_location
                            if scene_time:
                                setting += f", {scene_time}"
                            prompt_parts.append(setting)
                        # 5. Style anchor
                        if style_anchor:
                            prompt_parts.append(style_anchor)
                        if scene_mood:
                            prompt_parts.append(f"{scene_mood} mood")
                        current_prompt = ". ".join(prompt_parts)
                        logger.info(f"Shot {shot_id}: Wan22 prompt ({len(current_prompt)} chars): {current_prompt[:120]}...")
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: Wan22 prompt build failed: {e}")
                elif shot_engine == "wan" and chars:
                    # Wan T2V: ACTION FIRST, then condensed characters, then context.
                    # Wan 1.3B has limited attention — explicit terms must be near the start.
                    try:
                        char_descriptions = []
                        for cslug in chars:
                            char_row = await _find_character(cslug)
                            if char_row and char_row["design_prompt"]:
                                cname = char_row["name"]
                                appearance = _condense_for_video(char_row["design_prompt"], genre_profile, shot_engine)
                                char_descriptions.append(f"{cname} ({appearance})")
                        # Build structured prompt: ACTION → characters → scene
                        prompt_parts = []
                        # 1. Action/motion FIRST — this is what the shot is about
                        if motion_prompt and motion_prompt.lower() != "static":
                            prompt_parts.append(motion_prompt)
                        # 2. Condensed character appearances
                        if char_descriptions:
                            prompt_parts.append("; ".join(char_descriptions))
                        # 3. Scene description (truncated for token budget)
                        if scene_desc and genre_profile.get("include_scene_desc", True):
                            prompt_parts.append(scene_desc[:120])
                        # 4. Scene context (location + time)
                        if scene_location:
                            setting = scene_location
                            if scene_time:
                                setting += f", {scene_time}"
                            prompt_parts.append(setting)
                        # 5. Style anchor last (least important for content)
                        if style_anchor:
                            prompt_parts.append(style_anchor)
                        current_prompt = ". ".join(prompt_parts)
                        logger.info(f"Shot {shot_id}: Wan prompt ({len(current_prompt)} chars): {current_prompt[:120]}...")
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: Wan prompt build failed: {e}")

                # Inject NSM state descriptors into prompt (Phase 4)
                _shot_nsm = _nsm_shot_states.get(str(shot_id), {})
                if _shot_nsm and character_slug and character_slug in _shot_nsm:
                    _state_ctx = _shot_nsm[character_slug]
                    if _state_ctx.get("prompt_additions"):
                        current_prompt = f"{current_prompt}, {_state_ctx['prompt_additions']}"
                        logger.info(f"Shot {shot_id}: NSM state additions: {_state_ctx['prompt_additions'][:80]}")
                elif _shot_nsm and shot_engine == "wan" and chars:
                    # Multi-character: use structured state prompt builder
                    try:
                        from packages.narrative_state.continuity import build_multi_character_state_prompt
                        _mc_chars = []
                        for _cs in chars:
                            _cs_state = _shot_nsm.get(_cs, {}).get("state", {})
                            _cs_row = await _find_character(_cs)
                            _mc_chars.append({
                                "name": _cs_row["name"] if _cs_row else _cs,
                                "slug": _cs,
                                "design_prompt": _cs_row["design_prompt"] if _cs_row else "",
                                "state": _cs_state,
                            })
                        if any(c["state"] for c in _mc_chars):
                            current_prompt = build_multi_character_state_prompt(
                                characters=_mc_chars,
                                motion_prompt=current_prompt,
                            )
                            logger.info(f"Shot {shot_id}: multi-char state prompt built ({len(current_prompt)} chars)")
                    except Exception as _mc_err:
                        # Fallback to simple injection
                        state_additions = []
                        for _cs in chars:
                            if _cs in _shot_nsm and _shot_nsm[_cs].get("prompt_additions"):
                                state_additions.append(f"{_cs}: {_shot_nsm[_cs]['prompt_additions']}")
                        if state_additions:
                            current_prompt = f"{current_prompt}. State: {'. '.join(state_additions)}"
                        logger.debug(f"Shot {shot_id}: multi-char state prompt fallback: {_mc_err}")

                # Build genre + style-aware negative prompt
                _nsm_neg = ""
                if _shot_nsm and character_slug and character_slug in _shot_nsm:
                    _nsm_neg = _shot_nsm[character_slug].get("negative_additions", "")
                current_negative = _build_video_negative(style_anchor, genre_profile, _nsm_neg)
                shot_steps = shot_dict.get("steps") or 30
                shot_guidance = shot_dict.get("guidance_scale") or 6.0
                shot_seconds = float(shot_dict.get("duration_seconds") or 3)
                shot_use_f1 = shot_dict.get("use_f1") or False
                shot_seed = shot_dict.get("seed")

                # Determine first frame source — priority order:
                # 0. Multi-character FramePack: generate composite source image via IP-Adapter
                # 1. Previous shot's last frame (same character, same scene) — intra-scene continuity
                # 2. Cross-scene continuity frame (same character, prior scene) — inter-scene continuity
                # 3. Auto-assigned source image from approved pool — cold start
                # Wan T2V is text-only — skip source image entirely
                is_multi_char = chars and len(chars) >= 2
                image_filename = None
                first_frame_path = None
                if shot_engine == "wan":
                    logger.info(f"Shot {shot_id}: Wan T2V — no source image needed")
                elif shot_engine == "wan22" and is_multi_char:
                    # Wan 2.2 multi-char: T2V mode, no source image needed
                    logger.info(f"Shot {shot_id}: Wan22 T2V (multi-char) — no source image needed")
                # wan22 solo shots fall through to source image selection below (I2V mode)
                elif is_multi_char and shot_engine in ("framepack", "framepack_f1"):
                    # Multi-character shot: generate composite source image
                    try:
                        from .composite_image import generate_composite_source
                        # Get checkpoint from project's generation style
                        ckpt = "realistic_vision_v51.safetensors"
                        try:
                            style_row = await conn.fetchrow(
                                """SELECT gs.checkpoint_model FROM projects p
                                   JOIN generation_styles gs ON p.default_style = gs.style_name
                                   WHERE p.id = $1""", project_id)
                            if style_row and style_row["checkpoint_model"]:
                                ckpt = style_row["checkpoint_model"]
                                if not ckpt.endswith(".safetensors"):
                                    ckpt += ".safetensors"
                        except Exception:
                            pass

                        logger.info(f"Shot {shot_id}: multi-char ({chars}) — generating composite source image")
                        composite_path = await generate_composite_source(
                            conn, project_id, list(chars), motion_prompt, ckpt
                        )
                        if composite_path and composite_path.exists():
                            first_frame_path = str(composite_path)
                            image_filename = await copy_to_comfyui_input(first_frame_path)
                            logger.info(f"Shot {shot_id}: composite source ready: {composite_path.name}")
                        else:
                            logger.warning(f"Shot {shot_id}: composite generation failed, falling back to solo image")
                            # Fall through to solo image logic below
                            is_multi_char = False
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: composite error: {e}, falling back to solo image")
                        is_multi_char = False

                if not image_filename and shot_engine != "wan" and not (is_multi_char and first_frame_path):
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
                        # Use state-aware selection when NSM states exist (Phase 4)
                        cross_scene_frame = None
                        if character_slug and project_id:
                            _char_target_state = None
                            if _shot_nsm and character_slug in _shot_nsm:
                                _char_target_state = _shot_nsm[character_slug].get("state")
                            if _char_target_state:
                                try:
                                    from packages.narrative_state.continuity import select_continuity_source
                                    cross_scene_frame = await select_continuity_source(
                                        conn, project_id, character_slug,
                                        _char_target_state, scene_id,
                                    )
                                except Exception as _e:
                                    logger.debug(f"NSM continuity selection: {_e}")
                            if not cross_scene_frame:
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
                                if shot_engine == "wan22":
                                    # Wan 2.2: graceful fallback to T2V mode (no ref image)
                                    logger.info(f"Shot {shot_id}: Wan22 no source image → T2V fallback")
                                else:
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

                # Build structured filename prefix: {project}_ep{N}_sc{N}_sh{N}_{engine}_{hash}
                # The hash is the first 8 chars of the shot UUID for disk→DB traceability.
                _ep = f"ep{episode_number:02d}" if episode_number else "ep00"
                _sc = f"sc{scene_number:02d}" if scene_number else "sc00"
                _sh = f"sh{shot_dict.get('shot_number', 0):02d}"
                _shot_hash = str(shot_id).replace("-", "")[:8]
                _file_prefix = f"{project_slug}_{_ep}_{_sc}_{_sh}_{shot_engine}_{_shot_hash}"

                # Persist the final assembled prompts so they're visible in the UI
                await conn.execute(
                    "UPDATE shots SET generation_prompt = $2, generation_negative = $3 WHERE id = $1",
                    shot_id, current_prompt, current_negative,
                )

                # Dispatch to video engine
                if shot_engine == "reference_v2v":
                    # V2V style transfer: use source video clip directly through FramePack V2V
                    _ref_video = shot_dict.get("source_video_path")
                    if not _ref_video or not Path(_ref_video).exists():
                        logger.error(f"Shot {shot_id}: reference_v2v but no source_video_path")
                        await conn.execute(
                            "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                            shot_id, "No source video clip available for reference_v2v",
                        )
                        continue

                    # Auto-detect kohya-format FramePack LoRA for the character
                    # Only attach LoRAs that use lora_unet_ key format (kohya/comfyui)
                    _fp_lora = None
                    if character_slug:
                        for _suffix in ("_framepack_lora", "_framepack"):
                            _lp = Path(f"/opt/ComfyUI/models/loras/{character_slug}{_suffix}.safetensors")
                            if _lp.exists():
                                # Validate LoRA format — must be kohya/comfyui format
                                try:
                                    from safetensors import safe_open
                                    with safe_open(str(_lp), framework="pt") as _sf:
                                        _k0 = list(_sf.keys())[0] if _sf.keys() else ""
                                    if _k0.startswith("lora_unet_"):
                                        _fp_lora = _lp.name
                                    else:
                                        logger.warning(f"Skipping incompatible LoRA {_lp.name} (not kohya format, key: {_k0[:60]})")
                                except Exception as _le:
                                    logger.warning(f"Could not validate LoRA {_lp.name}: {_le}")
                                break

                    from .framepack_refine import refine_wan_video
                    attempt_start = _time_inner.time()
                    refined = await refine_wan_video(
                        wan_video_path=_ref_video,
                        prompt_text=current_prompt,
                        negative_text=current_negative,
                        denoise_strength=0.45,
                        total_seconds=shot_seconds,
                        steps=25,
                        seed=shot_seed,
                        guidance_scale=shot_guidance,
                        lora_name=_fp_lora,
                        output_prefix=_file_prefix,
                    )
                    gen_time = _time_inner.time() - attempt_start

                    if not refined:
                        await conn.execute(
                            "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                            shot_id, "FramePack V2V refinement returned no output",
                        )
                        continue

                    video_path = refined
                    logger.info(f"Shot {shot_id}: reference_v2v done in {gen_time:.0f}s → {Path(refined).name}")

                    # Post-process: interpolation + color grade only (no upscale — already 544x704)
                    try:
                        from .video_postprocess import postprocess_wan_video
                        processed = await postprocess_wan_video(
                            video_path,
                            upscale=False,
                            interpolate=True,
                            color_grade=True,
                            target_fps=30,
                        )
                        if processed:
                            video_path = processed
                            logger.info(f"Shot {shot_id}: post-processed → {Path(processed).name}")
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: post-processing failed: {e}, using raw output")

                    last_frame = await extract_last_frame(video_path)

                    completed_count += 1
                    completed_videos.append(video_path)
                    prev_last_frame = last_frame
                    prev_character = character_slug

                    _review = 'approved' if auto_approve else 'pending_review'
                    await conn.execute("""
                        UPDATE shots SET status = 'completed', output_video_path = $2,
                               last_frame_path = $3, generation_time_seconds = $4,
                               review_status = $5
                        WHERE id = $1
                    """, shot_id, video_path, last_frame, gen_time, _review)

                    if character_slug and last_frame and project_id:
                        try:
                            await _save_continuity_frame(
                                conn, project_id, character_slug,
                                scene_id, shot_id, last_frame,
                                scene_number=scene_number,
                                shot_number=shot_dict.get("shot_number"),
                            )
                        except Exception as e:
                            logger.warning(f"Shot {shot_id}: failed to save continuity frame: {e}")

                    logger.info(f"Shot {shot_id}: generated in {gen_time:.0f}s → {_review}")

                    await event_bus.emit(SHOT_GENERATED, {
                        "shot_id": str(shot_id),
                        "scene_id": str(scene_id),
                        "project_id": project_id,
                        "video_engine": shot_engine,
                        "video_path": video_path,
                        "generation_time_seconds": gen_time,
                        "auto_approve": auto_approve,
                    })
                    continue

                elif shot_engine == "wan22":
                    fps = 16
                    num_frames = max(9, int(shot_seconds * fps) + 1)
                    import hashlib as _hashlib
                    if not shot_seed:
                        _scene_seed_bytes = _hashlib.sha256(str(scene_id).encode()).digest()
                        _scene_base_seed = int.from_bytes(_scene_seed_bytes[:8], "big") % (2**63)
                        shot_seed = _scene_base_seed + (shot_dict.get("shot_number", 0) or 0)
                    wan_cfg = max(shot_guidance, 7.5)  # higher CFG keeps prompt control over LoRA
                    wan_w, wan_h = 480, 720
                    if _project_width and _project_height and _project_width > _project_height:
                        wan_w, wan_h = 720, 480
                    # Get LoRA from engine selector (set by _find_wan_lora)
                    _wan22_lora = engine_sel.lora_name
                    _wan22_lora_str = engine_sel.lora_strength
                    # I2V mode: pass ref_image if we have a source image
                    _wan22_ref = image_filename if image_filename else None
                    logger.info(
                        f"Shot {shot_id}: Wan22 dims={wan_w}x{wan_h} lora={_wan22_lora} "
                        f"ref_image={_wan22_ref is not None} seed={shot_seed} cfg={wan_cfg} frames={num_frames}"
                    )
                    workflow, prefix = build_wan22_workflow(
                        prompt_text=current_prompt, num_frames=num_frames, fps=fps,
                        steps=shot_steps, seed=shot_seed, cfg=wan_cfg,
                        width=wan_w, height=wan_h,
                        negative_text=current_negative,
                        output_prefix=_file_prefix,
                        lora_name=_wan22_lora,
                        lora_strength=_wan22_lora_str,
                        ref_image=_wan22_ref,
                    )
                    comfyui_prompt_id = _submit_wan_workflow(workflow)
                elif shot_engine == "wan":
                    fps = 16
                    num_frames = max(9, int(shot_seconds * fps) + 1)
                    # Use scene-level seed for style consistency across shots
                    # Derive per-shot seed: scene_seed + shot_number
                    import hashlib as _hashlib
                    if not shot_seed:
                        _scene_seed_bytes = _hashlib.sha256(str(scene_id).encode()).digest()
                        _scene_base_seed = int.from_bytes(_scene_seed_bytes[:8], "big") % (2**63)
                        shot_seed = _scene_base_seed + (shot_dict.get("shot_number", 0) or 0)
                    # Higher CFG for better style compliance
                    wan_cfg = max(shot_guidance, 7.5)
                    # Map project resolution to Wan-safe dims (must be multiples of 16)
                    # Wan native is 480x720; scale proportionally for landscape/portrait
                    wan_w, wan_h = 480, 720  # default portrait
                    if _project_width and _project_height and _project_width > _project_height:
                        wan_w, wan_h = 720, 480  # landscape
                    logger.info(f"Shot {shot_id}: Wan dims={wan_w}x{wan_h} (project={_project_width}x{_project_height})")
                    workflow, prefix = build_wan_t2v_workflow(
                        prompt_text=current_prompt, num_frames=num_frames, fps=fps,
                        steps=shot_steps, seed=shot_seed, cfg=wan_cfg,
                        width=wan_w, height=wan_h,
                        use_gguf=True,
                        negative_text=current_negative,
                        output_prefix=_file_prefix,
                    )
                    logger.info(f"Shot {shot_id}: Wan seed={shot_seed} cfg={wan_cfg} frames={num_frames}")
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
                        output_prefix=_file_prefix,
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

                # FramePack V2V refinement for Wan shots (2.1 and 2.2)
                if shot_engine in ("wan", "wan22") and video_path:
                    try:
                        from .framepack_refine import refine_wan_video
                        # Auto-detect kohya-format FramePack LoRA for refinement
                        _fp_lora = None
                        if character_slug:
                            for _suffix in ("_framepack_lora", "_framepack"):
                                _lp = Path(f"/opt/ComfyUI/models/loras/{character_slug}{_suffix}.safetensors")
                                if _lp.exists():
                                    try:
                                        from safetensors import safe_open
                                        with safe_open(str(_lp), framework="pt") as _sf:
                                            _k0 = list(_sf.keys())[0] if _sf.keys() else ""
                                        if _k0.startswith("lora_unet_"):
                                            _fp_lora = _lp.name
                                        else:
                                            logger.warning(f"Skipping incompatible LoRA {_lp.name} for refinement")
                                    except Exception:
                                        pass
                                    break
                        refined = await refine_wan_video(
                            wan_video_path=video_path,
                            prompt_text=current_prompt,
                            negative_text=current_negative,
                            denoise_strength=0.4,
                            total_seconds=shot_seconds,
                            steps=25,
                            seed=shot_seed,
                            guidance_scale=shot_guidance,
                            lora_name=_fp_lora,
                            output_prefix=f"{_file_prefix}_refined",
                        )
                        if refined:
                            video_path = refined
                            logger.info(f"Shot {shot_id}: FramePack V2V refinement done → {Path(refined).name}")
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: V2V refinement failed: {e}, using raw Wan output")

                # Post-process all video outputs: interpolation + upscale + color grade
                # Wan gets upscale (480→960), FramePack gets interpolation + color only
                try:
                    from .video_postprocess import postprocess_wan_video
                    do_upscale = shot_engine in ("wan", "wan22")  # Wan is 480p, needs upscale
                    processed = await postprocess_wan_video(
                        video_path,
                        upscale=do_upscale,
                        interpolate=True,
                        color_grade=True,
                        scale_factor=2,
                        target_fps=30,
                    )
                    if processed:
                        video_path = processed
                        logger.info(f"Shot {shot_id}: post-processed → {Path(processed).name}")
                except Exception as e:
                    logger.warning(f"Shot {shot_id}: post-processing failed: {e}, using raw output")

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

                _review = 'approved' if auto_approve else 'pending_review'
                await conn.execute("""
                    UPDATE shots SET status = 'completed', output_video_path = $2,
                           last_frame_path = $3, generation_time_seconds = $4,
                           review_status = $5
                    WHERE id = $1
                """, shot_id, video_path, last_frame, gen_time, _review)

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

                logger.info(f"Shot {shot_id}: generated in {gen_time:.0f}s → {_review}")

                await event_bus.emit(SHOT_GENERATED, {
                    "shot_id": str(shot_id),
                    "scene_id": str(scene_id),
                    "project_id": project_id,
                    "character_slug": character_slug,
                    "video_engine": shot_engine,
                    "generation_time": gen_time,
                    "video_path": video_path,
                })

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
