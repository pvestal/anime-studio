"""Smart source image selection for scene shots.

Scores approved training images against shot requirements (pose, quality,
diversity) so the UI can recommend the best source image for each shot.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# --- Pose-to-shot mapping ---

SHOT_POSE_MAP: dict[str, list[str]] = {
    "close-up": ["close-up portrait", "upper body portrait", "head tilt"],
    "wide": ["full body", "standing front", "walking pose"],
    "establishing": ["full body", "standing front", "dramatic lighting"],
    "medium": ["three-quarter view", "standing front", "arms crossed", "sitting"],
    "action": ["dynamic pose", "running", "crouching"],
    "extreme_close": ["close-up portrait", "upper body portrait"],
}

CAMERA_ANGLE_BONUS: dict[str, list[str]] = {
    "low": ["looking up", "crouching"],
    "high": ["looking down"],
    "dutch": ["dramatic lighting"],
}

# Neutral defaults for missing data
_DEFAULT_POSE_SCORE = 0.3
_DEFAULT_QUALITY_SCORE = 0.5
_DEFAULT_VISION_SCORE = 0.5

# Composite weights (must sum to 1.0)
_W_POSE = 0.35
_W_QUALITY = 0.25
_W_VISION = 0.15
_W_DIVERSITY = 0.10
_W_VIDEO_HISTORY = 0.15

# Default when no video history exists (neutral — doesn't penalize or boost)
_DEFAULT_VIDEO_HISTORY_SCORE = 0.5

# Action keywords for description matching
_ACTION_KEYWORDS = {
    "walking": ["walking", "stride", "stroll", "standing"],
    "running": ["running", "sprint", "dash", "dynamic"],
    "fighting": ["fighting", "combat", "sword", "dynamic pose", "attack"],
    "sitting": ["sitting", "seated", "chair", "bench"],
    "talking": ["upper body", "portrait", "three-quarter"],
    "looking": ["portrait", "close-up", "face"],
}


def batch_read_metadata(
    base_path: Path, slug: str, image_names: list[str],
) -> dict[str, dict[str, Any]]:
    """Read .meta.json for each image, skipping missing files."""
    result: dict[str, dict[str, Any]] = {}
    images_dir = base_path / slug / "images"
    for name in image_names:
        meta_path = images_dir / f"{name}.meta.json"
        if not meta_path.exists():
            result[name] = {}
            continue
        try:
            with open(meta_path) as f:
                result[name] = json.load(f)
        except (json.JSONDecodeError, OSError):
            result[name] = {}
    return result


def score_pose_match(
    image_pose: str | None, shot_type: str, camera_angle: str | None,
) -> float:
    """Score 0-1 how well the image pose matches the shot type."""
    if not image_pose:
        return _DEFAULT_POSE_SCORE

    pose_lower = image_pose.lower()
    ideal_poses = SHOT_POSE_MAP.get(shot_type, [])
    if not ideal_poses:
        return _DEFAULT_POSE_SCORE

    # Exact or substring match against ideal poses
    best = 0.0
    for ideal in ideal_poses:
        if ideal in pose_lower or pose_lower in ideal:
            best = max(best, 1.0)
        elif any(word in pose_lower for word in ideal.split()):
            best = max(best, 0.6)

    # Camera angle bonus
    if camera_angle and camera_angle in CAMERA_ANGLE_BONUS:
        for bonus_pose in CAMERA_ANGLE_BONUS[camera_angle]:
            if bonus_pose in pose_lower:
                best = min(best + 0.15, 1.0)
                break

    return best if best > 0 else _DEFAULT_POSE_SCORE


def score_quality(meta: dict[str, Any]) -> float:
    """Score 0-1 from quality_score or vision_review composite."""
    qs = meta.get("quality_score")
    if qs is not None:
        return max(0.0, min(1.0, float(qs)))

    vr = meta.get("vision_review")
    if isinstance(vr, dict):
        tv = vr.get("training_value")
        if tv is not None:
            return max(0.0, min(1.0, float(tv) / 10.0))

    return _DEFAULT_QUALITY_SCORE


def score_vision_match(meta: dict[str, Any]) -> float:
    """Score 0-1 from vision_review character_match + clarity."""
    vr = meta.get("vision_review")
    if not isinstance(vr, dict):
        return _DEFAULT_VISION_SCORE

    cm = vr.get("character_match")
    cl = vr.get("clarity")
    if cm is not None and cl is not None:
        return max(0.0, min(1.0, (float(cm) + float(cl)) / 20.0))

    return _DEFAULT_VISION_SCORE


def score_diversity(image_name: str, already_used: set[str]) -> float:
    """1.0 if not yet used, 0.0 if already assigned to another shot."""
    return 0.0 if image_name in already_used else 1.0


def score_video_effectiveness(
    image_name: str,
    video_scores: dict[str, float] | None,
) -> float:
    """Score 0-1 based on historical video quality when using this image.

    Args:
        image_name: The image filename.
        video_scores: Pre-fetched dict of {image_name: avg_video_quality_score}.
                      None or empty means no history available.
    """
    if not video_scores:
        return _DEFAULT_VIDEO_HISTORY_SCORE
    avg = video_scores.get(image_name)
    if avg is None:
        return _DEFAULT_VIDEO_HISTORY_SCORE
    return max(0.0, min(1.0, avg))


def score_description_match(
    meta: dict[str, Any],
    motion_prompt: str | None,
) -> float:
    """Score 0-1 based on keyword overlap between shot motion_prompt and image caption.

    Checks image caption/description from .meta.json against the shot's motion_prompt.
    """
    if not motion_prompt:
        return 0.5  # neutral

    prompt_lower = motion_prompt.lower()

    # Get image description from meta
    caption = ""
    vr = meta.get("vision_review")
    if isinstance(vr, dict):
        caption = (vr.get("description") or "").lower()
    if not caption:
        caption = (meta.get("caption") or "").lower()
    if not caption:
        return 0.5  # no caption, neutral

    # Direct word overlap
    prompt_words = set(prompt_lower.split())
    caption_words = set(caption.split())
    common = prompt_words & caption_words
    # Remove stopwords
    stopwords = {"the", "a", "an", "in", "on", "at", "to", "of", "and", "is", "with", "for"}
    common -= stopwords

    overlap_score = min(len(common) / max(len(prompt_words - stopwords), 1), 1.0)

    # Action keyword bonus
    action_bonus = 0.0
    for action, related_poses in _ACTION_KEYWORDS.items():
        if action in prompt_lower:
            for pose in related_poses:
                if pose in caption:
                    action_bonus = 0.3
                    break
            if action_bonus > 0:
                break

    return min(1.0, 0.3 + overlap_score * 0.4 + action_bonus)


def _build_reason(
    pose_score: float, quality_score: float, image_pose: str | None,
    shot_type: str,
) -> str:
    """Build a human-readable reason string."""
    parts = []
    if pose_score >= 0.8 and image_pose:
        parts.append(f'pose "{image_pose}" matches {shot_type}')
    elif pose_score >= 0.5 and image_pose:
        parts.append(f'pose "{image_pose}" partially matches {shot_type}')
    if quality_score >= 0.8:
        parts.append("high quality")
    elif quality_score >= 0.6:
        parts.append("good quality")
    return "; ".join(parts) if parts else "best available"


def recommend_images_for_shot(
    slug: str,
    images_meta: dict[str, dict[str, Any]],
    shot_type: str,
    camera_angle: str | None,
    already_used: set[str],
    top_n: int = 5,
    video_scores: dict[str, float] | None = None,
    motion_prompt: str | None = None,
) -> list[dict[str, Any]]:
    """Score and rank images for a single shot.

    Args:
        video_scores: Pre-fetched {image_name: avg_video_quality} for this character.
        motion_prompt: Shot's motion prompt for description matching.

    Returns sorted list of {image_name, slug, score, pose, quality_score, reason}.
    """
    scored: list[dict[str, Any]] = []

    for name, meta in images_meta.items():
        image_pose = meta.get("pose")
        p = score_pose_match(image_pose, shot_type, camera_angle)
        q = score_quality(meta)
        v = score_vision_match(meta)
        d = score_diversity(name, already_used)
        vh = score_video_effectiveness(name, video_scores)
        dm = score_description_match(meta, motion_prompt)

        # Redistribute description match weight from pose when motion_prompt provided
        if motion_prompt:
            w_pose = _W_POSE - 0.05
            w_desc = 0.05
        else:
            w_pose = _W_POSE
            w_desc = 0.0

        composite = (
            w_pose * p
            + _W_QUALITY * q
            + _W_VISION * v
            + _W_DIVERSITY * d
            + _W_VIDEO_HISTORY * vh
            + w_desc * dm
        )

        scored.append({
            "image_name": name,
            "slug": slug,
            "score": round(composite, 3),
            "pose": image_pose,
            "quality_score": round(q, 3),
            "video_history_score": round(vh, 3),
            "reason": _build_reason(p, q, image_pose, shot_type),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


def recommend_for_scene(
    base_path: Path,
    shots: list[dict[str, Any]],
    approved_images: dict[str, list[str]],
    top_n: int = 5,
    video_scores: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    """Generate per-shot recommendations for an entire scene.

    Args:
        base_path: Dataset base directory.
        shots: List of shot dicts with shot_type, camera_angle,
               characters_present, source_image_path, id, shot_number,
               and optionally motion_prompt.
        approved_images: {slug: [image_name, ...]} of approved images.
        top_n: Max recommendations per shot.
        video_scores: {slug: {image_name: avg_quality}} from source_image_effectiveness.

    Returns:
        [{shot_id, shot_number, shot_type, camera_angle,
          current_source, recommendations: [...]}]
    """
    # Batch-read metadata for all characters
    all_meta: dict[str, dict[str, dict[str, Any]]] = {}
    for slug, images in approved_images.items():
        all_meta[slug] = batch_read_metadata(base_path, slug, images)

    # Track already-used images for diversity scoring
    already_used: set[str] = set()

    # Seed already_used with existing assignments
    for shot in shots:
        src = shot.get("source_image_path") or ""
        if src:
            # Extract filename from "slug/images/filename.png"
            parts = src.split("/")
            if parts:
                already_used.add(parts[-1])

    results: list[dict[str, Any]] = []

    for shot in shots:
        shot_type = shot.get("shot_type") or "medium"
        camera_angle = shot.get("camera_angle")
        motion_prompt = shot.get("motion_prompt")
        chars = shot.get("characters_present") or []

        # Determine which slugs to score (prefer characters_present, fall back to all)
        target_slugs = [s for s in chars if s in all_meta] if chars else list(all_meta.keys())
        if not target_slugs:
            target_slugs = list(all_meta.keys())

        # Collect recommendations across matching characters
        combined: list[dict[str, Any]] = []
        for slug in target_slugs:
            meta = all_meta.get(slug, {})
            if not meta:
                continue
            slug_video_scores = (video_scores or {}).get(slug)
            recs = recommend_images_for_shot(
                slug, meta, shot_type, camera_angle, already_used, top_n,
                video_scores=slug_video_scores,
                motion_prompt=motion_prompt,
            )
            combined.extend(recs)

        # Re-sort combined and take top_n
        combined.sort(key=lambda x: x["score"], reverse=True)
        top_recs = combined[:top_n]

        # Mark top pick as used for diversity in subsequent shots
        if top_recs:
            already_used.add(top_recs[0]["image_name"])

        results.append({
            "shot_id": shot.get("id"),
            "shot_number": shot.get("shot_number"),
            "shot_type": shot_type,
            "camera_angle": camera_angle,
            "current_source": shot.get("source_image_path"),
            "recommendations": top_recs,
        })

    return results
