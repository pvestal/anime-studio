"""
Timing Templates and Data
Large data structures, presets, and pure helper functions for the TimingOrchestrator.
"""

from typing import Dict, List, Any


# ── Pacing Templates ─────────────────────────────────────────────────────────

PACING_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "action": {
        "base_tempo": "fast",
        "shot_duration_range": (0.5, 3.0),
        "transition_speed": "quick",
        "rhythm_pattern": "accelerating",
        "breathing_room": "minimal",
        "peak_intensity_timing": 0.7
    },
    "dialogue": {
        "base_tempo": "moderate",
        "shot_duration_range": (2.0, 8.0),
        "transition_speed": "natural",
        "rhythm_pattern": "conversational",
        "breathing_room": "natural_pauses",
        "peak_intensity_timing": 0.6
    },
    "contemplative": {
        "base_tempo": "slow",
        "shot_duration_range": (4.0, 12.0),
        "transition_speed": "gradual",
        "rhythm_pattern": "meditative",
        "breathing_room": "generous",
        "peak_intensity_timing": 0.8
    },
    "dramatic": {
        "base_tempo": "variable",
        "shot_duration_range": (1.0, 10.0),
        "transition_speed": "dramatic",
        "rhythm_pattern": "building_tension",
        "breathing_room": "strategic",
        "peak_intensity_timing": 0.75
    },
    "romantic": {
        "base_tempo": "gentle",
        "shot_duration_range": (3.0, 8.0),
        "transition_speed": "smooth",
        "rhythm_pattern": "flowing",
        "breathing_room": "intimate",
        "peak_intensity_timing": 0.65
    },
    "comedic": {
        "base_tempo": "snappy",
        "shot_duration_range": (0.8, 4.0),
        "transition_speed": "quick",
        "rhythm_pattern": "punchy",
        "breathing_room": "setup_punchline",
        "peak_intensity_timing": 0.5
    },
    "mysterious": {
        "base_tempo": "deliberate",
        "shot_duration_range": (2.5, 9.0),
        "transition_speed": "suspenseful",
        "rhythm_pattern": "building_mystery",
        "breathing_room": "tension_building",
        "peak_intensity_timing": 0.85
    },
    "energetic": {
        "base_tempo": "upbeat",
        "shot_duration_range": (1.0, 4.0),
        "transition_speed": "dynamic",
        "rhythm_pattern": "energetic_flow",
        "breathing_room": "active",
        "peak_intensity_timing": 0.6
    }
}


# ── Rhythm Patterns ──────────────────────────────────────────────────────────

RHYTHM_PATTERNS: Dict[str, Dict[str, Any]] = {
    "accelerating": {
        "pattern": [1.0, 0.8, 0.6, 0.4, 0.3],
        "description": "Progressively faster pacing",
        "tension_curve": "exponential_increase"
    },
    "decelerating": {
        "pattern": [0.3, 0.4, 0.6, 0.8, 1.0],
        "description": "Progressively slower pacing",
        "tension_curve": "gradual_release"
    },
    "conversational": {
        "pattern": [1.0, 0.8, 1.0, 0.9, 1.0],
        "description": "Natural speech rhythm",
        "tension_curve": "dialogue_peaks"
    },
    "meditative": {
        "pattern": [1.0, 1.2, 1.0, 1.3, 1.0],
        "description": "Contemplative, unhurried",
        "tension_curve": "gentle_waves"
    },
    "building_tension": {
        "pattern": [1.0, 0.9, 0.7, 0.5, 0.3],
        "description": "Tension builds to climax",
        "tension_curve": "dramatic_buildup"
    },
    "flowing": {
        "pattern": [1.0, 0.9, 1.1, 0.95, 1.0],
        "description": "Smooth, flowing rhythm",
        "tension_curve": "gentle_undulation"
    },
    "punchy": {
        "pattern": [0.5, 1.0, 0.3, 1.5, 0.4],
        "description": "Quick setup, strong punchline",
        "tension_curve": "comedy_beats"
    },
    "building_mystery": {
        "pattern": [1.0, 1.1, 0.8, 1.2, 0.6],
        "description": "Mystery and revelation rhythm",
        "tension_curve": "mystery_escalation"
    },
    "energetic_flow": {
        "pattern": [0.8, 0.7, 0.9, 0.6, 0.8],
        "description": "High energy with variation",
        "tension_curve": "energetic_peaks"
    }
}


# ── Tempo Guidelines ─────────────────────────────────────────────────────────

TEMPO_GUIDELINES: Dict[str, Dict[str, Any]] = {
    "dawn": {
        "natural_pace": "awakening",
        "tempo_modifier": 0.9,
        "suggested_rhythm": "gentle_acceleration",
        "breathing_space": "generous"
    },
    "morning": {
        "natural_pace": "active",
        "tempo_modifier": 1.1,
        "suggested_rhythm": "energetic_flow",
        "breathing_space": "moderate"
    },
    "midday": {
        "natural_pace": "peak_energy",
        "tempo_modifier": 1.2,
        "suggested_rhythm": "accelerating",
        "breathing_space": "efficient"
    },
    "afternoon": {
        "natural_pace": "steady",
        "tempo_modifier": 1.0,
        "suggested_rhythm": "conversational",
        "breathing_space": "natural"
    },
    "evening": {
        "natural_pace": "winding_down",
        "tempo_modifier": 0.8,
        "suggested_rhythm": "flowing",
        "breathing_space": "relaxed"
    },
    "night": {
        "natural_pace": "intimate",
        "tempo_modifier": 0.7,
        "suggested_rhythm": "meditative",
        "breathing_space": "contemplative"
    }
}


# ── Beat Structures ──────────────────────────────────────────────────────────

BEAT_STRUCTURES: Dict[str, List[Dict[str, Any]]] = {
    "three_act_micro": [
        {"beat": "setup", "timing_percent": 0.25, "intensity": 0.3},
        {"beat": "confrontation", "timing_percent": 0.50, "intensity": 0.8},
        {"beat": "resolution", "timing_percent": 0.25, "intensity": 0.4}
    ],
    "five_beat_structure": [
        {"beat": "introduction", "timing_percent": 0.15, "intensity": 0.2},
        {"beat": "rising_action", "timing_percent": 0.25, "intensity": 0.6},
        {"beat": "climax", "timing_percent": 0.20, "intensity": 1.0},
        {"beat": "falling_action", "timing_percent": 0.25, "intensity": 0.4},
        {"beat": "conclusion", "timing_percent": 0.15, "intensity": 0.2}
    ],
    "tension_release": [
        {"beat": "build_up", "timing_percent": 0.40, "intensity": 0.7},
        {"beat": "peak_tension", "timing_percent": 0.20, "intensity": 1.0},
        {"beat": "release", "timing_percent": 0.40, "intensity": 0.3}
    ],
    "revelation_structure": [
        {"beat": "mystery_setup", "timing_percent": 0.30, "intensity": 0.4},
        {"beat": "investigation", "timing_percent": 0.40, "intensity": 0.6},
        {"beat": "revelation", "timing_percent": 0.20, "intensity": 0.9},
        {"beat": "aftermath", "timing_percent": 0.10, "intensity": 0.3}
    ]
}


# ── Constant Mappings ────────────────────────────────────────────────────────

TEMPO_BPM_MAP: Dict[str, int] = {
    "slow": 60,
    "gentle": 70,
    "moderate": 80,
    "deliberate": 75,
    "snappy": 100,
    "fast": 120,
    "variable": 90,
    "upbeat": 110
}

SPEED_DURATION_MAP: Dict[str, float] = {
    "quick": 0.2,
    "natural": 0.5,
    "gradual": 1.0,
    "dramatic": 1.5,
    "smooth": 0.8,
    "suspenseful": 2.0,
    "dynamic": 0.3
}

BASE_INSTRUMENTS: Dict[str, List[str]] = {
    "dramatic": ["strings", "brass", "percussion"],
    "romantic": ["strings", "piano", "woodwinds"],
    "mysterious": ["strings", "synthesizer", "ambient"],
    "peaceful": ["acoustic_guitar", "piano", "soft_strings"],
    "energetic": ["percussion", "electric_instruments", "brass"],
    "comedic": ["light_percussion", "woodwinds", "playful_instruments"]
}

MOOD_KEY_SIGNATURES: Dict[str, str] = {
    "dramatic": "D minor",
    "romantic": "F major",
    "mysterious": "F# minor",
    "peaceful": "C major",
    "energetic": "E major",
    "comedic": "G major",
    "melancholic": "A minor",
    "contemplative": "E\u266d major"
}

HARMONIC_SUGGESTIONS: Dict[str, str] = {
    "introduction": "tonic_establishment",
    "rising_action": "tension_building_harmony",
    "climax": "dominant_resolution",
    "falling_action": "subdominant_relaxation",
    "conclusion": "tonic_return",
    "setup": "stable_harmony",
    "confrontation": "dissonant_tension",
    "resolution": "consonant_resolution"
}


# ── Pure Helper Functions ────────────────────────────────────────────────────

def calculate_scene_bpm(base_tempo: str, modifier: float) -> int:
    """Calculate scene BPM (beats per minute) for musical synchronization"""
    base_bpm = TEMPO_BPM_MAP.get(base_tempo, 80)
    return int(base_bpm * modifier)


def suggest_instrumentation(intensity: float, mood: str) -> List[str]:
    """Suggest instrumentation based on intensity and mood"""
    mood_instruments = BASE_INSTRUMENTS.get(mood, ["piano", "strings"])

    if intensity > 0.8:
        return mood_instruments + ["full_orchestra", "dramatic_percussion"]
    elif intensity > 0.6:
        return mood_instruments + ["enhanced_section"]
    elif intensity > 0.4:
        return mood_instruments
    else:
        return mood_instruments[:2]


def intensity_to_dynamics(intensity: float) -> str:
    """Convert intensity to musical dynamics"""
    if intensity >= 0.9:
        return "fortissimo (ff)"
    elif intensity >= 0.7:
        return "forte (f)"
    elif intensity >= 0.5:
        return "mezzo-forte (mf)"
    elif intensity >= 0.3:
        return "mezzo-piano (mp)"
    else:
        return "piano (p)"


def calculate_tempo_variation(intensity: float) -> str:
    """Calculate tempo variation based on intensity"""
    if intensity >= 0.8:
        return "accelerando"
    elif intensity <= 0.3:
        return "ritardando"
    else:
        return "tempo_stable"


def suggest_key_signature(mood: str) -> str:
    """Suggest key signature based on mood"""
    return MOOD_KEY_SIGNATURES.get(mood, "C major")


def suggest_harmony(beat_name: str, mood: str) -> str:
    """Suggest harmonic progression for specific beat"""
    return HARMONIC_SUGGESTIONS.get(beat_name, "stable_harmony")
