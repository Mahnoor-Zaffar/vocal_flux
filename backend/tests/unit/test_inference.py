import numpy as np
import pytest

from app.core.config import WhisperConfig
from app.inference.engine import MockInferenceEngine


@pytest.fixture
def config() -> WhisperConfig:
    return WhisperConfig(model="small", device="cpu", compute_type="int8")


@pytest.mark.asyncio
async def test_mock_engine_transcribes_after_loading(config: WhisperConfig) -> None:
    engine = MockInferenceEngine(config, text="hello world")
    await engine.load()
    await engine.warmup()

    result = await engine.transcribe(np.zeros(16_000, dtype=np.float32))

    assert engine.loaded
    assert result.text == "hello world"
    assert result.duration_seconds == 1.0


@pytest.mark.asyncio
async def test_mock_engine_rejects_inference_before_loading(config: WhisperConfig) -> None:
    engine = MockInferenceEngine(config)

    with pytest.raises(RuntimeError, match="not loaded"):
        await engine.transcribe(np.zeros(160, dtype=np.float32))
