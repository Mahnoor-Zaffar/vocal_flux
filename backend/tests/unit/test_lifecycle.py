import asyncio

import numpy as np
import pytest

from app.core.config import WhisperConfig
from app.inference.engine import MockInferenceEngine
from app.inference.lifecycle import (
    EngineNotReadyError,
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
    lifecycle = ModelLifecycle(make_engine(delay_seconds=0.05), timeout_seconds=0.01)
    await lifecycle.start()

    with pytest.raises(InferenceTimeoutError):
        await lifecycle.transcribe(np.zeros(160, dtype=np.float32))

    assert lifecycle.state is ModelState.DEGRADED


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    lifecycle = ModelLifecycle(make_engine())
    await lifecycle.start()

    await asyncio.gather(lifecycle.close(), lifecycle.close())

    assert lifecycle.state is ModelState.SHUTTING_DOWN
    assert not lifecycle.engine.loaded
