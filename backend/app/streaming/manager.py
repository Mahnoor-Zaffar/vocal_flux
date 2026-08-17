import asyncio
import uuid

from app.core.config import Settings
from app.inference.lifecycle import ModelLifecycle
from app.streaming.session import TranscriptionSession


class SessionLimitExceeded(RuntimeError):
    pass


class InferenceUnavailable(RuntimeError):
    pass


class SessionManager:
    def __init__(self, settings: Settings, lifecycle: ModelLifecycle) -> None:
        self.settings = settings
        self.lifecycle = lifecycle
        self._sessions: dict[str, TranscriptionSession] = {}
        self._lock = asyncio.Lock()
        self.total_sessions = 0

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)

    async def create(self) -> TranscriptionSession:
        async with self._lock:
            if not self.lifecycle.ready:
                raise InferenceUnavailable
            if len(self._sessions) >= self.settings.max_concurrent_sessions:
                raise SessionLimitExceeded
            session_id = uuid.uuid4().hex
            session = TranscriptionSession(session_id, self.settings, self.lifecycle)
            self._sessions[session_id] = session
            self.total_sessions += 1
        await session.start()
        return session

    async def remove(self, session: TranscriptionSession, *, reason: str = "disconnect") -> None:
        await session.close(reason=reason)
        async with self._lock:
            self._sessions.pop(session.session_id, None)

    async def close_all(self) -> None:
        sessions = list(self._sessions.values())
        await asyncio.gather(*(session.close(reason="server_shutdown") for session in sessions))
        self._sessions.clear()
