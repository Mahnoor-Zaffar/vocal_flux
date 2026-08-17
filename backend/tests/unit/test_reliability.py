import pytest

from app.core.security import ConnectionRateLimiter


def test_connection_rate_limiter_uses_a_sliding_window() -> None:
    limiter = ConnectionRateLimiter(max_attempts=2, window_seconds=60)

    assert limiter.allow("client", now=0)
    assert limiter.allow("client", now=1)
    assert not limiter.allow("client", now=2)
    assert limiter.allow("client", now=61)


def test_rate_limits_are_isolated_by_client_key() -> None:
    limiter = ConnectionRateLimiter(max_attempts=1, window_seconds=60)

    assert limiter.allow("first", now=0)
    assert not limiter.allow("first", now=1)
    assert limiter.allow("second", now=1)


@pytest.mark.asyncio
async def test_rate_limiter_clear_releases_client_state() -> None:
    limiter = ConnectionRateLimiter(max_attempts=1, window_seconds=60)
    limiter.allow("client", now=0)

    limiter.clear()

    assert limiter.allow("client", now=1)
