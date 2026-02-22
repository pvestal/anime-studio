"""Image classification — character identification, confusable verification, roster building."""

import json
import logging
from pathlib import Path

from packages.core.config import VISION_MODEL, BASE_PATH, OLLAMA_URL

logger = logging.getLogger(__name__)

# Resolve script dir for bible path lookups
_SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "server"


# DEPRECATED: Hardcoded roster kept as fallback for callers that don't pass project_name.
# Prefer build_character_roster(project_name) which builds dynamically from DB.
CHARACTER_ROSTER: dict[str, str] = {
    "mario": "short stocky man in red cap with letter M, red shirt, blue overalls, thick brown mustache — the main hero",
    "luigi": "tall thin man in green cap with letter L, green shirt, blue overalls, thin dark mustache — Mario's brother",
    "princess_peach": "blonde woman in PINK dress (NOT blue/teal) with golden crown or tiara — pink is the key identifier",
    "toad": "small mushroom-headed creature with oversized white cap covered in red spots, wearing blue vest — NOT a turtle",
    "yoshi": "green dinosaur with round nose, white belly, and red saddle on back — rides like a horse, long tongue",
    "rosalina": "tall blonde woman in TEAL/LIGHT BLUE gown (NOT pink), star wand, hair covering one eye — teal dress is the key identifier",
    "bowser": "massive menacing turtle-dragon with spiky green shell, horns, fangs, red mohawk hair — the main villain, much larger than other characters",
    "bowser_jr": "small child version of Bowser with white bib/bandana with fangs drawn on it, top-knot ponytail — much smaller than Bowser",
    "kamek": "small turtle/koopa in blue wizard robes and round glasses, rides a broomstick, magic wand",
    "luma": "tiny glowing star-shaped creature with small dot eyes, floats in space, associated with Rosalina",
    "birdo": "pink dinosaur-like creature with large tubular snout, red bow on head",
}


# Known confusable character pairs with focused verification prompts.
# Maps slug -> {partner: slug, prompt: focused binary question}
CONFUSABLE_PAIRS: dict[str, dict] = {
    "princess_peach": {
        "partner": "rosalina",
        "prompt": (
            "This frame shows a blonde female character. I need to determine WHICH character she is.\n\n"
            "PRINCESS PEACH wears a PINK dress. She has a small golden crown/tiara.\n"
            "ROSALINA wears a TEAL or LIGHT BLUE dress. Her hair covers one eye. She often holds a star wand.\n\n"
            "Look ONLY at the PRIMARY character's DRESS COLOR:\n"
            "- If the dress is PINK or MAGENTA -> answer is princess_peach\n"
            "- If the dress is TEAL, CYAN, or LIGHT BLUE -> answer is rosalina\n\n"
            "Return ONLY valid JSON with two fields:\n"
            "  answer — must be exactly one of: princess_peach, rosalina\n"
            "  dress_color — the actual color you see in the image"
        ),
    },
    "rosalina": {
        "partner": "princess_peach",
        "prompt": (
            "This frame shows a blonde female character. I need to determine WHICH character she is.\n\n"
            "PRINCESS PEACH wears a PINK dress. She has a small golden crown/tiara.\n"
            "ROSALINA wears a TEAL or LIGHT BLUE dress. Her hair covers one eye. She often holds a star wand.\n\n"
            "Look ONLY at the PRIMARY character's DRESS COLOR:\n"
            "- If the dress is PINK or MAGENTA -> answer is princess_peach\n"
            "- If the dress is TEAL, CYAN, or LIGHT BLUE -> answer is rosalina\n\n"
            "Return ONLY valid JSON with two fields:\n"
            "  answer — must be exactly one of: princess_peach, rosalina\n"
            "  dress_color — the actual color you see in the image"
        ),
    },
    "bowser": {
        "partner": "bowser_jr",
        "prompt": (
            "This frame shows a turtle-dragon character. I need to determine WHICH one.\n\n"
            "BOWSER is MASSIVE — he towers over all other characters. Huge spiky shell, horns, red mohawk.\n"
            "BOWSER JR. is SMALL — child-sized. Has a white bib/bandana with drawn fangs. Top-knot ponytail.\n\n"
            "Key question: Is this character LARGE (adult-sized) or SMALL (child-sized)?\n"
            "- If LARGE with no bib -> answer is bowser\n"
            "- If SMALL with white bib -> answer is bowser_jr\n\n"
            "Return ONLY valid JSON with two fields:\n"
            "  answer — must be exactly one of: bowser, bowser_jr\n"
            "  size — either large or small"
        ),
    },
    "bowser_jr": {
        "partner": "bowser",
        "prompt": (
            "This frame shows a turtle-dragon character. I need to determine WHICH one.\n\n"
            "BOWSER is MASSIVE — he towers over all other characters. Huge spiky shell, horns, red mohawk.\n"
            "BOWSER JR. is SMALL — child-sized. Has a white bib/bandana with drawn fangs. Top-knot ponytail.\n\n"
            "Key question: Is this character LARGE (adult-sized) or SMALL (child-sized)?\n"
            "- If LARGE with no bib -> answer is bowser\n"
            "- If SMALL with white bib -> answer is bowser_jr\n\n"
            "Return ONLY valid JSON with two fields:\n"
            "  answer — must be exactly one of: bowser, bowser_jr\n"
            "  size — either large or small"
        ),
    },
}


# Cache for loaded bible data
_bible_cache: dict[str, dict | None] = {}


def load_project_bible(project_name: str) -> dict | None:
    """Load bible.json for a project if it exists.

    Checks multiple path patterns for the bible file.
    Results are cached in memory.

    Args:
        project_name: Project name (will be slugified for path lookup).

    Returns: Parsed bible dict, or None if not found.
    """
    if project_name in _bible_cache:
        return _bible_cache[project_name]

    slug = project_name.lower().replace(" ", "_")

    # Check multiple possible paths
    search_paths = [
        _SCRIPT_DIR.parent / "workflows" / "projects" / slug / "bible.json",
        Path("/opt/tower-anime-production/workflows/projects") / slug / "bible.json",
    ]

    # Also try partial slug matches (e.g., "mario_galaxy" for "Super Mario Galaxy Anime Adventure")
    for base in [_SCRIPT_DIR.parent / "workflows" / "projects",
                 Path("/opt/tower-anime-production/workflows/projects")]:
        if base.is_dir():
            for d in base.iterdir():
                if d.is_dir() and d.name in slug:
                    search_paths.append(d / "bible.json")

    for bible_path in search_paths:
        if bible_path.exists():
            try:
                bible = json.loads(bible_path.read_text())
                _bible_cache[project_name] = bible
                logger.info(f"Loaded bible.json for '{project_name}': {bible_path}")
                return bible
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load bible {bible_path}: {e}")

    _bible_cache[project_name] = None
    return None


def build_character_roster(project_name: str | None = None,
                           character_info: dict[str, dict] | None = None) -> dict[str, str]:
    """Build a classification roster dynamically from DB characters + design_prompts.

    Uses the cached _char_project_cache from packages.core.db.
    Falls back to CHARACTER_ROSTER if no DB data is available.

    Args:
        project_name: Filter to characters in this project. None = all cached characters.
        character_info: Pre-loaded character info dict (slug -> {name, design_prompt}).
                       If provided, used directly instead of cache.

    Returns: dict mapping slug -> visual description string for vision classification.
    """
    from packages.core.db import _char_project_cache

    roster: dict[str, str] = {}

    # If character_info is directly provided, use it
    source = character_info or _char_project_cache

    for slug, info in source.items():
        # Filter by project if specified
        if project_name and info.get("project_name") != project_name:
            continue

        design_prompt = info.get("design_prompt", "")
        name = info.get("name", slug.replace("_", " ").title())

        if design_prompt:
            roster[slug] = design_prompt
        elif slug in CHARACTER_ROSTER:
            # Fall back to hardcoded description if DB has no design_prompt
            roster[slug] = CHARACTER_ROSTER[slug]
        else:
            roster[slug] = name

    # If we got nothing from DB, fall back to full hardcoded roster
    if not roster:
        return dict(CHARACTER_ROSTER)

    return roster


def verify_confusable(image_path: Path, initial_slug: str, img_b64: str) -> str | None:
    """Run a focused binary verification for confusable character pairs.

    Returns the verified slug, or None if inconclusive.
    """
    import urllib.request as _ur

    pair = CONFUSABLE_PAIRS[initial_slug]
    partner = pair["partner"]
    prompt = pair["prompt"]

    try:
        payload = json.dumps({
            "model": VISION_MODEL,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 100},
        }).encode()
        req = _ur.Request(f"{OLLAMA_URL}/api/generate", data=payload,
                          headers={"Content-Type": "application/json"})
        resp = _ur.urlopen(req, timeout=30)
        raw = json.loads(resp.read()).get("response", "").strip()

        from .vision import extract_json_from_vision
        result = extract_json_from_vision(raw)
        if result is None:
            logger.warning(f"Confusable verification returned no JSON for {image_path.name}: {raw[:150]}")
            return None

        answer = result.get("answer", "").strip().lower()

        # Accept exact slug matches from the pair
        if answer == initial_slug:
            return initial_slug
        elif answer == partner:
            logger.info(f"Confusable override: {image_path.name} reclassified "
                        f"{initial_slug} -> {partner} (dress_color={result.get('dress_color', '?')}, "
                        f"size={result.get('size', '?')})")
            return partner

        # Vision model parroted the placeholder — infer from the secondary field instead.
        dress_color = result.get("dress_color", "").strip().lower()
        size = result.get("size", "").strip().lower()

        if dress_color:
            # Pink/magenta -> Peach, teal/blue/cyan -> Rosalina
            if any(c in dress_color for c in ("pink", "magenta", "rose")):
                inferred = "princess_peach"
            elif any(c in dress_color for c in ("teal", "blue", "cyan", "light blue")):
                inferred = "rosalina"
            else:
                inferred = None
            if inferred and inferred in (initial_slug, partner):
                logger.info(f"Confusable inferred from dress_color='{dress_color}': "
                            f"{image_path.name} -> {inferred}")
                return inferred

        if size:
            # Large -> Bowser, small -> Bowser Jr.
            if "large" in size or "big" in size or "massive" in size:
                inferred = "bowser"
            elif "small" in size or "child" in size or "tiny" in size:
                inferred = "bowser_jr"
            else:
                inferred = None
            if inferred and inferred in (initial_slug, partner):
                logger.info(f"Confusable inferred from size='{size}': "
                            f"{image_path.name} -> {inferred}")
                return inferred

        logger.warning(f"Confusable verification got unexpected answer '{answer}' "
                       f"for {image_path.name} (dress_color={dress_color}, size={size})")
        return None

    except Exception as e:
        logger.warning(f"Confusable verification failed for {image_path.name}: {e}")
        return None


def classify_image(image_path: Path, allowed_slugs: list[str] | None = None,
                   character_info: dict[str, dict] | None = None,
                   project_name: str | None = None,
                   bible_data: dict | None = None) -> tuple[list[str], str]:
    """Classify which characters appear in an image using direct vision model identification.

    Instead of describe->keyword matching, asks the vision model directly which characters
    from the roster are visible. Much higher accuracy.

    Args:
        image_path: Path to the image file
        allowed_slugs: List of character slugs to check for
        character_info: Dict mapping slug -> {name, design_prompt} for context
        project_name: Project name to build dynamic roster from DB
        bible_data: Pre-loaded bible.json dict for richer character descriptions

    Returns (matched_slugs, description).
    """
    import base64
    import urllib.request as _ur

    from .vision import extract_json_from_vision

    # Build roster dynamically from DB, falling back to hardcoded CHARACTER_ROSTER
    roster = build_character_roster(project_name=project_name, character_info=character_info)

    if not allowed_slugs:
        allowed_slugs = list(roster.keys())

    # Build character description lines for the vision prompt
    char_lines = []
    valid_slugs = []
    for slug in allowed_slugs:
        # Use dynamic roster first, then hardcoded fallback
        desc = roster.get(slug)
        if not desc:
            continue

        info = (character_info or {}).get(slug, {})
        name = info.get("name", slug.replace("_", " ").title())

        # If bible data has richer character descriptions, prefer those
        if bible_data:
            bible_chars = bible_data.get("characters", {})
            for bchar in (bible_chars if isinstance(bible_chars, list) else bible_chars.values()):
                bname = bchar.get("name", "")
                if bname and bname.lower().replace(" ", "_").replace(".", "") == slug.replace("_", ""):
                    bible_visual = bchar.get("visual_description", bchar.get("appearance", ""))
                    if bible_visual:
                        desc = bible_visual
                    break

        char_lines.append(f"- {slug}: {name} — {desc}")
        valid_slugs.append(slug)

    char_list = "\n".join(char_lines)

    prompt = f"""Look at this animated/CGI frame carefully. Identify the PRIMARY CHARACTER and extract visual details for production reference.

Known characters:
{char_list}

TASKS:
1. Identify the PRIMARY CHARACTER — the main focus of this frame (largest, most centered, most in-focus)
2. Note any other visible characters
3. Describe the character's EXACT appearance: colors, outfit details, proportions, facial features, accessories
4. Describe the environment/setting: location type, lighting, color palette, mood
5. Note the art style: rendering quality, animation style, visual effects

RULES:
- Only set "primary" if you can clearly see their SPECIFIC distinguishing features
- If NO single character dominates (group shot, landscape, etc.) set primary to null
- If dark, blurry, or characters too small to identify, set primary to null
- Do NOT guess — return null rather than incorrectly identify
- Be SPECIFIC in appearance_notes — exact colors ("bright red"), exact clothing items, exact proportions

Return ONLY valid JSON:
{{"primary": "slug_or_null", "others": ["slug1"], "confidence": "high_or_medium_or_low", "description": "one-line scene summary", "appearance_notes": "detailed character appearance: colors, outfit, features, proportions", "environment": "setting, lighting, colors, mood", "art_style": "rendering style, visual quality notes"}}

CONFIDENCE RULES:
- "high": You can clearly see the character's distinguishing features and are certain of the identification
- "medium": The character is likely correct but some features are obscured, distant, or ambiguous
- "low": You are guessing — the character is too small, too dark, or features don't clearly match"""

    try:
        img_data = base64.b64encode(image_path.read_bytes()).decode()
        payload = json.dumps({
            "model": VISION_MODEL,
            "prompt": prompt,
            "images": [img_data],
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 500},
        }).encode()
        req = _ur.Request(f"{OLLAMA_URL}/api/generate", data=payload,
                          headers={"Content-Type": "application/json"})
        resp = _ur.urlopen(req, timeout=60)
        raw = json.loads(resp.read()).get("response", "").strip()

        # Parse JSON response
        result = extract_json_from_vision(raw)
        if result is None:
            logger.warning(f"Vision classification returned no JSON for {image_path.name}: {raw[:150]}")
            return [], ""

        primary = result.get("primary")
        others = result.get("others", [])
        description = result.get("description", "")
        confidence = (result.get("confidence") or "medium").lower()

        # Reject low-confidence classifications — too unreliable for LoRA training
        if confidence == "low":
            logger.info(f"Low confidence classification for {image_path.name}, skipping")
            return [], description

        # Build matched list: primary + validated "others" for multi-character assignment.
        # A frame of Mario riding Yoshi → both get the frame.
        #
        # GUARD: The vision model hallucinates `others` — it sees the roster and
        # free-associates characters that aren't in the frame.  Rules:
        #   - Only trust others when confidence == "high"
        #   - Max 2 others (3 total).  If the model lists 3+ others it's hallucinating.
        #   - Group shots (no primary) only accepted with exactly 2 others.
        _MAX_OTHERS = 2
        valid_others = [s for s in others if s in valid_slugs]

        matched = []
        if primary and primary in valid_slugs:
            matched.append(primary)
            if confidence == "high" and len(valid_others) <= _MAX_OTHERS:
                for other_slug in valid_others:
                    if other_slug not in matched:
                        matched.append(other_slug)
        elif len(valid_others) == 1:
            # No primary but exactly 1 other — treat as the subject
            matched.append(valid_others[0])
        elif not primary and len(valid_others) == 2 and confidence == "high":
            # Group shot with exactly 2 identifiable characters
            matched.extend(valid_others)

        # Confusable verification: run per-character, not per-frame
        verified_matched = []
        for slug in matched:
            if slug in CONFUSABLE_PAIRS:
                verified = verify_confusable(image_path, slug, img_data)
                if verified is not None:
                    if verified not in verified_matched:
                        verified_matched.append(verified)
                else:
                    logger.info(f"Confusable verification inconclusive for {slug} in {image_path.name}, dropping")
            else:
                if slug not in verified_matched:
                    verified_matched.append(slug)

        if matched and not verified_matched:
            logger.info(f"All confusable verifications failed for {image_path.name}, skipping")
            return [], description

        matched = verified_matched

        # Pack extra observations into the description for downstream use
        extras = {}
        for key in ("appearance_notes", "environment", "art_style"):
            val = result.get(key, "")
            if val:
                extras[key] = val
        if extras:
            # Encode extras as JSON suffix so callers can optionally parse them
            description = json.dumps({"description": description, **extras})

        return matched, description

    except Exception as e:
        logger.warning(f"Vision classification failed for {image_path.name}: {e}")
        return [], ""
