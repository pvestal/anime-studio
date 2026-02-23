"""
Echo Brain Helpers
Helper functions, utility code, and formatting functions for EchoBrainIntegration.
"""

from typing import Dict, List, Any


# ── Keyword Lists for Element Extraction ─────────────────────────────────────

VISUAL_KEYWORDS: List[str] = [
    "lighting", "shadow", "color", "composition", "framing",
    "angle", "shot", "camera", "visual", "bright", "dark",
    "wide", "close", "medium", "establish"
]

ACTION_KEYWORDS: List[str] = [
    "move", "walk", "run", "gesture", "expression", "look",
    "turn", "approach", "interact", "speak", "react"
]

ENVIRONMENT_KEYWORDS: List[str] = [
    "setting", "location", "background", "atmosphere", "weather",
    "time", "season", "indoor", "outdoor", "natural", "urban"
]

EMOTION_KEYWORDS: List[str] = ["feel", "emotion", "mood", "tension"]

TECHNICAL_KEYWORDS: List[str] = ["technical", "production", "equipment"]

VISUAL_QUALITY_KEYWORDS: List[str] = ["visual", "composition", "lighting", "color"]
NARRATIVE_KEYWORDS: List[str] = ["story", "narrative", "character", "emotion"]
PRODUCTION_KEYWORDS: List[str] = ["production", "efficiency", "cost", "time"]
AUDIENCE_KEYWORDS: List[str] = ["audience", "engagement", "appeal", "interest"]


# ── Default Values ───────────────────────────────────────────────────────────

DEFAULT_PROFESSIONAL_REQUIREMENTS: Dict[str, Any] = {
    "camera_angle": "medium_shot",
    "camera_movement": "static",
    "lighting_type": "natural",
    "color_palette": ["#FFFFFF", "#000000", "#808080"],
    "aspect_ratio": "16:9",
    "frame_rate": 24,
    "resolution": "1920x1080"
}

DEFAULT_QUALITY_METRICS: Dict[str, float] = {
    "overall_score": 8.5,
    "visual_clarity": 8.0,
    "narrative_coherence": 8.5,
    "production_feasibility": 9.0,
    "artistic_merit": 8.0
}


# ── Pure Helper Functions ────────────────────────────────────────────────────

def extract_scene_elements(response_text: str) -> Dict[str, Any]:
    """Extract structured scene elements from Echo's natural language response"""
    elements = {
        "visual_elements": [],
        "character_actions": [],
        "environmental_details": [],
        "emotional_content": [],
        "technical_suggestions": []
    }

    sentences = response_text.split('.')
    for sentence in sentences:
        sentence_lower = sentence.lower().strip()

        if any(keyword in sentence_lower for keyword in VISUAL_KEYWORDS):
            elements["visual_elements"].append(sentence.strip())
        elif any(keyword in sentence_lower for keyword in ACTION_KEYWORDS):
            elements["character_actions"].append(sentence.strip())
        elif any(keyword in sentence_lower for keyword in ENVIRONMENT_KEYWORDS):
            elements["environmental_details"].append(sentence.strip())
        elif any(emotion in sentence_lower for emotion in EMOTION_KEYWORDS):
            elements["emotional_content"].append(sentence.strip())
        elif any(tech in sentence_lower for tech in TECHNICAL_KEYWORDS):
            elements["technical_suggestions"].append(sentence.strip())

    return elements


def categorize_optimization_sentences(response_text: str) -> Dict[str, List[str]]:
    """Categorize optimization sentences by type"""
    optimization_suggestions = {
        "visual_improvements": [],
        "narrative_enhancements": [],
        "production_efficiencies": [],
        "audience_engagement": []
    }

    sentences = response_text.split('.')
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        sentence_lower = sentence.lower()

        if any(visual in sentence_lower for visual in VISUAL_QUALITY_KEYWORDS):
            optimization_suggestions["visual_improvements"].append(sentence)
        elif any(narrative in sentence_lower for narrative in NARRATIVE_KEYWORDS):
            optimization_suggestions["narrative_enhancements"].append(sentence)
        elif any(production in sentence_lower for production in PRODUCTION_KEYWORDS):
            optimization_suggestions["production_efficiencies"].append(sentence)
        elif any(audience in sentence_lower for audience in AUDIENCE_KEYWORDS):
            optimization_suggestions["audience_engagement"].append(sentence)

    return optimization_suggestions


def build_quality_metrics(response_text: str) -> Dict[str, float]:
    """Build quality metrics from validation response text"""
    quality_metrics = DEFAULT_QUALITY_METRICS.copy()

    if "excellent" in response_text.lower():
        quality_metrics["overall_score"] = 9.0
    elif "good" in response_text.lower():
        quality_metrics["overall_score"] = 7.5
    elif "poor" in response_text.lower():
        quality_metrics["overall_score"] = 6.0

    return quality_metrics


def extract_validation_recommendations(response_text: str) -> List[str]:
    """Extract recommendations from validation response"""
    recommendations = []

    if "improve" in response_text.lower():
        recommendations.append("Consider improvements as suggested by Echo Brain")

    if "enhance" in response_text.lower():
        recommendations.append("Enhancement opportunities identified")

    if "excellent" in response_text.lower():
        recommendations.append("Scene meets professional standards")

    if not recommendations:
        recommendations.append("Scene description acceptable for production")

    return recommendations


def format_production_notes(scene_elements: Dict[str, Any]) -> str:
    """Generate production notes from scene elements"""
    notes = ["Echo Brain collaboration provided:"]

    if scene_elements.get("visual_elements"):
        notes.append(f"Visual guidance: {len(scene_elements['visual_elements'])} suggestions")

    if scene_elements.get("character_actions"):
        notes.append(f"Character direction: {len(scene_elements['character_actions'])} actions")

    if scene_elements.get("technical_suggestions"):
        notes.append(f"Technical input: {len(scene_elements['technical_suggestions'])} recommendations")

    return ". ".join(notes)


def document_professional_enhancements(
    original_elements: Dict[str, Any],
    enhanced_description: Dict[str, Any]
) -> List[str]:
    """Document what professional enhancements were added"""
    enhancements = []

    if enhanced_description.get("professional_visual_description"):
        enhancements.append("Structured visual description formatting")

    if enhanced_description.get("cinematography_notes"):
        enhancements.append("Professional cinematography notation")

    if enhanced_description.get("technical_specifications"):
        enhancements.append("Complete technical specifications")

    if enhanced_description.get("timing_notes"):
        enhancements.append("Professional timing and pacing notes")

    return enhancements


def generate_echo_timing_notes(
    scene_elements: Dict[str, Any],
    context: Dict[str, Any]
) -> str:
    """Generate timing notes based on Echo's analysis"""
    mood = context.get("mood", "neutral")
    base_timing = "Standard scene pacing"

    if scene_elements.get("character_actions"):
        base_timing += " with character action emphasis"

    if scene_elements.get("emotional_content"):
        base_timing += " allowing for emotional beats"

    if mood == "dramatic":
        base_timing += " with dramatic pauses"
    elif mood == "energetic":
        base_timing += " with quick pacing"
    elif mood == "contemplative":
        base_timing += " with extended holds"

    return base_timing
