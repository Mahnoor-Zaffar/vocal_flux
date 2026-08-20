import asyncio
import time

import pytest

from app.core.config import Settings
from app.inference.lifecycle import InferenceTimeoutError, ModelLifecycle, ModelState
from app.inference.whisper import FasterWhisperEngine


@pytest.mark.model
async def test_degraded_lifecycle_recovers_after_timed_out_inference(
    device, compute_type, long_audio
):
    settings = Settings(
        _env_file=None,
        whisper_model="base",
        whisper_device=device,
        whisper_compute_type=compute_type,
        whisper_beam_size=1,
    )
    lifecycle = ModelLifecycle(
        FasterWhisperEngine(settings.whisper_config()),
        timeout_seconds=4.0,
        timeout_headroom=0.001,
        timeout_margin=0.5,
        recovery_delay_seconds=0.5,
        recovery_probe_timeout_seconds=8.0,
    )
    await lifecycle.start()
    assert lifecycle.state is ModelState.READY
    try:
        with pytest.raises(InferenceTimeoutError):
            await lifecycle.transcribe(long_audio)
        assert lifecycle.state is ModelState.DEGRADED

        deadline = time.monotonic() + 30.0
        while lifecycle.state is not ModelState.READY:
            if time.monotonic() > deadline:
                pytest.fail("lifecycle did not recover to READY within 30s")
            await asyncio.sleep(0.2)

        await lifecycle.engine.warmup()
        assert lifecycle.state is ModelState.READY
    finally:
        await lifecycle.close()
