"""In-memory session store with TTL eviction for interactive visual novel."""
import asyncio
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class SessionState:
    session_id: str
    project_id: int
    project_name: str
    character_slugs: list[str]
    characters: list[dict]  # Character info from DB
    world_context: str
    checkpoint_model: str
    generation_params: dict  # cfg, steps, sampler, scheduler, width, height

    # Story state
    scenes: list[dict] = field(default_factory=list)
    relationships: dict[str, int] = field(default_factory=dict)
    variables: dict[str, str | int | float | bool] = field(default_factory=dict)
    is_ended: bool = False

    # Image tracking: scene_index -> {status, prompt_id, path, ...}
    images: dict[int, dict] = field(default_factory=dict)

    # Prefetch tracking
    prefetch_scene_index: int | None = None
    prefetch_prompt_id: str | None = None

    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def touch(self):
        self.last_active = time.time()

    @property
    def current_scene_index(self) -> int:
        return len(self.scenes) - 1 if self.scenes else -1

    @property
    def story_summary(self) -> str:
        """Condensed summary of last 5 scenes for context window."""
        if not self.scenes:
            return ""
        recent = self.scenes[-5:]
        lines = []
        for s in recent:
            narration = s.get("narration", "")[:150]
            choice = s.get("chosen_text", "")
            line = narration
            if choice:
                line += f" [Player chose: {choice}]"
            lines.append(line)
        return " -> ".join(lines)


class SessionStore:
    """In-memory store for active game sessions."""

    def __init__(self, ttl_seconds: int = 3600):
        self._sessions: dict[str, SessionState] = {}
        self._ttl = ttl_seconds
        self._cleanup_task: asyncio.Task | None = None

    def create(self, **kwargs) -> SessionState:
        session_id = uuid.uuid4().hex[:12]
        session = SessionState(session_id=session_id, **kwargs)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> SessionState | None:
        session = self._sessions.get(session_id)
        if session:
            session.touch()
        return session

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def list_sessions(self) -> list[dict]:
        return [
            {
                "session_id": s.session_id,
                "project_id": s.project_id,
                "project_name": s.project_name,
                "scene_count": len(s.scenes),
                "current_scene_index": s.current_scene_index,
                "is_ended": s.is_ended,
                "created_at": s.created_at,
            }
            for s in self._sessions.values()
        ]

    def start_cleanup(self):
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._eviction_loop())

    async def _eviction_loop(self):
        while True:
            await asyncio.sleep(300)  # Check every 5 minutes
            now = time.time()
            expired = [
                sid for sid, s in self._sessions.items()
                if now - s.last_active > self._ttl
            ]
            for sid in expired:
                self._sessions.pop(sid, None)


# Singleton
store = SessionStore()
