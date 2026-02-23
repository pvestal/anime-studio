"""CLIP-based character classification — visual similarity matching against reference images.

Replaces the vision-model approach (gemma3:12b + text roster) which hallucinated characters
and took ~18s/frame. This uses CLIP image embeddings for ~50ms/frame on CPU with much
higher accuracy.

Pipeline:
  1. Build reference embeddings from approved character images
  2. Batch-embed candidate frames
  3. Cosine similarity matching with thresholds
  4. Temporal verification pass (rescue/resolve ambiguous frames)
"""

import json
import logging
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from packages.core.config import BASE_PATH

logger = logging.getLogger(__name__)

# --- Thresholds ---
MATCH_THRESHOLD = 0.75
AMBIGUITY_MARGIN = 0.05
RESCUE_THRESHOLD = 0.70
HIGH_CONFIDENCE = 0.85

# --- Singleton model ---
_model = None
_preprocess = None
_lock = threading.Lock()


def _get_device():
    """Return cuda:0 (NVIDIA) if available, else CPU. CLIP is ~400MB — fits alongside ComfyUI."""
    import torch
    return torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")


def _load_clip_model():
    """Lazy-load CLIP ViT-L-14 on GPU if available. Thread-safe singleton.

    Returns (model, preprocess_fn). Falls back to ViT-B-32 if ViT-L fails.
    """
    global _model, _preprocess
    if _model is not None:
        return _model, _preprocess

    with _lock:
        if _model is not None:
            return _model, _preprocess

        import open_clip
        import torch

        try:
            model, _, preprocess = open_clip.create_model_and_transforms(
                "ViT-L-14", pretrained="laion2b_s32b_b82k"
            )
            logger.info("Loaded CLIP ViT-L-14 (768-dim)")
        except Exception as e:
            logger.warning(f"ViT-L-14 failed ({e}), falling back to ViT-B-32")
            model, _, preprocess = open_clip.create_model_and_transforms(
                "ViT-B-32", pretrained="laion2b_s34b_b79k"
            )
            logger.info("Loaded CLIP ViT-B-32 (512-dim)")

        device = _get_device()
        model = model.eval().to(device)
        logger.info(f"CLIP model on {device}")
        _model = model
        _preprocess = preprocess
        return _model, _preprocess


def _embed_image(path: Path | str) -> np.ndarray:
    """Embed a single image -> L2-normalized vector."""
    import torch
    from PIL import Image

    model, preprocess = _load_clip_model()
    device = _get_device()
    path = Path(path)

    img = Image.open(path).convert("RGB")
    tensor = preprocess(img).unsqueeze(0).to(device)

    with torch.no_grad():
        features = model.encode_image(tensor)
        features = features / features.norm(dim=-1, keepdim=True)

    return features.squeeze(0).cpu().numpy()


def _embed_images_batch(paths: list[Path], batch_size: int = 16) -> np.ndarray:
    """Batch embed images. Returns (N, dim) array of L2-normalized vectors."""
    import torch
    from PIL import Image

    model, preprocess = _load_clip_model()

    all_features = []
    for i in range(0, len(paths), batch_size):
        batch_paths = paths[i:i + batch_size]
        tensors = []
        for p in batch_paths:
            try:
                img = Image.open(p).convert("RGB")
                tensors.append(preprocess(img))
            except Exception as e:
                logger.warning(f"Failed to load {p}: {e}")
                # Use a zero tensor as placeholder — will get low similarity
                tensors.append(preprocess(Image.new("RGB", (224, 224))))

        batch = torch.stack(tensors).to(_get_device())
        with torch.no_grad():
            features = model.encode_image(batch)
            features = features / features.norm(dim=-1, keepdim=True)
        all_features.append(features.cpu().numpy())

    return np.concatenate(all_features, axis=0) if all_features else np.empty((0, 0))


def build_reference_embeddings(
    project_name: str,
    character_slugs: list[str] | None = None,
    force_rebuild: bool = False,
) -> dict[str, np.ndarray]:
    """Build CLIP embeddings for each character's reference images.

    Sources (in priority order):
      1. datasets/{slug}/reference_images/ — curated references
      2. Approved images from datasets/{slug}/images/ via approval_status.json

    Returns dict mapping slug -> (N, dim) array of reference embeddings.
    Caches to datasets/.clip_cache/{project}_refs.npz.
    """
    import re

    project_slug = re.sub(r"[^a-z0-9_]", "", project_name.lower().replace(" ", "_"))
    cache_dir = BASE_PATH / ".clip_cache"
    cache_file = cache_dir / f"{project_slug}_refs.npz"

    # Try cache first
    if not force_rebuild and cache_file.exists():
        try:
            data = np.load(cache_file, allow_pickle=False)
            refs = {key: data[key] for key in data.files}
            if refs:
                logger.info(f"Loaded cached reference embeddings: {', '.join(f'{k}:{v.shape[0]}' for k, v in refs.items())}")
                return refs
        except Exception as e:
            logger.warning(f"Cache load failed: {e}")

    # Discover character slugs from DB if not provided
    if character_slugs is None:
        character_slugs = _get_project_slugs(project_name)

    refs: dict[str, np.ndarray] = {}

    for slug in character_slugs:
        ref_paths: list[Path] = []

        # Priority 1: curated reference_images/
        ref_dir = BASE_PATH / slug / "reference_images"
        if ref_dir.is_dir():
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                ref_paths.extend(ref_dir.glob(ext))
            # Exclude _rejected subfolder
            ref_paths = [p for p in ref_paths if "_rejected" not in str(p)]

        # Priority 2: approved images from images/
        approval_file = BASE_PATH / slug / "approval_status.json"
        if approval_file.exists():
            try:
                approval = json.loads(approval_file.read_text())
                images_dir = BASE_PATH / slug / "images"
                for filename, status in approval.items():
                    if status == "approved":
                        img_path = images_dir / filename
                        if img_path.exists() and img_path not in ref_paths:
                            ref_paths.append(img_path)
            except (json.JSONDecodeError, IOError):
                pass

        if not ref_paths:
            logger.warning(f"No reference images for {slug}")
            continue

        embeddings = _embed_images_batch(ref_paths)
        if embeddings.size > 0:
            refs[slug] = embeddings
            logger.info(f"  {slug}: {len(ref_paths)} references -> {embeddings.shape}")

    # Save cache
    if refs:
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.savez(cache_file, **refs)
        logger.info(f"Cached reference embeddings to {cache_file}")

    return refs


def classify_frame_clip(
    frame_embedding: np.ndarray,
    ref_embeddings: dict[str, np.ndarray],
) -> dict:
    """Classify a single frame against reference embeddings via cosine similarity.

    Multi-character aware: returns ALL characters above threshold, not just the top one.
    A frame of Mario riding Yoshi returns both.

    Returns:
        {matched_slug (best), matched_slugs (all above threshold), similarity,
         all_scores, ambiguous, runner_up_slug, runner_up_similarity}
    """
    all_scores: dict[str, float] = {}

    for slug, refs in ref_embeddings.items():
        # Cosine similarity — embeddings are already L2-normalized
        similarities = frame_embedding @ refs.T
        # Use max similarity across all reference images for this character
        all_scores[slug] = float(np.max(similarities))

    if not all_scores:
        return {
            "matched_slug": None, "matched_slugs": [], "similarity": 0.0,
            "all_scores": {}, "ambiguous": False,
            "runner_up_slug": None, "runner_up_similarity": 0.0,
        }

    # Sort by score descending
    ranked = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
    best_slug, best_score = ranked[0]
    runner_slug = ranked[1][0] if len(ranked) > 1 else None
    runner_score = ranked[1][1] if len(ranked) > 1 else 0.0

    # All characters above threshold — multi-character assignment
    matched_slugs = [slug for slug, score in ranked if score >= MATCH_THRESHOLD]

    matched = best_slug if best_score >= MATCH_THRESHOLD else None
    ambiguous = (best_score - runner_score) < AMBIGUITY_MARGIN if matched else False

    return {
        "matched_slug": matched,
        "matched_slugs": matched_slugs,
        "similarity": best_score,
        "all_scores": all_scores,
        "ambiguous": ambiguous,
        "runner_up_slug": runner_slug,
        "runner_up_similarity": runner_score,
    }


def classify_frames_batch(
    frame_paths: list[Path],
    ref_embeddings: dict[str, np.ndarray],
    batch_size: int = 16,
) -> list[dict]:
    """Batch classify frames against references. Returns list of classification dicts."""
    frame_embeddings = _embed_images_batch(frame_paths, batch_size=batch_size)
    results = []
    for i, embedding in enumerate(frame_embeddings):
        result = classify_frame_clip(embedding, ref_embeddings)
        result["frame_path"] = str(frame_paths[i])
        result["frame_index"] = i
        results.append(result)
    return results


def verify_assignments(classifications: list[dict]) -> list[dict]:
    """Second-pass verification using temporal context.

    - Unmatched frames between two same-character frames -> rescue at lower threshold
    - Ambiguous frames -> resolve using neighbor agreement
    - High-confidence frames -> mark as confirmed
    """
    n = len(classifications)
    if n == 0:
        return classifications

    for i, c in enumerate(classifications):
        # Mark high-confidence as confirmed
        if c["matched_slug"] and c["similarity"] >= HIGH_CONFIDENCE:
            c["verified"] = True
            c["verification_reason"] = "high_confidence"
            continue

        # Already matched — keep as-is
        if c["matched_slug"] and not c["ambiguous"]:
            c["verified"] = True
            c["verification_reason"] = "clear_match"
            continue

        # Try to rescue unmatched frames using neighbor context
        if c["matched_slug"] is None and c["similarity"] >= RESCUE_THRESHOLD:
            # Look at neighbors (within 3 frames)
            neighbor_slugs = []
            for offset in (-3, -2, -1, 1, 2, 3):
                j = i + offset
                if 0 <= j < n and classifications[j]["matched_slug"]:
                    neighbor_slugs.append(classifications[j]["matched_slug"])

            if neighbor_slugs:
                # Find the most common neighbor slug
                from collections import Counter
                most_common = Counter(neighbor_slugs).most_common(1)[0]
                slug, count = most_common
                if count >= 2:
                    # Check if this frame has a reasonable score for that character
                    char_score = c["all_scores"].get(slug, 0.0)
                    if char_score >= RESCUE_THRESHOLD:
                        c["matched_slug"] = slug
                        c["similarity"] = char_score
                        c["verified"] = True
                        c["verification_reason"] = f"rescued_by_neighbors({count})"
                        continue

        # Resolve ambiguous frames using neighbors
        if c["ambiguous"] and c["matched_slug"]:
            neighbor_slugs = []
            for offset in (-2, -1, 1, 2):
                j = i + offset
                if 0 <= j < n and classifications[j]["matched_slug"]:
                    neighbor_slugs.append(classifications[j]["matched_slug"])

            if c["matched_slug"] in neighbor_slugs:
                c["ambiguous"] = False
                c["verified"] = True
                c["verification_reason"] = "neighbor_confirmed"
            elif c.get("runner_up_slug") in neighbor_slugs:
                c["matched_slug"] = c["runner_up_slug"]
                c["similarity"] = c["runner_up_similarity"]
                c["ambiguous"] = False
                c["verified"] = True
                c["verification_reason"] = "neighbor_override"
            else:
                c["verified"] = False
                c["verification_reason"] = "ambiguous_unresolved"
            continue

        c["verified"] = c["matched_slug"] is not None
        c["verification_reason"] = "default"

    return classifications


def run_clip_pipeline(
    frame_paths: list[Path],
    project_name: str,
    character_slugs: list[str] | None = None,
    target_slug: str | None = None,
    video_path: Path | str | None = None,
    clip_duration: float = 2.0,
    extract_clips: bool = False,
    progress_callback: Callable | None = None,
    frame_timestamps: list[float] | None = None,
) -> dict:
    """Orchestrate the full CLIP classification pipeline.

    Phases:
      1. Build/load reference embeddings
      2. Batch classify all frames
      3. Verification pass
      4. (Optional) Extract video clips for target character

    Args:
        frame_paths: List of frame image paths
        project_name: Project name for reference lookup
        character_slugs: Character slugs to classify against (None = all project chars)
        target_slug: Filter results to this character
        video_path: Source video for clip extraction
        clip_duration: Duration of extracted clips in seconds
        extract_clips: Whether to extract video clips
        progress_callback: fn(phase, detail) for progress tracking
        frame_timestamps: Optional timestamps for each frame (parallel to frame_paths)

    Returns dict with phase results, per-character counts, and clips.
    """
    def _progress(phase: str, detail: str = ""):
        if progress_callback:
            progress_callback(phase, detail)
        logger.info(f"[CLIP pipeline] {phase}: {detail}")

    # Phase 1: Build reference embeddings
    _progress("building_references", f"project={project_name}")
    refs = build_reference_embeddings(project_name, character_slugs)
    if not refs:
        return {"error": "No reference embeddings could be built", "per_character": {}}

    _progress("building_references", f"Built refs for {len(refs)} characters")

    # Phase 2: Batch classify
    _progress("classifying", f"{len(frame_paths)} frames")
    classifications = classify_frames_batch(frame_paths, refs)

    # Attach timestamps if provided
    if frame_timestamps and len(frame_timestamps) == len(classifications):
        for cls, ts in zip(classifications, frame_timestamps):
            cls["timestamp"] = ts

    _progress("classifying", f"Done — {sum(1 for c in classifications if c['matched_slug'])} matched")

    # Phase 3: Verification pass
    _progress("verifying", "temporal context verification")
    classifications = verify_assignments(classifications)
    verified_count = sum(1 for c in classifications if c.get("verified"))
    _progress("verifying", f"Done — {verified_count} verified")

    # Count per character — use matched_slugs for multi-character frames
    per_character: dict[str, int] = {}
    for c in classifications:
        for slug in c.get("matched_slugs", []):
            per_character[slug] = per_character.get(slug, 0) + 1
        # Fallback if matched_slugs empty but matched_slug set (rescue/verify)
        if not c.get("matched_slugs") and c.get("matched_slug"):
            slug = c["matched_slug"]
            per_character[slug] = per_character.get(slug, 0) + 1

    # Filter to target if specified — match if target in matched_slugs
    target_results = classifications
    if target_slug:
        target_results = [
            c for c in classifications
            if target_slug in c.get("matched_slugs", []) or c.get("matched_slug") == target_slug
        ]

    # Phase 4: Extract clips (optional)
    clips = []
    if extract_clips and video_path and target_slug and frame_timestamps:
        _progress("extracting_clips", f"for {target_slug}")
        try:
            from packages.lora_training.clip_extraction import extract_character_clips
            clips = extract_character_clips(
                video_path=Path(video_path),
                classifications=classifications,
                target_slug=target_slug,
                output_dir=BASE_PATH / "_clips" / target_slug,
                clip_duration=clip_duration,
            )
            _progress("extracting_clips", f"Extracted {len(clips)} clips")
        except Exception as e:
            logger.error(f"Clip extraction failed: {e}")
            _progress("extracting_clips", f"Failed: {e}")

    _progress("complete", f"{sum(per_character.values())} total matches across {len(per_character)} characters")

    return {
        "classifications": classifications,
        "target_results": target_results,
        "per_character": per_character,
        "total_frames": len(frame_paths),
        "total_matched": sum(per_character.values()),
        "total_unmatched": len(frame_paths) - sum(per_character.values()),
        "clips": clips,
        "reference_characters": list(refs.keys()),
        "reference_counts": {k: v.shape[0] for k, v in refs.items()},
    }


def _get_project_slugs(project_name: str) -> list[str]:
    """Get character slugs for a project from the DB cache."""
    try:
        from packages.core.db import _char_project_cache
        return [
            slug for slug, info in _char_project_cache.items()
            if info.get("project_name") == project_name
        ]
    except Exception:
        # Fallback: scan datasets directory
        slugs = []
        if BASE_PATH.is_dir():
            for d in BASE_PATH.iterdir():
                if d.is_dir() and not d.name.startswith("_"):
                    slugs.append(d.name)
        return slugs
