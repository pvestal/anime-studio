"""
Cinematography Data
Large data dicts, preset configurations, and constant mappings for the CinematographyEngine.
"""

from typing import Dict, List, Any


# ── Camera Movements ─────────────────────────────────────────────────────────

CAMERA_MOVEMENTS: Dict[str, Dict[str, Any]] = {
    "static": {
        "description": "Fixed camera position",
        "emotional_impact": "stable, focused",
        "technical_notes": "Use sturdy tripod, ensure perfect framing",
        "best_for": ["dialogue", "contemplation", "establishing"]
    },
    "pan": {
        "description": "Horizontal camera movement",
        "emotional_impact": "revealing, following",
        "technical_notes": "Smooth fluid head essential, consistent speed",
        "best_for": ["following_action", "revealing_environment", "connecting_elements"]
    },
    "tilt": {
        "description": "Vertical camera movement",
        "emotional_impact": "dramatic reveal, scale",
        "technical_notes": "Controlled vertical movement, maintain horizon",
        "best_for": ["revealing_scale", "dramatic_emphasis", "character_power"]
    },
    "zoom_in": {
        "description": "Optical magnification increase",
        "emotional_impact": "intensity, focus, urgency",
        "technical_notes": "Smooth zoom control, maintain focus throughout",
        "best_for": ["building_tension", "emotional_climax", "detail_focus"]
    },
    "zoom_out": {
        "description": "Optical magnification decrease",
        "emotional_impact": "revelation, context, isolation",
        "technical_notes": "Reveal broader context gradually",
        "best_for": ["context_revelation", "emotional_distance", "scope_establishment"]
    },
    "dolly_in": {
        "description": "Camera moves physically closer",
        "emotional_impact": "intimacy, engagement",
        "technical_notes": "Smooth track or steadicam, maintain subject focus",
        "best_for": ["emotional_connection", "dramatic_emphasis", "character_focus"]
    },
    "dolly_out": {
        "description": "Camera moves physically away",
        "emotional_impact": "separation, objectivity",
        "technical_notes": "Smooth retreat while maintaining composition",
        "best_for": ["emotional_distance", "context_expansion", "scene_closure"]
    },
    "tracking": {
        "description": "Camera follows subject movement",
        "emotional_impact": "dynamic, energetic",
        "technical_notes": "Smooth parallel movement, anticipate subject path",
        "best_for": ["action_sequences", "character_journey", "dynamic_scenes"]
    },
    "handheld": {
        "description": "Handheld camera for naturalistic feel",
        "emotional_impact": "immediate, realistic, unstable",
        "technical_notes": "Controlled shake, avoid excessive movement",
        "best_for": ["action", "urgency", "personal_moments"]
    },
    "crane": {
        "description": "Elevated camera movement",
        "emotional_impact": "epic, sweeping, grand",
        "technical_notes": "Smooth crane operation, plan trajectory carefully",
        "best_for": ["epic_reveals", "environmental_scope", "dramatic_emphasis"]
    }
}


# ── Shot Sequences ───────────────────────────────────────────────────────────

SHOT_SEQUENCES: Dict[str, List[Dict[str, Any]]] = {
    "dialogue_standard": [
        {"shot": "medium_shot", "duration": 3, "purpose": "establish_characters"},
        {"shot": "over_shoulder", "duration": 4, "purpose": "character_a_speaking"},
        {"shot": "reverse_over_shoulder", "duration": 4, "purpose": "character_b_response"},
        {"shot": "two_shot", "duration": 2, "purpose": "interaction_conclusion"}
    ],
    "action_buildup": [
        {"shot": "wide_shot", "duration": 2, "purpose": "establish_environment"},
        {"shot": "medium_shot", "duration": 3, "purpose": "character_preparation"},
        {"shot": "close_up", "duration": 2, "purpose": "emotional_intensity"},
        {"shot": "extreme_close_up", "duration": 1, "purpose": "critical_detail"}
    ],
    "revelation_sequence": [
        {"shot": "close_up", "duration": 2, "purpose": "character_reaction"},
        {"shot": "medium_shot", "duration": 3, "purpose": "revelation_object"},
        {"shot": "wide_shot", "duration": 4, "purpose": "full_context"},
        {"shot": "extreme_close_up", "duration": 2, "purpose": "emotional_impact"}
    ],
    "contemplation_sequence": [
        {"shot": "medium_shot", "duration": 4, "purpose": "character_state"},
        {"shot": "cutaway", "duration": 3, "purpose": "thought_object"},
        {"shot": "close_up", "duration": 5, "purpose": "internal_processing"},
        {"shot": "wide_shot", "duration": 3, "purpose": "environment_context"}
    ]
}


# ── Transition Types ─────────────────────────────────────────────────────────

TRANSITION_TYPES: Dict[str, Dict[str, Any]] = {
    "cut": {
        "duration": 0.0,
        "description": "Instantaneous scene change",
        "emotional_impact": "direct, immediate",
        "best_for": ["fast_pacing", "parallel_action", "dialogue"]
    },
    "fade_in": {
        "duration": 1.5,
        "description": "Gradual appearance from black",
        "emotional_impact": "gentle_introduction, new_beginning",
        "best_for": ["scene_opening", "time_passage", "dream_sequences"]
    },
    "fade_out": {
        "duration": 1.5,
        "description": "Gradual disappearance to black",
        "emotional_impact": "closure, finality",
        "best_for": ["scene_ending", "death", "time_passage"]
    },
    "dissolve": {
        "duration": 2.0,
        "description": "Gradual blend between scenes",
        "emotional_impact": "smooth_flow, connection",
        "best_for": ["time_passage", "memory", "thematic_connection"]
    },
    "wipe": {
        "duration": 1.0,
        "description": "Geometric transition between scenes",
        "emotional_impact": "stylistic, dynamic",
        "best_for": ["stylistic_choice", "location_change", "time_shift"]
    },
    "iris_in": {
        "duration": 1.2,
        "description": "Circular expansion from center",
        "emotional_impact": "focus, revelation",
        "best_for": ["focus_shift", "dream_state", "flashback"]
    },
    "iris_out": {
        "duration": 1.2,
        "description": "Circular contraction to center",
        "emotional_impact": "closure, focus_loss",
        "best_for": ["fainting", "death", "tunnel_vision"]
    }
}


# ── Lens Specifications ──────────────────────────────────────────────────────

LENS_SPECIFICATIONS: Dict[str, Dict[str, Any]] = {
    "ultra_wide": {
        "focal_length": "14-24mm",
        "field_of_view": "very_wide",
        "distortion": "barrel_distortion",
        "best_for": ["establishing_shots", "environmental_scope", "dramatic_perspective"]
    },
    "wide": {
        "focal_length": "24-35mm",
        "field_of_view": "wide",
        "distortion": "minimal",
        "best_for": ["group_shots", "environmental_context", "action_sequences"]
    },
    "standard": {
        "focal_length": "35-85mm",
        "field_of_view": "natural",
        "distortion": "none",
        "best_for": ["dialogue", "medium_shots", "natural_perspective"]
    },
    "telephoto": {
        "focal_length": "85-200mm",
        "field_of_view": "narrow",
        "distortion": "compression",
        "best_for": ["close_ups", "character_isolation", "background_compression"]
    },
    "super_telephoto": {
        "focal_length": "200mm+",
        "field_of_view": "very_narrow",
        "distortion": "extreme_compression",
        "best_for": ["extreme_close_ups", "distant_subjects", "dramatic_compression"]
    }
}


# ── Shot-to-Lens Mapping ────────────────────────────────────────────────────

SHOT_LENS_MAPPING: Dict[str, str] = {
    "establishing_shot": "ultra_wide",
    "wide_shot": "wide",
    "medium_shot": "standard",
    "two_shot": "standard",
    "over_shoulder": "standard",
    "close_up": "telephoto",
    "extreme_close_up": "super_telephoto",
    "cutaway": "standard"
}
