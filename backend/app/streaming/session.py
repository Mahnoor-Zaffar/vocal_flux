import asyncio
from enum import StrEnum

from app.core.config import Settings
from app.inference.lifecycle import ModelLifecycle
from app.schemas.audio import AudioFrameMetadata
from app.schemas.session import ControlMessage
from app.schemas.transcript import (
    ErrorEvent,
    PongEvent,
    ProtocolEvent,
    SessionClosedEvent,
    SessionStartedEvent,
    TranscriptEvent,
)
from app.streaming.context import TranscriptContext
from app.streaming.pipeline import AudioPipeline
from app.streaming.queue import AudioFrame, AudioQueueFull, ControlCommand, SessionQueue
from app.transcript.events import TranscriptUpdate
from app.transcript.state import TranscriptState


class SessionState(StrEnum):
    CONNECTING = "connecting"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    PROCESSING = "processing"
    STOPPING = "stopping"
    ERROR = "error"
    CLOSED = "closed"


class TranscriptionSession:
    def __init__(self, session_id: str, settings: Settings, lifecycle: ModelLifecycle) -> None:
        self.session_id = session_id
        self.settings = settings
        self.state = SessionState.CONNECTING
        self.input_queue = SessionQueue(settings.max_queue_size)
        self.output_queue: asyncio.Queue[ProtocolEvent] = asyncio.Queue()
        self.transcript_state = TranscriptState()
        self.context = TranscriptContext()
        self.pipeline = AudioPipeline(settings, lifecycle, self.context)
        self._processor_task: asyncio.Task[None] | None = None
        self._stream_id: str | None = None
        self._seen_sequences: set[int] = set()
        self._last_sequence = -1
        self._event_sequence = 0
        self._close_lock = asyncio.Lock()

    async def start(self) -> None:
        if self.state is not SessionState.CONNECTING:
            return
        self.state = SessionState.INITIALIZING
        self._processor_task = asyncio.create_task(
            self._process_loop(), name=f"vocalflux-session-{self.session_id}"
        )
        self.state = SessionState.ACTIVE
        await self.emit(SessionStartedEvent(session_id=self.session_id))

    async def submit_audio(self, metadata: AudioFrameMetadata, payload: bytes) -> bool:
        if self.state not in {SessionState.ACTIVE, SessionState.PROCESSING}:
            return False
        if metadata.session_id != self.session_id:
            await self.emit_error("SESSION_MISMATCH", "Audio session does not match connection")
            return False
        if self._stream_id is None:
            self._stream_id = metadata.stream_id
        elif metadata.stream_id != self._stream_id:
            await self.emit_error("STREAM_MISMATCH", "Audio stream does not match session")
            return False
        if len(payload) > self.settings.max_message_size:
            await self.emit_error("MESSAGE_TOO_LARGE", "Audio frame exceeds size limit")
            return False
        if metadata.sequence_number in self._seen_sequences:
            return False
        if metadata.sequence_number < self._last_sequence:
            await self.emit_error(
                "OLD_SEQUENCE", "Audio sequence is older than the accepted cursor"
            )
            return False
        if metadata.sequence_number > self._last_sequence + 1:
            await self.emit_error("MISSING_SEQUENCE", "One or more audio sequences are missing")
        try:
            self.input_queue.put_nowait(AudioFrame(metadata=metadata, payload=payload))
        except AudioQueueFull:
            await self.emit_error("QUEUE_OVERFLOW", "Session audio queue is full")
            if self.settings.queue_overflow_policy == "disconnect":
                await self.close(reason="queue_overflow")
            return False
        self._seen_sequences.add(metadata.sequence_number)
        self._last_sequence = max(self._last_sequence, metadata.sequence_number)
        return True

    async def submit_control(self, message: ControlMessage) -> None:
        if message.type == "ping":
            await self.emit(PongEvent(id=message.id))
            return
        if message.type == "start":
            return
        try:
            self.input_queue.put_nowait(ControlCommand(message.type, message.id))
        except AudioQueueFull:
            await self.emit_error("QUEUE_OVERFLOW", "Session queue is full")
            if message.type == "stop":
                await self.close(reason="queue_overflow")

    async def next_event(self) -> ProtocolEvent:
        return await self.output_queue.get()

    async def emit(self, event: ProtocolEvent) -> None:
        await self.output_queue.put(event)

    async def emit_error(self, code: str, message: str, *, fatal: bool = False) -> None:
        await self.emit(
            ErrorEvent(code=code, message=message, fatal=fatal, session_id=self.session_id)
        )

    async def close(self, *, reason: str = "disconnect") -> None:
        async with self._close_lock:
            if self.state is SessionState.CLOSED:
                return
            self.state = SessionState.STOPPING
            if (
                self._processor_task is not None
                and self._processor_task is not asyncio.current_task()
            ):
                self._processor_task.cancel()
                await asyncio.gather(self._processor_task, return_exceptions=True)
            self.input_queue.drain()
            self.state = SessionState.CLOSED
            await self.emit(SessionClosedEvent(session_id=self.session_id, reason=reason))

    async def _process_loop(self) -> None:
        try:
            while True:
                item = await self.input_queue.get()
                try:
                    self.state = SessionState.PROCESSING
                    if isinstance(item, AudioFrame):
                        transcripts = await self.pipeline.process(item.metadata, item.payload)
                        await self._emit_transcripts(transcripts)
                    elif item.command == "flush":
                        transcripts = await self.pipeline.flush(self._last_sequence)
                        await self._emit_transcripts(transcripts)
                    elif item.command == "stop":
                        transcripts = await self.pipeline.flush(self._last_sequence)
                        await self._emit_transcripts(transcripts)
                        self.state = SessionState.CLOSED
                        await self.emit(
                            SessionClosedEvent(session_id=self.session_id, reason="client_stop")
                        )
                        return
                except Exception as exc:
                    self.state = SessionState.ERROR
                    await self.emit_error("PIPELINE_ERROR", str(exc), fatal=False)
                finally:
                    self.input_queue.task_done()
                    if self.state is SessionState.PROCESSING:
                        self.state = SessionState.ACTIVE
        except asyncio.CancelledError:
            raise
        finally:
            if self.state not in {SessionState.CLOSED, SessionState.STOPPING}:
                self.state = SessionState.ERROR

    async def _emit_transcripts(self, transcripts: list) -> None:
        for transcript in transcripts:
            emission = self.transcript_state.apply(
                TranscriptUpdate(
                    sequence=transcript.sequence,
                    text=transcript.text,
                    is_final=transcript.is_final,
                    latency_ms=transcript.latency_ms,
                )
            )
            if emission.ignored:
                continue
            self.context.update_committed_text(emission.committed_text)
            self._event_sequence += 1
            await self.emit(
                TranscriptEvent(
                    session_id=self.session_id,
                    sequence=self._event_sequence,
                    text=emission.text,
                    is_final=emission.is_final,
                    latency_ms=emission.latency_ms,
                    committed_text=emission.committed_text,
                    unstable_text=emission.unstable_text,
                )
            )
