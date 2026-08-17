import time
from collections import defaultdict, deque


class ConnectionRateLimiter:
    """Fixed-window connection-attempt limiter keyed by client identity."""

    def __init__(self, *, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: defaultdict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        attempts = self._attempts[key]
        cutoff = current - self.window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if len(attempts) >= self.max_attempts:
            return False
        attempts.append(current)
        return True

    def clear(self) -> None:
        self._attempts.clear()
