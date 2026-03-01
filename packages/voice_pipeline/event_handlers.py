"""Voice pipeline event handlers — react to training completion, re-synthesis triggers.

Registered at startup in server/app.py via register_voice_event_handlers().
"""

import logging

from packages.core.db import connect_direct
from packages.core.events import event_bus, VOICE_TRAINING_COMPLETED

logger = logging.getLogger(__name__)


async def _on_voice_training_completed(data: dict):
    """When a voice model finishes training, invalidate stale dialogue audio.

    This ensures scenes containing dialogue for the trained character will
    re-synthesize with the newly available higher-quality voice model on
    next generation or batch synthesis run.
    """
    character_slug = data.get("character_slug")
    engine = data.get("engine", "unknown")
    job_id = data.get("job_id", "?")

    if not character_slug:
        logger.warning("voice.training.completed event missing character_slug, skipping")
        return

    conn = await connect_direct()
    try:
        # 1. Null out dialogue_audio_path for scenes containing this character's dialogue
        #    This forces re-synthesis on next build_scene_dialogue() call.
        result = await conn.execute("""
            UPDATE scenes SET dialogue_audio_path = NULL
            WHERE id IN (
                SELECT DISTINCT s.scene_id FROM shots s
                WHERE s.dialogue_character_slug = $1
                  AND s.dialogue_text IS NOT NULL
                  AND s.dialogue_text != ''
            )
            AND dialogue_audio_path IS NOT NULL
        """, character_slug)
        scenes_invalidated = int(result.split()[-1]) if result else 0

        # 2. Mark older edge-tts / lower-tier synthesis jobs as 'stale'
        #    so they won't be mistaken for current.
        result2 = await conn.execute("""
            UPDATE voice_synthesis_jobs
            SET status = 'stale'
            WHERE character_slug = $1
              AND engine IN ('edge-tts', 'xtts')
              AND status = 'completed'
        """, character_slug)
        jobs_staled = int(result2.split()[-1]) if result2 else 0

        logger.info(
            f"voice.training.completed handler: {character_slug} ({engine}, job={job_id}) "
            f"→ invalidated {scenes_invalidated} scene dialogue paths, "
            f"staled {jobs_staled} synthesis jobs"
        )
    except Exception as e:
        logger.error(f"voice.training.completed handler failed: {e}")
    finally:
        await conn.close()


def register_voice_event_handlers():
    """Register all voice pipeline event handlers on the EventBus."""
    event_bus.subscribe(VOICE_TRAINING_COMPLETED, _on_voice_training_completed)
    logger.info("EventBus: voice pipeline event handlers registered")
