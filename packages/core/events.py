"""EventBus — simple in-process async event emitter for cross-package coordination.

No external dependencies. Follows Echo Brain's autonomous/core.py pattern.

Usage:
    from packages.core.events import event_bus

    # Register handler (at module import or startup)
    @event_bus.on("image.rejected")
    async def handle_rejection(data):
        await learning_system.analyze_failure(data)

    # Emit event (at decision point)
    await event_bus.emit("image.rejected", {
        "character_slug": slug,
        "image_name": img_path.name,
        "quality_score": quality_score,
        "categories": categories,
    })
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Event type constants
IMAGE_GENERATED = "image.generated"
IMAGE_APPROVED = "image.approved"
IMAGE_REJECTED = "image.rejected"
GENERATION_SUBMITTED = "generation.submitted"
GENERATION_COMPLETED = "generation.completed"
FEEDBACK_RECORDED = "feedback.recorded"
REGENERATION_QUEUED = "regeneration.queued"
ECHO_BRAIN_CONSULTED = "echo_brain.consulted"
SHOT_GENERATED = "shot.generated"
SHOT_REJECTED = "shot.rejected"

# Production orchestrator events
TRAINING_STARTED = "training.started"
TRAINING_COMPLETE = "training.complete"
SCENE_PLANNING_COMPLETE = "scene_planning.complete"
SCENE_READY = "scene.ready"
EPISODE_ASSEMBLED = "episode.assembled"
EPISODE_PUBLISHED = "episode.published"
PIPELINE_PHASE_ADVANCED = "pipeline.phase_advanced"

# Voice pipeline events
VOICE_SEGMENT_APPROVED = "voice.segment.approved"
VOICE_SEGMENT_REJECTED = "voice.segment.rejected"
VOICE_TRAINING_SUBMITTED = "voice.training.submitted"
VOICE_TRAINING_COMPLETED = "voice.training.completed"
VOICE_SYNTHESIS_COMPLETED = "voice.synthesis.completed"


class EventBus:
    """Async event emitter. Handlers run concurrently via asyncio.gather."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._emit_count: int = 0
        self._error_count: int = 0

    def on(self, event: str):
        """Decorator to register an async handler for an event type."""
        def decorator(fn: Callable[..., Coroutine]):
            self._handlers[event].append(fn)
            logger.debug(f"EventBus: registered {fn.__name__} for '{event}'")
            return fn
        return decorator

    def subscribe(self, event: str, handler: Callable):
        """Imperative handler registration (alternative to decorator)."""
        self._handlers[event].append(handler)

    async def emit(self, event: str, data: dict[str, Any] | None = None):
        """Emit an event to all registered handlers. Errors logged, not raised."""
        handlers = self._handlers.get(event, [])
        if not handlers:
            return

        self._emit_count += 1
        data = data or {}
        data.setdefault("_event", event)
        data.setdefault("_timestamp", datetime.now().isoformat())

        results = await asyncio.gather(
            *(self._safe_call(h, data) for h in handlers),
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self._error_count += 1
                logger.error(
                    f"EventBus handler {handlers[i].__name__} failed on '{event}': {result}"
                )

    async def _safe_call(self, handler: Callable, data: dict):
        """Call handler, converting sync functions to async if needed."""
        result = handler(data)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def stats(self) -> dict:
        """Return bus statistics."""
        return {
            "registered_events": list(self._handlers.keys()),
            "total_handlers": sum(len(h) for h in self._handlers.values()),
            "total_emits": self._emit_count,
            "total_errors": self._error_count,
        }


# Module-level singleton
event_bus = EventBus()


def register_graph_sync_handlers():
    """Register graph sync handlers on the EventBus. Called once at startup."""
    from .graph_sync import (
        on_image_approved,
        on_image_rejected,
        on_generation_submitted,
        on_regeneration_queued,
    )
    event_bus.subscribe(IMAGE_APPROVED, on_image_approved)
    event_bus.subscribe(IMAGE_REJECTED, on_image_rejected)
    event_bus.subscribe(GENERATION_SUBMITTED, on_generation_submitted)
    event_bus.subscribe(REGENERATION_QUEUED, on_regeneration_queued)
    logger.info("EventBus: graph sync handlers registered")
