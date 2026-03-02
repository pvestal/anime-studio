"""Vision review — image quality assessment, perceptual hashing, description helpers."""

import json
import logging
from pathlib import Path

from packages.core.config import VISION_MODEL, OLLAMA_URL

logger = logging.getLogger(__name__)


def perceptual_hash(image_path: Path, hash_size: int = 8) -> str:
    """Compute a simple average-hash for perceptual dedup.

    Resizes to hash_size x hash_size grayscale, computes mean,
    returns hex string of bits > mean. Images that look similar
    get the same hash even if they differ by compression/scaling.
    """
    try:
        from PIL import Image
        img = Image.open(image_path).convert("L").resize((hash_size, hash_size), Image.LANCZOS)
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p > avg else "0" for p in pixels)
        return hex(int(bits, 2))
    except Exception:
        # Fallback to file hash if PIL fails
        import hashlib
        return hashlib.md5(image_path.read_bytes()).hexdigest()[:16]


def extract_json_from_vision(raw: str) -> dict | None:
    """Robustly extract a JSON object from vision model's response.

    Handles: markdown code fences, plain text around JSON, no JSON at all.
    Returns the parsed dict, or None if no valid JSON found.
    """
    import re

    if not raw:
        return None

    # Strip markdown code fences first: ```json ... ``` or ``` ... ```
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()

    # Find the first { ... } block
    start = raw.find("{")
    if start == -1:
        return None

    end = raw.rfind("}")
    if end == -1 or end <= start:
        return None

    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None


def vision_describe_image(image_path: Path) -> str:
    """Get a visual description of an image using the configured vision model (legacy, kept for upload endpoint)."""
    import base64
    import urllib.request as _ur

    img_data = base64.b64encode(image_path.read_bytes()).decode()
    payload = json.dumps({
        "model": VISION_MODEL,
        "prompt": "Describe the characters visible in this animated frame. Focus on species, colors, clothing, and distinctive features. Be concise.",
        "images": [img_data],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 250},
    }).encode()
    req = _ur.Request(f"{OLLAMA_URL}/api/generate", data=payload, headers={"Content-Type": "application/json"})
    resp = _ur.urlopen(req, timeout=60)
    return json.loads(resp.read()).get("response", "").strip()


_VISION_REVIEW_PROMPT = """You are evaluating an image for use in LoRA training of a specific character.

The character this image SHOULD contain: {character_name}
Character description: {design_prompt}
Expected gender: {expected_gender}
{style_context}{feature_checklist}{common_errors_section}
Look at the image carefully and answer these questions with HONEST scores from 0 to 10. Do NOT default to middle scores — a blurry crowd scene should score LOW, a crisp solo portrait should score HIGH.

Questions:
- character_match: How well does the visible character match the expected character? Check all key colors and features listed above. Wrong colors or missing key features = LOW score. (0=completely wrong character, 10=perfect match with correct colors and features)
- is_human: Does this character have HUMAN features? Even in cartoon/CGI/3D style, check: Does it have smooth human-like skin (not scales, fur, or shell)? A human-shaped face with a human nose? Human body proportions (arms, legs, torso like a person)? If YES to these → answer true. A character is HUMAN even if it's a cute cartoon or Pixar-style 3D render. Only answer false if the character is clearly an ANIMAL, CREATURE, ROBOT, or OBJECT (has fur, scales, shell, beak, snout, wings, non-human body shape).
- gender_match: Does the character's APPARENT GENDER match the expected gender ("{expected_gender}")? Check body shape, facial features, chest, jawline, and overall presentation. Answer true if it matches, false if it clearly does not. If expected gender is "unknown", always answer true.
- solo: Is ONLY one character visible? Answer true or false. If you see 2+ characters, answer false.
- clarity: Is the image sharp and clear? (0=very blurry/dark, 10=crystal clear)
- completeness: What body portion is shown? Answer exactly one of: full, upper, face, partial
- training_value: How useful is this specific image for training a LoRA model of this character? Wrong colors or species = 0. Wrong gender = 0. (0=useless, 10=perfect training image)
- has_anatomical_defects: Does the image have obvious anatomical problems? Check for: extra fingers (more than 5 per hand), merged/fused limbs, distorted face (melted features, asymmetric eyes, misshapen mouth), extra limbs, missing limbs that should be visible. Answer true if ANY defect is present, false if anatomy looks correct.
- common_error_hits: List which known problems (from the KNOWN PROBLEMS section above, if any) are present in this image. Use an empty list if none or no known problems were listed.
- caption: Write one sentence describing what you see — the character, their pose, expression, and background.
- issues: List specific problems (wrong colors, wrong species, wrong gender, extra fingers, distorted face, missing features, etc). If none, use an empty list.

Return ONLY valid JSON:
{{"character_match": <0-10>, "is_human": <true/false>, "gender_match": <true/false>, "solo": <true/false>, "clarity": <0-10>, "completeness": "<full|upper|face|partial>", "training_value": <0-10>, "has_anatomical_defects": <true/false>, "common_error_hits": [<strings>], "caption": "<sentence>", "issues": [<strings>]}}"""


def _extract_gender(design_prompt: str) -> str:
    """Extract expected gender from design_prompt prefix tag or keywords.

    Design prompts typically start with '1man', '1woman', '1creature', etc.
    Falls back to keyword scanning if no prefix tag found.
    Returns 'male', 'female', 'non-human', or 'unknown'.
    """
    if not design_prompt:
        return "unknown"
    prompt_lower = design_prompt.lower().strip()
    # Check prefix tags first (most reliable)
    if prompt_lower.startswith(("1man", "1boy", "1male")):
        return "male"
    if prompt_lower.startswith(("1woman", "1girl", "1female")):
        return "female"
    if prompt_lower.startswith("1creature"):
        return "non-human"
    # Keyword fallback
    gender_male = any(w in prompt_lower for w in (" man,", " man ", " male,", " male ", " boy,", " boy "))
    gender_female = any(w in prompt_lower for w in (" woman,", " woman ", " female,", " female ", " girl,", " girl "))
    if gender_male and not gender_female:
        return "male"
    if gender_female and not gender_male:
        return "female"
    return "unknown"


def build_feature_checklist(appearance_data: dict) -> str:
    """Build a character-specific feature checklist from appearance_data for vision review."""
    if not appearance_data:
        return ""
    parts = []
    species = appearance_data.get("species")
    if species:
        parts.append(f"Species/Type: {species}")
    key_colors = appearance_data.get("key_colors")
    if key_colors:
        color_lines = [f"  - {k}: {v}" for k, v in key_colors.items()]
        parts.append("KEY COLORS (check each one carefully):\n" + "\n".join(color_lines))
    key_features = appearance_data.get("key_features")
    if key_features:
        feat_lines = [f"  - {f}" for f in key_features]
        parts.append("KEY IDENTIFYING FEATURES:\n" + "\n".join(feat_lines))
    common_errors = appearance_data.get("common_errors")
    if common_errors:
        err_lines = [f"  - {e}" for e in common_errors]
        parts.append("COMMON GENERATION ERRORS (reject if you see these):\n" + "\n".join(err_lines))
    if not parts:
        return ""
    return "\n" + "\n".join(parts) + "\n"


# Species-specific visual traits that MUST be visible for non-human characters.
# Maps species keywords -> (what to look for, what means WRONG)
_SPECIES_CHECKS = {
    "turtle": {
        "look_for": "a turtle or reptilian body: shell on back, green/yellow scaly skin, reptilian face with beak or snout",
        "wrong_if": "smooth human skin, a human face shape, human nose, human hair, human body proportions",
    },
    "koopa": {
        "look_for": "a Koopa/turtle creature: shell on back, scaly/reptilian skin, turtle-like face",
        "wrong_if": "smooth human skin, a human face, human hair, human body without shell",
    },
    "dinosaur": {
        "look_for": "a dinosaur or reptilian creature: scaly skin, snout/muzzle, non-human body shape, tail",
        "wrong_if": "smooth human skin, human face, human hands, human proportions without tail or snout",
    },
    "star-shaped": {
        "look_for": "a star-shaped creature: round/star body shape, small simple form, floating, glowing",
        "wrong_if": "human body, arms and legs like a person, human face, child or kid",
    },
    "mushroom": {
        "look_for": "a mushroom creature: oversized mushroom cap head that IS the head (not a hat), tiny body",
        "wrong_if": "human child wearing a hat, normal human head under a cap, human proportions",
    },
    "mouse": {
        "look_for": "a mouse/rodent creature: mouse snout, round ears, whiskers, fur, tail",
        "wrong_if": "smooth human skin, human face, human ears, no fur or whiskers",
    },
    "dragon": {
        "look_for": "a dragon-turtle creature: massive scaly body, spiky shell, horns, fangs, claws",
        "wrong_if": "human skin, human face, human body, no shell or scales",
    },
}


def _verify_species(image_path: Path, species: str, appearance_data: dict) -> bool:
    """Focused binary species verification for non-human characters.

    Asks a targeted yes/no question about whether the expected species traits
    are visible. Much more reliable than asking "is this human?" generically.

    Returns True if species matches, False if wrong species detected.
    """
    import base64
    import urllib.request as _ur

    # Find the best matching species check
    species_lower = species.lower()
    check = None
    for keyword, spec in _SPECIES_CHECKS.items():
        if keyword in species_lower:
            check = spec
            break

    if check is None:
        # No specific check available — skip verification
        return True

    prompt = (
        f"Look at the CHARACTER in this image carefully. I need to verify its SPECIES.\n\n"
        f"Expected species: {species}\n\n"
        f"CORRECT if you see: {check['look_for']}\n"
        f"WRONG if you see: {check['wrong_if']}\n\n"
        f"Focus ONLY on the character's BODY and FACE — ignore clothing, hats, and accessories.\n"
        f"Look at the SKIN: is it smooth human-like skin, or is it scaly/furry/non-human?\n"
        f"Look at the FACE: is it a human face shape, or a creature/animal face?\n\n"
        f"Does this character's body match the expected species ({species})?\n"
        f"Answer ONLY with valid JSON: {{\"species_correct\": true}} or {{\"species_correct\": false}}"
    )

    try:
        img_data = base64.b64encode(image_path.read_bytes()).decode()
        payload = json.dumps({
            "model": VISION_MODEL,
            "prompt": prompt,
            "images": [img_data],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 30},
        }).encode()
        req = _ur.Request(f"{OLLAMA_URL}/api/generate", data=payload,
                          headers={"Content-Type": "application/json"})
        resp = _ur.urlopen(req, timeout=30)
        raw = json.loads(resp.read()).get("response", "").strip()

        result = extract_json_from_vision(raw)
        if result and "species_correct" in result:
            correct = result["species_correct"]
            logger.info(f"Species verification for {image_path.name}: "
                        f"expected='{species}', correct={correct}")
            return bool(correct)

        # If we can't parse the response, check for keywords
        raw_lower = raw.lower()
        if "false" in raw_lower or "wrong" in raw_lower or "no" in raw_lower:
            logger.info(f"Species verification (keyword fallback) for {image_path.name}: FAILED")
            return False

        # Ambiguous — let it pass (don't over-reject)
        logger.warning(f"Species verification ambiguous for {image_path.name}: {raw[:100]}")
        return True

    except Exception as e:
        logger.warning(f"Species verification failed for {image_path.name}: {e}")
        return True  # Don't reject on errors


def vision_review_image(image_path: Path, character_name: str, design_prompt: str,
                        model: str | None = None, appearance_data: dict | None = None,
                        model_profile: dict | None = None) -> dict:
    """Assess an image for LoRA training quality using the configured vision model."""
    import base64
    import urllib.request as _ur

    expected_gender = _extract_gender(design_prompt)
    feature_checklist = build_feature_checklist(appearance_data or {})

    # Build model-aware style context
    style_context = ""
    if model_profile:
        style_context = (
            f"\nIMPORTANT: This image was generated by a {model_profile.get('style_label', 'unknown')} model.\n"
            f"Expected visual style: {model_profile.get('vision_style_hint', 'generated image')}.\n"
            f"Do NOT penalize for matching this style (e.g., anime eyes are correct for an anime model, "
            f"Pixar-style rendering is correct for a 3D cartoon model).\n"
        )

    # Build common_errors hard check section
    common_errors_section = ""
    common_errors = (appearance_data or {}).get("common_errors", [])
    if common_errors:
        err_lines = "\n".join(f"- {e}" for e in common_errors)
        common_errors_section = (
            f"\nCheck for these KNOWN PROBLEMS with this character:\n{err_lines}\n"
            f"For each: does this image show this problem? If YES, it is a critical issue.\n"
        )

    prompt = _VISION_REVIEW_PROMPT.format(
        character_name=character_name,
        design_prompt=design_prompt or "no design prompt available",
        expected_gender=expected_gender,
        feature_checklist=feature_checklist,
        style_context=style_context,
        common_errors_section=common_errors_section,
    )
    img_data = base64.b64encode(image_path.read_bytes()).decode()
    payload = json.dumps({
        "model": model or VISION_MODEL,
        "prompt": prompt,
        "images": [img_data],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 400},
    }).encode()
    req = _ur.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = _ur.urlopen(req, timeout=90)
    raw = json.loads(resp.read()).get("response", "").strip()

    # Try to parse JSON from the response
    review = extract_json_from_vision(raw)
    if review is None:
        logger.warning(f"Vision model returned non-JSON for {image_path.name}: {raw[:200]}")
        review = {
            "character_match": 5,
            "solo": True,
            "clarity": 5,
            "completeness": "unknown",
            "training_value": 5,
            "caption": raw[:200],
            "issues": ["Vision model returned non-structured response"],
        }

    # Ensure expected keys exist with defaults
    review.setdefault("character_match", 5)
    review.setdefault("is_human", None)
    review.setdefault("gender_match", True)
    review.setdefault("solo", True)
    review.setdefault("clarity", 5)
    review.setdefault("completeness", "unknown")
    review.setdefault("training_value", 5)
    review.setdefault("has_anatomical_defects", False)
    review.setdefault("common_error_hits", [])
    review.setdefault("caption", "")
    review.setdefault("issues", [])

    # Clamp numeric scores to 0-10
    for key in ("character_match", "clarity", "training_value"):
        val = review[key]
        if isinstance(val, (int, float)):
            review[key] = max(0, min(10, val))
        else:
            review[key] = 5

    # Hard species validation for non-human characters:
    # Run a focused binary verification (like confusable pair checks)
    if appearance_data:
        species = (appearance_data or {}).get("species", "")
        if "NOT human" in species:
            species_ok = _verify_species(image_path, species, appearance_data)
            review["species_verified"] = species_ok
            if not species_ok:
                logger.info(f"Species rejection for {image_path.name}: "
                            f"expected '{species}' but species check failed")
                review["character_match"] = 0
                review["training_value"] = 0
                review["issues"] = list(review["issues"]) + [
                    f"WRONG SPECIES: expected {species}, image shows wrong species"
                ]

    # Hard gender gate: wrong gender → zero out scores
    if expected_gender in ("male", "female") and not review.get("gender_match", True):
        logger.info(f"Gender rejection for {image_path.name}: "
                    f"expected '{expected_gender}', vision says wrong gender")
        review["character_match"] = 0
        review["training_value"] = 0
        review["issues"] = list(review["issues"]) + [
            f"WRONG GENDER: expected {expected_gender}"
        ]

    # Hard anatomy gate: visible defects → tank training_value
    if review.get("has_anatomical_defects", False):
        logger.info(f"Anatomy rejection for {image_path.name}: defects detected")
        review["training_value"] = min(review["training_value"], 2)
        review["issues"] = list(review["issues"]) + [
            "ANATOMICAL DEFECTS: extra/merged fingers, distorted face, or malformed limbs"
        ]

    # Hard common_error gate: known problems hit → cap training_value
    error_hits = review.get("common_error_hits", [])
    if error_hits:
        logger.info(f"Common error hits for {image_path.name}: {error_hits}")
        review["training_value"] = min(review["training_value"], 2)
        review["issues"] = list(review["issues"]) + [
            f"KNOWN PROBLEM: {hit}" for hit in error_hits
        ]

    return review


# Map vision review findings -> rejection categories for the feedback loop
VISION_ISSUE_TO_REJECTION = {
    "multiple characters": "not_solo",
    "multi-character": "not_solo",
    "not solo": "not_solo",
    "blurry": "bad_quality",
    "low quality": "bad_quality",
    "low resolution": "bad_quality",
    "artifacts": "bad_quality",
    "distorted": "bad_quality",
    "wrong character": "wrong_appearance",
    "not recognizable": "wrong_appearance",
    "wrong species": "wrong_appearance",
    "wrong gender": "wrong_appearance",
    "wrong style": "wrong_style",
    "inconsistent": "wrong_style",
    "awkward pose": "wrong_pose",
    "unnatural": "wrong_pose",
    "extra fingers": "bad_quality",
    "extra limbs": "bad_quality",
    "merged": "bad_quality",
    "fused": "bad_quality",
    "anatomical defects": "bad_quality",
    "malformed": "bad_quality",
}


def vision_issues_to_categories(review: dict) -> list[str]:
    """Convert vision review findings into structured rejection categories."""
    cats = set()
    # Not solo -> not_solo
    if not review.get("solo", True):
        cats.add("not_solo")
    # Low clarity -> bad_quality (6/10 minimum — 5 was too lenient, accepted fuzzy images)
    if review.get("clarity", 10) < 6:
        cats.add("bad_quality")
    # Low character match -> wrong_appearance
    if review.get("character_match", 10) < 4:
        cats.add("wrong_appearance")
    # Wrong gender -> wrong_appearance
    if not review.get("gender_match", True):
        cats.add("wrong_appearance")
    # Anatomical defects -> bad_quality
    if review.get("has_anatomical_defects", False):
        cats.add("bad_quality")
    # Scan issue strings for keyword matches
    for issue in review.get("issues", []):
        issue_lower = issue.lower()
        for keyword, cat in VISION_ISSUE_TO_REJECTION.items():
            if keyword in issue_lower:
                cats.add(cat)
    return list(cats)
