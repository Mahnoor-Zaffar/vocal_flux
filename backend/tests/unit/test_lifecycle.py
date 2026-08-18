import asyncio

import numpy as np
import pytest

from app.core.config import WhisperConfig
from app.inference.engine import MockInferenceEngine
from app.inference.lifecycle import (
    EngineNotReadyError,
    InferenceOutOfMemoryError,
    InferenceTimeoutError,
    ModelLifecycle,
    ModelState,
)


def make_engine(*, delay_seconds: float = 0.0) -> MockInferenceEngine:
    config = WhisperConfig(model="small", device="cpu", compute_type="int8")
    return MockInferenceEngine(config, delay_seconds=delay_seconds)


@pytest.mark.asyncio
async def test_start_warms_model_and_marks_ready() -> None:
    lifecycle = ModelLifecycle(make_engine())

    await lifecycle.start()

    assert lifecycle.state is ModelState.READY
    assert lifecycle.ready


@pytest.mark.asyncio
async def test_inference_requires_readiness() -> None:
    lifecycle = ModelLifecycle(make_engine())

    with pytest.raises(EngineNotReadyError):
        await lifecycle.transcribe(np.zeros(160, dtype=np.float32))


@pytest.mark.asyncio
async def test_timeout_degrades_lifecycle() -> None:
    lifecycle = ModelLifecycle(
        make_engine(delay_seconds=0.05),
        timeout_seconds=0.01,
        timeout_headroom=0.0001,
        timeout_margin=0.0,
    )
    await lifecycle.start()

    with pytest.raises(InferenceTimeoutError):
        await lifecycle.transcribe(np.zeros(160, dtype=np.float32))

    assert lifecycle.state is ModelState.DEGRADED
    await lifecycle.close()


@pytest.mark.asyncio
async def test_timeout_recovers_to_ready() -> None:
    engine = make_engine(delay_seconds=0.05)
    lifecycle = ModelLifecycle(
        engine,
        timeout_seconds=0.01,
        timeout_headroom=0.0001,
        timeout_margin=0.0,
        recovery_delay_seconds=0.01,
    )
    await lifecycle.start()

    with pytest.raises(InferenceTimeoutError):
        await lifecycle.transcribe(np.zeros(160, dtype=np.float32))
    assert lifecycle.state is ModelState.DEGRADED
    assert not lifecycle.ready

    engine.delay_seconds = 0.0
    await asyncio.sleep(0.05)

    assert lifecycle.state is ModelState.READY
    assert lifecycle.ready
    await lifecycle.close()


@pytest.mark.asyncio
async def test_timeout_budget_scales_with_window_duration() -> None:
    lifecycle = ModelLifecycle(
        make_engine(delay_seconds=0.05),
        timeout_seconds=0.01,
    )
    await lifecycle.start()

    result = await lifecycle.transcribe(np.zeros(16_000 * 2, dtype=np.float32))

    assert result.text == "mock transcript"
    assert lifecycle.state is ModelState.READY
    await lifecycle.close()


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    lifecycle = ModelLifecycle(make_engine())
    await lifecycle.start()

    await asyncio.gather(lifecycle.close(), lifecycle.close())

    assert lifecycle.state is ModelState.SHUTTING_DOWN
    assert not lifecycle.engine.loaded


class OutOfMemoryEngine(MockInferenceEngine):
    async def transcribe(self, audio: np.ndarray, *, prompt: str | None = None):
        raise RuntimeError("CUDA out of memory")


@pytest.mark.asyncio
async def test_cuda_oom_is_classified_and_degrades_engine() -> None:
    lifecycle = ModelLifecycle(OutOfMemoryEngine(make_engine().config))
    await lifecycle.start()

    with pytest.raises(InferenceOutOfMemoryError):
        await lifecycle.transcribe(np.zeros(160, dtype=np.float32))

    assert lifecycle.state is ModelState.DEGRADED
    await lifecycle.close()
