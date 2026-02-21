"""Model profiles — checkpoint-aware prompt translation and parameter adjustment.

Maps checkpoint filenames to structured profiles that control:
- Prompt format (prose vs booru tags)
- Quality prefixes and negatives
- Style tag stripping for model switches
- Solo/background suffixes
- IP-Adapter model availability
- Vision review style hints
- Threshold adjustments

Usage:
    from packages.core.model_profiles import get_model_profile, translate_prompt

    profile = get_model_profile("ponyDiffusionV6XL.safetensors")
    prompt = translate_prompt(design_prompt, appearance_data, profile, pose)
"""

import logging
import re

logger = logging.getLogger(__name__)

# --- Model Profile Registry ---
# Keys are substring matches against checkpoint filenames (case-insensitive).
# Order matters: first match wins. Put specific names before generic ones.

MODEL_PROFILES: dict[str, dict] = {
    "ponyDiffusion": {
        "architecture": "sdxl",
        "prompt_format": "booru_tags",
        "quality_prefix": "score_9, score_8_up, score_7_up, source_anime",
        "quality_negative": (
            "score_6, score_5, score_4, worst quality, low quality, "
            "blurry, jpeg artifacts, watermark, text, signature"
        ),
        "strip_style_tags": [
            "Arcane painterly style",
            "neon-noir atmosphere",
            "neon-noir lighting",
            "gritty neon-noir atmosphere",
            "dramatic shadows",
            "dramatic chiaroscuro",
            "dramatic chiaroscuro lighting",
            "dramatic lighting",
            "bold shadows",
            "dark cyberpunk alley setting",
            "cyberpunk alley",
            "dark alley background",
            "neon-lit background",
            "cyberpunk city background",
            "muted gritty tones",
        ],
        "solo_suffix": "solo",
        "background_suffix": "simple background, white background",
        "ip_adapter_model": None,  # No SDXL IP-Adapter installed yet
        "vision_style_hint": "anime-style illustration with clean lines and cel-shading",
        "style_label": "anime/illustration (Pony Diffusion XL)",
        "default_cfg": 7.0,
        "default_steps": 28,
    },
    "cyberrealistic": {
        "architecture": "sd15",
        "prompt_format": "prose",
        "quality_prefix": "masterpiece, best quality, highly detailed, sharp focus",
        "quality_negative": (
            "worst quality, low quality, blurry, deformed, disfigured, "
            "bad anatomy, extra limbs, watermark, text, signature"
        ),
        "strip_style_tags": [],
        "solo_suffix": "solo, 1person, single character",
        "background_suffix": "white background, simple background",
        "ip_adapter_model": "ip-adapter-plus_sd15.safetensors",
        "vision_style_hint": "photorealistic digital art with cinematic lighting",
        "style_label": "photorealistic (Cyberrealistic)",
        "default_cfg": 7.0,
        "default_steps": 25,
    },
    "realcartoonPixar": {
        "architecture": "sd15",
        "prompt_format": "prose",
        "quality_prefix": "masterpiece, best quality, Pixar style, 3D render, Illumination style",
        "quality_negative": (
            "worst quality, low quality, blurry, deformed, disfigured, "
            "bad anatomy, extra limbs, watermark, text, signature, "
            "photorealistic, live action"
        ),
        "strip_style_tags": [],
        "solo_suffix": "solo, 1person, single character",
        "background_suffix": "white background, simple background",
        "ip_adapter_model": "ip-adapter-plus_sd15.safetensors",
        "vision_style_hint": "Pixar/Illumination-style 3D animated character",
        "style_label": "3D cartoon (RealCartoon Pixar)",
        "default_cfg": 8.5,
        "default_steps": 40,
    },
    "realistic_vision": {
        "architecture": "sd15",
        "prompt_format": "prose",
        "quality_prefix": "masterpiece, best quality, highly detailed, sharp focus, RAW photo",
        "quality_negative": (
            "worst quality, low quality, blurry, deformed, disfigured, "
            "bad anatomy, extra limbs, watermark, text, signature, "
            "cartoon, anime, drawing, painting"
        ),
        "strip_style_tags": [],
        "solo_suffix": "solo, 1person, single character",
        "background_suffix": "white background, simple background",
        "ip_adapter_model": "ip-adapter-plus_sd15.safetensors",
        "vision_style_hint": "photorealistic portrait with natural lighting",
        "style_label": "photorealistic (Realistic Vision)",
        "default_cfg": 7.0,
        "default_steps": 25,
    },
    "dreamshaper": {
        "architecture": "sd15",
        "prompt_format": "prose",
        "quality_prefix": "masterpiece, best quality, highly detailed",
        "quality_negative": (
            "worst quality, low quality, blurry, deformed, disfigured, "
            "bad anatomy, extra limbs, watermark, text, signature"
        ),
        "strip_style_tags": [],
        "solo_suffix": "solo, 1person, single character",
        "background_suffix": "white background, simple background",
        "ip_adapter_model": "ip-adapter-plus_sd15.safetensors",
        "vision_style_hint": "semi-realistic digital art with painterly qualities",
        "style_label": "semi-realistic (DreamShaper)",
        "default_cfg": 7.0,
        "default_steps": 25,
    },
}

# Safe fallback for unknown checkpoints
_DEFAULT_PROFILE: dict = {
    "architecture": "sd15",
    "prompt_format": "prose",
    "quality_prefix": "masterpiece, best quality",
    "quality_negative": "worst quality, low quality, blurry, deformed",
    "strip_style_tags": [],
    "solo_suffix": "solo, 1person, single character",
    "background_suffix": "white background, simple background",
    "ip_adapter_model": None,
    "vision_style_hint": "generated image",
    "style_label": "unknown model",
    "default_cfg": 7.0,
    "default_steps": 25,
}


def get_model_profile(checkpoint_filename: str,
                      db_architecture: str | None = None,
                      db_prompt_format: str | None = None) -> dict:
    """Look up the model profile for a checkpoint filename.

    Substring-matches against MODEL_PROFILES keys (case-insensitive).
    DB overrides (model_architecture, prompt_format) take precedence when set.

    Returns a copy so callers can modify without affecting the registry.
    """
    if not checkpoint_filename:
        return dict(_DEFAULT_PROFILE)

    ckpt_lower = checkpoint_filename.lower()

    profile = None
    for key, prof in MODEL_PROFILES.items():
        if key.lower() in ckpt_lower:
            profile = dict(prof)
            break

    if profile is None:
        logger.info(f"No profile matched for '{checkpoint_filename}', using SD1.5 default")
        profile = dict(_DEFAULT_PROFILE)

    # DB overrides take precedence
    if db_architecture:
        profile["architecture"] = db_architecture
    if db_prompt_format:
        profile["prompt_format"] = db_prompt_format

    return profile


# --- Prompt Translation ---

# Regex patterns for scene-setting phrases that conflict with training backgrounds
_SCENE_SETTING_PATTERNS = [
    r"(?:in|at|inside|within)\s+(?:a\s+)?(?:dark|neon|cyberpunk|futuristic|dimly[\s-]lit)\s+[\w\s]+(?:alley|street|bar|club|room|city|district)",
]
_SCENE_RE = re.compile("|".join(_SCENE_SETTING_PATTERNS), re.IGNORECASE)


def _strip_style_tags(text: str, tags_to_strip: list[str]) -> str:
    """Remove known style markers from a prompt string."""
    for tag in tags_to_strip:
        # Case-insensitive removal, clean up leftover commas
        text = re.sub(re.escape(tag), "", text, flags=re.IGNORECASE)

    # Remove scene-setting phrases
    text = _SCENE_RE.sub("", text)

    # Clean up: multiple commas, leading/trailing commas, extra spaces
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"^\s*,\s*", "", text)
    text = re.sub(r"\s*,\s*$", "", text)
    text = re.sub(r"\s{2,}", " ", text)

    return text.strip()


def _appearance_to_tags(appearance_data: dict) -> str:
    """Convert appearance_data key_colors and key_features to tag format.

    E.g., {"hair": "silver"} -> "silver_hair"
          ["pointed ears", "scar on forehead"] -> "pointed_ears, scar_on_forehead"
    """
    tags = []

    key_colors = appearance_data.get("key_colors", {})
    if isinstance(key_colors, dict):
        for feature, color in key_colors.items():
            # "hair": "silver" -> "silver_hair"
            tag = f"{color}_{feature}".lower().replace(" ", "_")
            tags.append(tag)

    key_features = appearance_data.get("key_features", [])
    if isinstance(key_features, list):
        for feat in key_features:
            tag = feat.lower().replace(" ", "_")
            tags.append(tag)

    return ", ".join(tags)


def _appearance_to_prose(appearance_data: dict) -> str:
    """Convert appearance_data key_colors and key_features to natural language."""
    parts = []

    key_colors = appearance_data.get("key_colors", {})
    if isinstance(key_colors, dict):
        color_phrases = [f"{color} {feature}" for feature, color in key_colors.items()]
        if color_phrases:
            parts.append(", ".join(color_phrases))

    key_features = appearance_data.get("key_features", [])
    if isinstance(key_features, list) and key_features:
        parts.append(", ".join(key_features))

    return ", ".join(parts)


def build_solo_suffix(profile: dict, design_prompt: str) -> str:
    """Build gender-aware solo suffix from profile and prompt content.

    For booru_tags models, uses gendered solo tags (1boy/1girl).
    For prose models, uses generic solo tag.
    """
    base_solo = profile["solo_suffix"]

    if profile["prompt_format"] == "booru_tags":
        prompt_lower = (design_prompt or "").lower()
        if any(tag in prompt_lower for tag in ("1man", "1boy", "1male", " male,")):
            return f"{base_solo}, 1boy"
        elif any(tag in prompt_lower for tag in ("1woman", "1girl", "1female", " female,")):
            return f"{base_solo}, 1girl"

    return base_solo


def translate_prompt(design_prompt: str, appearance_data: dict | None,
                     profile: dict, pose: str = "") -> str:
    """Model-aware prompt assembly.

    For booru_tags models (PonyXL):
        - Strips known style markers
        - Converts appearance_data to tag format
        - Appends model-appropriate quality/solo/background

    For prose models:
        - Keeps design_prompt as-is
        - Enriches with appearance data as natural language
        - Appends standard quality/solo/background

    The design_prompt in the DB stays unchanged. Translation is at generation time only.
    """
    appearance_data = appearance_data or {}
    parts = []

    # 1. Quality prefix from profile
    parts.append(profile["quality_prefix"])

    # 2. Process design_prompt based on format
    prompt_body = design_prompt or ""
    if profile["prompt_format"] == "booru_tags" and profile.get("strip_style_tags"):
        prompt_body = _strip_style_tags(prompt_body, profile["strip_style_tags"])

    parts.append(prompt_body)

    # 3. Appearance data enrichment
    if appearance_data:
        if profile["prompt_format"] == "booru_tags":
            appearance_tags = _appearance_to_tags(appearance_data)
        else:
            appearance_tags = _appearance_to_prose(appearance_data)
        if appearance_tags:
            parts.append(appearance_tags)

    # 4. Pose
    if pose:
        parts.append(pose)

    # 5. Solo + background suffix
    solo = build_solo_suffix(profile, design_prompt)
    parts.append(solo)
    parts.append(profile["background_suffix"])

    return ", ".join(p for p in parts if p)


def adjust_thresholds(profile: dict,
                      reject_threshold: float,
                      approve_threshold: float) -> tuple[float, float]:
    """Nudge auto-triage thresholds based on model type.

    Anime/illustration models tend to score lower on "clarity" in vision review
    because vision models trained on photos penalize stylization. Relax thresholds
    slightly for non-photorealistic models.
    """
    if profile["prompt_format"] == "booru_tags":
        # Anime models: slightly more lenient
        return (
            max(0.1, reject_threshold - 0.05),
            max(0.5, approve_threshold - 0.05),
        )
    if "cartoon" in profile.get("style_label", "").lower():
        # 3D cartoon: slightly more lenient
        return (
            max(0.1, reject_threshold - 0.03),
            max(0.5, approve_threshold - 0.03),
        )
    # Photorealistic: use as-is
    return (reject_threshold, approve_threshold)
