"""Temporal state decay — pure functions for how character states change between scenes.

Each decay function takes the current value and returns the next value.
Clothing and accessories persist until explicitly changed.
"""

# --- Injury Decay ---
# severity progression: severe → moderate → minor → healed
_INJURY_SEVERITY_DECAY = {
    "severe": "moderate",
    "moderate": "minor",
    "minor": "healed",
    "healed": "healed",
}

# countdown_scenes: how many scenes until an injury auto-decays one step
_DEFAULT_INJURY_COUNTDOWN = 2


def decay_injury(injury: dict) -> dict | None:
    """Decay a single injury. Returns updated injury or None if healed.

    Injury dict: {"type": str, "severity": str, "countdown": int, "location": str}
    """
    severity = injury.get("severity", "minor")
    countdown = injury.get("countdown", _DEFAULT_INJURY_COUNTDOWN)

    if severity == "permanent":
        return injury  # permanent injuries never decay

    if severity == "healed":
        return None

    countdown -= 1
    if countdown <= 0:
        new_severity = _INJURY_SEVERITY_DECAY.get(severity, "healed")
        if new_severity == "healed":
            return None
        return {
            **injury,
            "severity": new_severity,
            "countdown": _DEFAULT_INJURY_COUNTDOWN,
        }

    return {**injury, "countdown": countdown}


def decay_injuries(injuries: list[dict]) -> list[dict]:
    """Decay all injuries, removing healed ones."""
    result = []
    for inj in injuries:
        decayed = decay_injury(inj)
        if decayed is not None:
            result.append(decayed)
    return result


# --- Emotion Decay ---
# furious → angry → irritated → calm (1 scene per step)
_EMOTION_DECAY = {
    "furious": "angry",
    "angry": "irritated",
    "irritated": "calm",
    "threatening": "irritated",
    "nervous": "uneasy",
    "uneasy": "calm",
    "calm": "calm",
    "ecstatic": "happy",
    "happy": "content",
    "content": "calm",
    "terrified": "scared",
    "scared": "anxious",
    "anxious": "calm",
    "devastated": "sad",
    "sad": "melancholy",
    "melancholy": "calm",
    "shocked": "surprised",
    "surprised": "calm",
    "disgusted": "uncomfortable",
    "uncomfortable": "calm",
    "determined": "focused",
    "focused": "calm",
    "serene": "calm",
    "embarrassed": "uncomfortable",
}


def decay_emotion(emotional_state: str) -> str:
    """Decay emotional state by one step toward calm."""
    return _EMOTION_DECAY.get(emotional_state, "calm")


# --- Body State Decay ---
# wet → damp → dry (2 scenes each)
# bloody → stained → clean (2 scenes each)
# dirty → dusty → clean (2 scenes each)
_BODY_STATE_DECAY = {
    "wet": ("damp", 2),
    "damp": ("dry", 1),
    "dry": ("clean", 0),
    "bloody": ("stained", 2),
    "stained": ("clean", 1),
    "dirty": ("dusty", 2),
    "dusty": ("clean", 1),
    "sweaty": ("clean", 1),
    "clean": ("clean", 0),
}


def decay_body_state(body_state: str, scenes_elapsed: int = 1) -> str:
    """Decay body state. Multiple scenes_elapsed can skip steps."""
    current = body_state
    for _ in range(scenes_elapsed):
        entry = _BODY_STATE_DECAY.get(current)
        if entry is None or entry[1] == 0:
            break
        current = entry[0]
    return current


# --- Energy Decay ---
# exhausted → tired → normal (1 scene per step)
_ENERGY_DECAY = {
    "exhausted": "tired",
    "tired": "normal",
    "normal": "normal",
    "energized": "normal",
    "hyperactive": "energized",
}


def decay_energy(energy_level: str) -> str:
    """Decay energy level by one step toward normal."""
    return _ENERGY_DECAY.get(energy_level, "normal")


def apply_all_decay(state: dict) -> dict:
    """Apply all decay rules to a character state dict. Returns new dict.

    Clothing, accessories, and carrying persist unchanged.
    """
    return {
        **state,
        "injuries": decay_injuries(state.get("injuries") or []),
        "emotional_state": decay_emotion(state.get("emotional_state", "calm")),
        "body_state": decay_body_state(state.get("body_state", "clean")),
        "energy_level": decay_energy(state.get("energy_level", "normal")),
        # These persist:
        # clothing, hair_state, accessories, carrying, relationship_context, location_in_scene
    }
