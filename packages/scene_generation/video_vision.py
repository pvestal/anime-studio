"""Video vision review — frame extraction and per-frame vision model assessment.

Split from video_qc.py to isolate vision model interaction from QC orchestration.
"""

import asyncio
import base64
import json
import logging
from pathlib import Path

from packages.core.config import OLLAMA_URL, VISION_MODEL

logger = logging.getLogger(__name__)

# Known issue categories the vision model can identify
KNOWN_ISSUES = [
    "artifact_flicker", "blurry", "wrong_character", "bad_anatomy",
    "frozen_motion", "wrong_action", "poor_lighting", "text_watermark",
    "color_shift",
]


async def extract_review_frames(video_path: str, count: int = 3) -> list[str]:
    """Extract frames at start (0.1s), midpoint, and end (-0.1s) via ffmpeg.

    Returns list of PNG paths stored alongside the video as _qc_frame_N.png.
    """
    video = Path(video_path)
    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    # Get video duration
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    duration = float(stdout.decode().strip()) if stdout.decode().strip() else 3.0

    # Calculate timestamps: 0.1s, midpoint, duration-0.1s
    timestamps = [0.1]
    if count >= 2:
        timestamps.append(max(0.2, duration / 2))
    if count >= 3:
        timestamps.append(max(0.3, duration - 0.1))

    frame_paths = []
    base = video_path.rsplit(".", 1)[0]

    for i, ts in enumerate(timestamps[:count]):
        out_path = f"{base}_qc_frame_{i}.png"
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-ss", str(ts), "-i", video_path,
            "-vframes", "1", "-q:v", "2", out_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0 and Path(out_path).exists():
            frame_paths.append(out_path)
        else:
            logger.warning(f"Frame extraction failed at {ts}s: {stderr.decode()[-200:]}")

    return frame_paths


async def _vision_review_single_frame(
    frame_path: str,
    motion_prompt: str,
    character_slug: str | None = None,
    source_image_path: str | None = None,
) -> dict:
    """Send frame + optional source image to vision model for comparative assessment.

    When source_image_path is provided, sends BOTH images and asks the model to
    compare the generated frame against the source (character match, art style,
    motion execution, technical quality). This produces much wider score distributions
    than single-image "rate quality 1-10" prompts.

    When no source image (e.g. Wan T2V), falls back to single-image review.

    Returns dict with character_match, style_match, motion_execution,
    technical_quality (all 1-10), and issues list.
    """
    import urllib.request

    with open(frame_path, "rb") as f:
        frame_b64 = base64.b64encode(f.read()).decode()

    images = [frame_b64]
    char_context = f" The character should be '{character_slug}'." if character_slug else ""
    issue_list = ", ".join(KNOWN_ISSUES)

    # Comparative prompt when source image is available
    if source_image_path and Path(source_image_path).exists():
        with open(source_image_path, "rb") as f:
            source_b64 = base64.b64encode(f.read()).decode()
        # Source image first, generated frame second
        images = [source_b64, frame_b64]

        prompt = (
            f"You are comparing a SOURCE IMAGE (image 1) with a GENERATED VIDEO FRAME (image 2). "
            f"The video was supposed to animate the source image with this action: \"{motion_prompt}\".{char_context}\n\n"
            f"Score each category 1-10 by COMPARING the two images:\n"
            f"- character_match: does the generated frame preserve the character's identity, face, hair, clothing from the source? (1=completely different person, 10=perfect match)\n"
            f"- style_match: does the art style, color palette, line quality match the source? (1=totally different style, 10=seamless)\n"
            f"- motion_execution: does the frame show the described action naturally? (1=frozen/wrong action, 10=perfect motion)\n"
            f"- technical_quality: sharpness, no artifacts, no glitches, good anatomy (1=broken, 10=flawless)\n\n"
            f"Be STRICT — a score of 7+ means genuinely good. 5 means mediocre. 3 means bad.\n\n"
            f"Also list any issues from this set: [{issue_list}]\n\n"
            f"Reply in EXACTLY this JSON format, nothing else:\n"
            f'{{"character_match": N, "style_match": N, "motion_execution": N, '
            f'"technical_quality": N, "issues": ["issue1", "issue2"]}}'
        )
    else:
        # Fallback: single-image review (Wan T2V or missing source)
        prompt = (
            f"You are reviewing an anime video frame. The intended motion/action is: \"{motion_prompt}\".{char_context}\n\n"
            f"Score each category 1-10. Be STRICT — 7+ means genuinely good, 5 means mediocre, 3 means bad:\n"
            f"- character_match: character appears on-model and correct (if no reference, score anatomy/consistency)\n"
            f"- style_match: art style is consistent and appealing\n"
            f"- motion_execution: does the frame match the described motion/action\n"
            f"- technical_quality: sharpness, no artifacts, no glitches\n\n"
            f"Also list any issues from this set: [{issue_list}]\n\n"
            f"Reply in EXACTLY this JSON format, nothing else:\n"
            f'{{"character_match": N, "style_match": N, "motion_execution": N, '
            f'"technical_quality": N, "issues": ["issue1", "issue2"]}}'
        )

    payload = json.dumps({
        "model": VISION_MODEL,
        "prompt": prompt,
        "images": images,
        "stream": False,
        "options": {"temperature": 0.1},
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        resp = urllib.request.urlopen(req, timeout=90)
        result = json.loads(resp.read())
        text = result.get("response", "").strip()

        # Extract JSON from response (may have markdown fences)
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        parsed = json.loads(text)

        # Validate and clamp scores
        scores = {}
        for key in ("character_match", "style_match", "motion_execution", "technical_quality"):
            val = parsed.get(key, 5)
            scores[key] = max(1, min(10, int(val)))

        # Validate issues
        issues = [i for i in parsed.get("issues", []) if i in KNOWN_ISSUES]

        return {**scores, "issues": issues}

    except Exception as e:
        logger.warning(f"Vision review failed for {frame_path}: {e}")
        return {
            "character_match": 5,
            "style_match": 5,
            "motion_execution": 5,
            "technical_quality": 5,
            "issues": [],
        }


async def review_video_frames(
    frame_paths: list[str],
    motion_prompt: str,
    character_slug: str | None = None,
    source_image_path: str | None = None,
) -> dict:
    """Review multiple frames and aggregate scores.

    When source_image_path is provided, each frame is compared against
    the source for character/style fidelity (comparative scoring).

    Returns:
        {
            overall_score: float (0-1),
            issues: list[str],
            per_frame: list[dict],
            category_averages: dict,
        }
    """
    if not frame_paths:
        return {"overall_score": 0.5, "issues": [], "per_frame": []}

    # Review frames sequentially (Ollama single-model queue)
    per_frame = []
    for fp in frame_paths:
        result = await _vision_review_single_frame(
            fp, motion_prompt, character_slug, source_image_path,
        )
        per_frame.append(result)

    # Aggregate: weighted average across frames, then weighted category mix
    # character_match + style_match weighted higher when comparing against source
    if source_image_path and Path(source_image_path).exists():
        weights = {
            "character_match": 0.30,
            "style_match": 0.20,
            "motion_execution": 0.25,
            "technical_quality": 0.25,
        }
    else:
        weights = {
            "character_match": 0.20,
            "style_match": 0.15,
            "motion_execution": 0.30,
            "technical_quality": 0.35,
        }

    category_avgs = {}
    for key in weights:
        vals = [fr[key] for fr in per_frame]
        category_avgs[key] = sum(vals) / len(vals)

    # Weighted sum normalized to 0-1 (scores are 1-10)
    raw_score = sum(category_avgs[k] * w for k, w in weights.items())
    overall_score = round((raw_score - 1) / 9, 2)  # map 1-10 -> 0-1
    overall_score = max(0.0, min(1.0, overall_score))

    # Union of all frame issues
    all_issues = set()
    for fr in per_frame:
        all_issues.update(fr.get("issues", []))

    return {
        "overall_score": overall_score,
        "issues": sorted(all_issues),
        "per_frame": per_frame,
        "category_averages": {k: round(v, 1) for k, v in category_avgs.items()},
    }
