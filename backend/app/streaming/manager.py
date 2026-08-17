import asyncio
import uuid
from typing import Final

from app.core import metrics
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.security import ConnectionRateLimiter
from app.inference.lifecycle import ModelLifecycle
from app.streaming.session import TranscriptionSession


class SessionLimitExceeded(RuntimeError):
    pass


class InferenceUnavailable(RuntimeError):
    pass


class RateLimitExceeded(RuntimeError):
    pass


class ServerShuttingDown(RuntimeError):
    pass


UNKNOWN_CLIENT: Final = "unknown"


class SessionManager:
    def __init__(self, settings: Settings, lifecycle: ModelLifecycle) -> None:
        self.settings = settings
        self.lifecycle = lifecycle
        self._sessions: dict[str, TranscriptionSession] = {}
        self._lock = asyncio.Lock()
        self.total_sessions = 0
        self.accepting = True
        self._rate_limiter = ConnectionRateLimiter(
            max_attempts=settings.rate_limit_attempts,
            window_seconds=settings.rate_limit_window_seconds,
        )
        self._logger = get_logger(__name__)

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)

    async def create(self, *, client_key: str = UNKNOWN_CLIENT) -> TranscriptionSession:
        async with self._lock:
            if not self.accepting:
                raise ServerShuttingDown
            if not self._rate_limiter.allow(client_key):
                metrics.rejected_sessions.labels(reason="rate_limit").inc()
                raise RateLimitExceeded
            if not self.lifecycle.ready:
                metrics.rejected_sessions.labels(reason="not_ready").inc()
                raise InferenceUnavailable
            if len(self._sessions) >= self.settings.max_concurrent_sessions:
                metrics.rejected_sessions.labels(reason="session_limit").inc()
                raise SessionLimitExceeded
            session_id = uuid.uuid4().hex
            session = TranscriptionSession(session_id, self.settings, self.lifecycle)
            self._sessions[session_id] = session
            self.total_sessions += 1
            metrics.session_started()
            self._logger.info("session_started", session_id=session_id, client_key=client_key)
        await session.start()
        return session

    async def remove(self, session: TranscriptionSession, *, reason: str = "disconnect") -> None:
        await session.close(reason=reason)
        async with self._lock:
            self._sessions.pop(session.session_id, None)
        self._logger.info("session_removed", session_id=session.session_id, reason=reason)

    async def stop_accepting(self) -> None:
        async with self._lock:
            self.accepting = False

    async def close_all(self) -> None:
        sessions = list(self._sessions.values())
        await asyncio.gather(*(session.close(reason="server_shutdown") for session in sessions))
        self._sessions.clear()
        self._rate_limiter.clear()
