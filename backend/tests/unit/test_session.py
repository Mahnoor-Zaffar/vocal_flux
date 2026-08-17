import numpy as np
import pytest

from app.core.config import Settings
from app.inference.engine import MockInferenceEngine
from app.inference.lifecycle import ModelLifecycle
from app.schemas.audio import AudioFrameMetadata
from app.streaming.session import TranscriptionSession


def make_metadata(sequence: int, *, session_id: str = "session") -> AudioFrameMetadata:
    return AudioFrameMetadata(
        type="audio_frame",
        session_id=session_id,
        stream_id="microphone",
        sequence_number=sequence,
    )


async def make_session() -> TranscriptionSession:
    settings = Settings(_env_file=None, window_size_ms=1000, overlap_ms=200)
    lifecycle = ModelLifecycle(
        MockInferenceEngine(settings.whisper_config()),
    )
    await lifecycle.start()
    session = TranscriptionSession("session", settings, lifecycle)
    await session.start()
    return session


@pytest.mark.asyncio
async def test_duplicate_and_old_sequences_are_not_processed() -> None:
    session = await make_session()
    await session.next_event()

    payload = np.zeros(2, dtype="<i2").tobytes()
    assert await session.submit_audio(make_metadata(0), payload)
    assert not await session.submit_audio(make_metadata(0), payload)
    assert await session.submit_audio(make_metadata(2), payload)
    assert not await session.submit_audio(make_metadata(1), payload)

    missing = await session.next_event()
    old = await session.next_event()
    assert missing.code == "MISSING_SEQUENCE"
    assert old.code == "OLD_SEQUENCE"
    await session.close()


@pytest.mark.asyncio
async def test_session_duration_closes_session_and_cancels_tasks() -> None:
    settings = Settings(_env_file=None, max_session_duration=0.01)
    lifecycle = ModelLifecycle(MockInferenceEngine(settings.whisper_config()))
    await lifecycle.start()
    session = TranscriptionSession("session", settings, lifecycle)
    await session.start()
    await session.next_event()

    duration_error = await session.next_event()
    closed = await session.next_event()

    assert duration_error.code == "SESSION_DURATION_EXCEEDED"
    assert closed.type == "session_closed"
    assert session.state.value == "closed"
    assert session._processor_task is not None
    assert session._processor_task.done()
