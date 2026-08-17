import asyncio
from dataclasses import dataclass

from app.schemas.audio import AudioFrameMetadata


@dataclass(frozen=True, slots=True)
class AudioFrame:
    metadata: AudioFrameMetadata
    payload: bytes


@dataclass(frozen=True, slots=True)
class ControlCommand:
    command: str
    message_id: str | None = None


QueueItem = AudioFrame | ControlCommand


class AudioQueueFull(Exception):
    pass


class SessionQueue:
    """Bounded per-session queue used to apply input backpressure."""

    def __init__(self, maxsize: int) -> None:
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=maxsize)

    @property
    def maxsize(self) -> int:
        return self._queue.maxsize

    @property
    def qsize(self) -> int:
        return self._queue.qsize()

    def put_nowait(self, item: QueueItem) -> None:
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull as exc:
            raise AudioQueueFull from exc

    async def get(self) -> QueueItem:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()

    def drain(self) -> None:
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()
