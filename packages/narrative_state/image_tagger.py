"""Image visual tagging — extract clothing, expression, pose etc. from approved images.

Uses Ollama gemma3:12b vision to analyze images and store structured tags
in the image_visual_tags table.
"""

import base64
import json
import logging
from pathlib import Path

from packages.core.config import BASE_PATH
from packages.core.db import connect_direct

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma3:12b"
OLLAMA_TIMEOUT = 90


async def tag_image_visual_properties(
    image_path: str | Path,
    character_slug: str,
    design_prompt: str | None = None,
    project_name: str | None = None,
) -> dict | None:
    """Analyze a single image and extract visual properties via Ollama vision.

    Returns the tag dict on success, None on failure.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        logger.warning(f"Image not found: {image_path}")
        return None

    # Read and encode image
    image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    image_name = image_path.name

    prompt = _build_tag_prompt(character_slug, design_prompt)

    tags = await _call_ollama_vision(prompt, image_data)
    if not tags:
        return None

    # Persist to DB
    conn = await connect_direct()
    try:
        await conn.execute("""
            INSERT INTO image_visual_tags
                (character_slug, project_name, image_name, clothing, hair_state,
                 expression, body_state, pose, accessories, setting,
                 quality_score, nsfw_level, face_visible, full_body,
                 tagged_by, confidence)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            ON CONFLICT (character_slug, image_name) DO UPDATE SET
                clothing = EXCLUDED.clothing,
                hair_state = EXCLUDED.hair_state,
                expression = EXCLUDED.expression,
                body_state = EXCLUDED.body_state,
                pose = EXCLUDED.pose,
                accessories = EXCLUDED.accessories,
                setting = EXCLUDED.setting,
                quality_score = EXCLUDED.quality_score,
                nsfw_level = EXCLUDED.nsfw_level,
                face_visible = EXCLUDED.face_visible,
                full_body = EXCLUDED.full_body,
                tagged_by = EXCLUDED.tagged_by,
                confidence = EXCLUDED.confidence
        """,
            character_slug, project_name, image_name,
            tags.get("clothing"), tags.get("hair_state"),
            tags.get("expression"), tags.get("body_state"),
            tags.get("pose"), tags.get("accessories", []),
            tags.get("setting"), tags.get("quality_score"),
            tags.get("nsfw_level", 0),
            tags.get("face_visible"), tags.get("full_body"),
            "vision_llm", tags.get("confidence", 0.8),
        )
        return {**tags, "character_slug": character_slug, "image_name": image_name}
    except Exception as e:
        logger.error(f"Failed to save tags for {image_name}: {e}")
        return None
    finally:
        await conn.close()


async def batch_tag_character_images(
    character_slug: str,
    project_name: str | None = None,
    limit: int = 50,
) -> dict:
    """Tag all untagged approved images for a character.

    Returns summary with counts.
    """
    conn = await connect_direct()
    try:
        # Get approved images from approval_status.json
        images_dir = BASE_PATH / character_slug / "images"
        approval_file = BASE_PATH / character_slug / "approval_status.json"

        if not images_dir.exists() or not approval_file.exists():
            return {"character_slug": character_slug, "tagged": 0, "skipped": 0,
                    "error": "No images or approval file found"}

        with open(approval_file) as f:
            statuses = json.load(f)

        approved_images = [
            name for name, st in statuses.items()
            if (st == "approved" or (isinstance(st, dict) and st.get("status") == "approved"))
            and (images_dir / name).exists()
        ]

        # Filter out already-tagged images
        already_tagged = set()
        rows = await conn.fetch(
            "SELECT image_name FROM image_visual_tags WHERE character_slug = $1",
            character_slug,
        )
        already_tagged = {r["image_name"] for r in rows}

        to_tag = [n for n in approved_images if n not in already_tagged][:limit]

        if not to_tag:
            return {"character_slug": character_slug, "tagged": 0, "skipped": len(approved_images),
                    "message": "All approved images already tagged"}

        # Get design_prompt for context
        design_prompt = None
        char_row = await conn.fetchrow(
            "SELECT design_prompt FROM characters "
            "WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), "
            "'[^a-z0-9_-]', '', 'g') = $1",
            character_slug,
        )
        if char_row:
            design_prompt = char_row["design_prompt"]
    finally:
        await conn.close()

    tagged = 0
    errors = 0
    for image_name in to_tag:
        image_path = images_dir / image_name
        result = await tag_image_visual_properties(
            image_path, character_slug, design_prompt, project_name
        )
        if result:
            tagged += 1
        else:
            errors += 1

    return {
        "character_slug": character_slug,
        "tagged": tagged,
        "errors": errors,
        "skipped": len(already_tagged),
        "remaining": len(approved_images) - len(already_tagged) - tagged,
    }


async def get_image_tags(
    character_slug: str, image_names: list[str] | None = None,
) -> dict[str, dict]:
    """Fetch visual tags for a character's images. Returns {image_name: tags_dict}."""
    conn = await connect_direct()
    try:
        if image_names:
            rows = await conn.fetch(
                "SELECT * FROM image_visual_tags "
                "WHERE character_slug = $1 AND image_name = ANY($2)",
                character_slug, image_names,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM image_visual_tags WHERE character_slug = $1",
                character_slug,
            )
        return {
            r["image_name"]: {
                "clothing": r["clothing"],
                "hair_state": r["hair_state"],
                "expression": r["expression"],
                "body_state": r["body_state"],
                "pose": r["pose"],
                "accessories": r["accessories"],
                "setting": r["setting"],
                "quality_score": r["quality_score"],
                "face_visible": r["face_visible"],
                "full_body": r["full_body"],
            }
            for r in rows
        }
    finally:
        await conn.close()


def _build_tag_prompt(character_slug: str, design_prompt: str | None) -> str:
    """Build the Ollama vision prompt for image tagging."""
    context = f"Character: {character_slug}"
    if design_prompt:
        context += f"\nDesign: {design_prompt}"

    return f"""Analyze this anime/illustration image and extract visual properties.
{context}

Output a JSON object with these fields:
- clothing: what the character is wearing (be specific, e.g. "white school blouse with red bow tie, dark pleated skirt")
- hair_state: hair condition (e.g. "loose long black hair", "tied in ponytail, slightly messy")
- expression: facial expression (e.g. "calm", "smiling", "angry", "surprised", "sad", "determined")
- body_state: one of [clean, wet, damp, bloody, stained, dirty, dusty, sweaty]
- pose: body pose (e.g. "standing front", "three-quarter view", "sitting", "action pose", "close-up portrait")
- accessories: array of accessories/items visible (e.g. ["glasses", "necklace", "sword"])
- setting: background/environment description (e.g. "classroom", "outdoor park", "dark alley")
- quality_score: image quality 0.0-1.0 (sharpness, composition, detail)
- nsfw_level: 0=safe, 1=suggestive, 2=explicit
- face_visible: true/false
- full_body: true if full body visible, false if partial
- confidence: your confidence in these tags 0.0-1.0

Output ONLY the JSON object, no other text."""


async def _call_ollama_vision(prompt: str, image_b64: str) -> dict | None:
    """Call Ollama vision model with an image."""
    import urllib.request
    try:
        payload = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2, "num_predict": 1024},
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)
        result = json.loads(resp.read())
        response_text = result.get("response", "")

        parsed = json.loads(response_text)
        if isinstance(parsed, dict):
            return parsed
        return None
    except Exception as e:
        logger.warning(f"Ollama vision tagging failed: {e}")
        return None
