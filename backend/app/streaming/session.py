import asyncio
import time
from enum import StrEnum

from app.core import metrics
from app.core.config import Settings
from app.core.logging import get_logger
from app.inference.lifecycle import (
    InferenceOutOfMemoryError,
    InferenceTimeoutError,
    ModelLifecycle,
)
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
        self._created_at = time.monotonic()
        self._duration_task: asyncio.Task[None] | None = None
        self._metrics_recorded = False
        self._closed_event = asyncio.Event()
        self._logger = get_logger(__name__).bind(session_id=session_id)

    async def start(self) -> None:
        if self.state is not SessionState.CONNECTING:
            return
        self.state = SessionState.INITIALIZING
        self._processor_task = asyncio.create_task(
            self._process_loop(), name=f"vocalflux-session-{self.session_id}"
        )
        self._duration_task = asyncio.create_task(
            self._enforce_duration(), name=f"vocalflux-duration-{self.session_id}"
        )
        self.state = SessionState.ACTIVE
        await self.emit(SessionStartedEvent(session_id=self.session_id))

    async def submit_audio(
        self,
        metadata: AudioFrameMetadata,
        payload: bytes,
        *,
        received_at_ns: int | None = None,
    ) -> bool:
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
            self.input_queue.put_nowait(
                AudioFrame(
                    metadata=metadata,
                    payload=payload,
                    received_at_ns=received_at_ns,
                    enqueued_at_ns=time.monotonic_ns(),
                )
            )
            metrics.queue_depth.set(self.input_queue.qsize)
            self._logger.info(
                "audio_received",
                sequence=metadata.sequence_number,
                queue_depth=self.input_queue.qsize,
            )
        except AudioQueueFull:
            await self.emit_error("QUEUE_OVERFLOW", "Session audio queue is full")
            metrics.queue_overflows.labels(policy=self.settings.queue_overflow_policy).inc()
            metrics.audio_dropped.inc(len(payload) / 2 / self.settings.audio_sample_rate)
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
            metrics.queue_overflows.labels(policy=self.settings.queue_overflow_policy).inc()
            if message.type == "stop":
                await self.close(reason="queue_overflow")

    async def next_event(self) -> ProtocolEvent:
        return await self.output_queue.get()

    async def wait_closed(self) -> None:
        await self._closed_event.wait()

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
                self._duration_task is not None
                and self._duration_task is not asyncio.current_task()
            ):
                self._duration_task.cancel()
                await asyncio.gather(self._duration_task, return_exceptions=True)
            if (
                self._processor_task is not None
                and self._processor_task is not asyncio.current_task()
            ):
                self._processor_task.cancel()
                await asyncio.gather(self._processor_task, return_exceptions=True)
            self.input_queue.drain()
            self.state = SessionState.CLOSED
            self._record_closed(reason)
            await self.emit(SessionClosedEvent(session_id=self.session_id, reason=reason))

    async def _process_loop(self) -> None:
        try:
            while True:
                item = await self.input_queue.get()
                metrics.queue_depth.set(self.input_queue.qsize)
                try:
                    self.state = SessionState.PROCESSING
                    if isinstance(item, AudioFrame):
                        transcripts = await self.pipeline.process(
                            item.metadata,
                            item.payload,
                            received_at_ns=item.received_at_ns,
                            enqueued_at_ns=item.enqueued_at_ns,
                        )
                        await self._emit_transcripts(transcripts)
                    elif item.command == "flush":
                        transcripts = await self.pipeline.flush(self._last_sequence)
                        await self._emit_transcripts(transcripts)
                    elif item.command == "stop":
                        transcripts = await self.pipeline.flush(self._last_sequence)
                        await self._emit_transcripts(transcripts)
                        self.state = SessionState.CLOSED
                        if self._duration_task is not None:
                            self._duration_task.cancel()
                            await asyncio.gather(self._duration_task, return_exceptions=True)
                        self._record_closed("client_stop")
                        await self.emit(
                            SessionClosedEvent(session_id=self.session_id, reason="client_stop")
                        )
                        return
                except Exception as exc:
                    self.state = SessionState.ERROR
                    if isinstance(exc, InferenceTimeoutError):
                        code = "INFERENCE_TIMEOUT"
                        message = "Transcription inference exceeded the configured timeout."
                        fatal = False
                    elif isinstance(exc, InferenceOutOfMemoryError):
                        code = "GPU_OOM"
                        message = "GPU inference resources were exhausted."
                        fatal = True
                    else:
                        code = "PIPELINE_ERROR"
                        message = "Audio processing failed for this session."
                        fatal = False
                    metrics.inference_errors.labels(code=code).inc()
                    self._logger.exception("session_processing_failed", error_code=code)
                    await self.emit_error(code, message, fatal=fatal)
                    if fatal:
                        await self.close(reason=code.lower())
                    else:
                        self.state = SessionState.ACTIVE
                finally:
                    self.input_queue.task_done()
                    if self.state is SessionState.PROCESSING:
                        self.state = SessionState.ACTIVE
        except asyncio.CancelledError:
            raise
        finally:
            if self.state not in {SessionState.CLOSED, SessionState.STOPPING}:
                self.state = SessionState.ERROR

    def _record_closed(self, reason: str) -> None:
        if self._metrics_recorded:
            return
        self._metrics_recorded = True
        metrics.session_closed(time.monotonic() - self._created_at)
        self._logger.info("session_closed", reason=reason)
        self._closed_event.set()

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
                    stage_timings_ms=transcript.stage_timings_ms,
                    first_result_latency_ms=transcript.first_result_latency_ms,
                )
            )

    async def _enforce_duration(self) -> None:
        try:
            await asyncio.sleep(self.settings.max_session_duration)
            await self.emit_error("SESSION_DURATION_EXCEEDED", "Maximum session duration reached")
            await self.close(reason="max_session_duration")
        except asyncio.CancelledError:
            raise
