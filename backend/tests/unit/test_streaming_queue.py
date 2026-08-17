import asyncio

import pytest

from app.schemas.audio import AudioFrameMetadata
from app.streaming.queue import AudioFrame, AudioQueueFull, SessionQueue


def make_frame(sequence: int) -> AudioFrame:
    return AudioFrame(
        metadata=AudioFrameMetadata(
            type="audio_frame",
            session_id="session",
            stream_id="microphone",
            sequence_number=sequence,
        ),
        payload=b"\x00\x00",
    )


def test_session_queue_is_bounded() -> None:
    queue = SessionQueue(maxsize=1)
    queue.put_nowait(make_frame(0))

    with pytest.raises(AudioQueueFull):
        queue.put_nowait(make_frame(1))


@pytest.mark.asyncio
async def test_queue_item_can_be_consumed_and_completed() -> None:
    queue = SessionQueue(maxsize=1)
    queue.put_nowait(make_frame(0))

    item = await asyncio.wait_for(queue.get(), timeout=0.1)
    queue.task_done()
    await asyncio.wait_for(queue.join(), timeout=0.1)

    assert item.metadata.sequence_number == 0
