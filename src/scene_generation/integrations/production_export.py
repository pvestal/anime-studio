"""
Production Export Helpers
Export-related functions, serialization helpers, and validation utilities
for AnimeProductionIntegration.
"""

from typing import Dict, List, Any
from datetime import datetime


# ── Default Generation Parameters ────────────────────────────────────────────

DEFAULT_GENERATION_PARAMETERS: Dict[str, Any] = {
    "resolution": "1920x1080",
    "aspect_ratio": "16:9",
    "frame_rate": 24,
    "duration_seconds": 5.0,
    "quality": "high",
    "style": "anime",
    "model": "animatediff_evolved",
    "guidance_scale": 7.5,
    "num_inference_steps": 20,
    "seed": -1
}

ANIME_OPTIMIZATION_KEYWORDS: List[str] = [
    "high quality", "detailed", "professional anime", "studio quality",
    "crisp", "vibrant", "well-lit", "sharp focus"
]

STANDARD_FRAME_RATES: List[int] = [24, 30, 60]

MAX_GENERATION_DURATION: float = 10.0

DEFAULT_MODEL: str = "animatediff_evolved"


# ── Pure Helper Functions ────────────────────────────────────────────────────

def validate_resolution(resolution: str) -> bool:
    """Validate resolution format"""
    try:
        width, height = resolution.split('x')
        width_int = int(width)
        height_int = int(height)
        return width_int > 0 and height_int > 0
    except Exception:
        return False


def build_generation_prompt(
    visual_description: str,
    cinematography_notes: str,
    atmosphere_description: str,
    technical_specs: Dict[str, Any]
) -> str:
    """Build comprehensive generation prompt"""
    prompt_parts = []

    if visual_description:
        prompt_parts.append(f"Visual composition: {visual_description}")

    if cinematography_notes:
        prompt_parts.append(f"Camera work: {cinematography_notes}")

    if atmosphere_description:
        prompt_parts.append(f"Atmosphere: {atmosphere_description}")

    if technical_specs:
        camera_angle = technical_specs.get("camera_angle", "medium_shot")
        camera_movement = technical_specs.get("camera_movement", "static")
        lighting_type = technical_specs.get("lighting_type", "natural")

        prompt_parts.append(f"Camera angle: {camera_angle}")
        prompt_parts.append(f"Camera movement: {camera_movement}")
        prompt_parts.append(f"Lighting: {lighting_type}")

    full_prompt = ". ".join(prompt_parts)
    anime_enhanced_prompt = f"Professional anime scene: {full_prompt}. High quality, detailed animation, studio production quality."

    return anime_enhanced_prompt


def build_generation_parameters(technical_specs: Dict[str, Any]) -> Dict[str, Any]:
    """Build generation parameters from technical specifications"""
    params = DEFAULT_GENERATION_PARAMETERS.copy()
    params["resolution"] = technical_specs.get("resolution", params["resolution"])
    params["aspect_ratio"] = technical_specs.get("aspect_ratio", params["aspect_ratio"])
    params["frame_rate"] = technical_specs.get("frame_rate", params["frame_rate"])
    params["duration_seconds"] = technical_specs.get("duration_seconds", params["duration_seconds"])
    return params


def optimize_visual_description(visual_desc: str) -> str:
    """Optimize visual description for anime generation"""
    desc_lower = visual_desc.lower()
    missing_keywords = [kw for kw in ANIME_OPTIMIZATION_KEYWORDS if kw not in desc_lower]

    if missing_keywords:
        optimization = ", ".join(missing_keywords[:3])
        return f"{visual_desc}. {optimization}."
    else:
        return visual_desc


def optimize_technical_specs(tech_specs: Dict[str, Any]) -> Dict[str, Any]:
    """Optimize technical specifications for generation"""
    optimized_specs = tech_specs.copy()

    if "resolution" not in optimized_specs:
        optimized_specs["resolution"] = "1920x1080"

    if "frame_rate" not in optimized_specs:
        optimized_specs["frame_rate"] = 24

    if "duration_seconds" not in optimized_specs:
        optimized_specs["duration_seconds"] = 5.0

    if optimized_specs.get("duration_seconds", 0) > MAX_GENERATION_DURATION:
        optimized_specs["duration_seconds"] = MAX_GENERATION_DURATION

    return optimized_specs


def build_export_result(
    result: Dict[str, Any],
    scene_ids: List[int],
    project_id: int
) -> Dict[str, Any]:
    """Process the export result from anime production system"""
    return {
        "success": True,
        "project_id": project_id,
        "scenes_exported": len(scene_ids),
        "export_status": result.get("status", "queued"),
        "generation_queue_id": result.get("queue_id"),
        "estimated_completion": result.get("estimated_completion"),
        "summary": {
            "total_scenes": len(scene_ids),
            "project_type": "scene_description_export",
            "export_timestamp": datetime.utcnow().isoformat()
        }
    }


def validate_scene_for_generation(scene_description: Dict[str, Any]) -> Dict[str, Any]:
    """Validate scene description for anime generation compatibility"""
    validation_results = {
        "valid": True,
        "issues": [],
        "warnings": [],
        "requirements_met": {}
    }

    # Check required fields
    required_fields = ["visual_description", "technical_specifications"]
    for field in required_fields:
        if field not in scene_description or not scene_description[field]:
            validation_results["valid"] = False
            validation_results["issues"].append(f"Missing required field: {field}")
            validation_results["requirements_met"][field] = False
        else:
            validation_results["requirements_met"][field] = True

    # Check technical specifications
    tech_specs = scene_description.get("technical_specifications", {})
    if isinstance(tech_specs, dict):
        resolution = tech_specs.get("resolution", "1920x1080")
        if not validate_resolution(resolution):
            validation_results["warnings"].append(f"Non-standard resolution: {resolution}")

        frame_rate = tech_specs.get("frame_rate", 24)
        if frame_rate not in STANDARD_FRAME_RATES:
            validation_results["warnings"].append(f"Non-standard frame rate: {frame_rate}")

        duration = tech_specs.get("duration_seconds")
        if duration and (duration < 1 or duration > 30):
            validation_results["warnings"].append(f"Duration outside recommended range: {duration}s")

    # Check visual description quality
    visual_desc = scene_description.get("visual_description", "")
    if len(visual_desc) < 20:
        validation_results["warnings"].append("Visual description is very brief")

    return validation_results
