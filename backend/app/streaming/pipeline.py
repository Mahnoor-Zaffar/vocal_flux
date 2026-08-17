import time
from dataclasses import dataclass

from app.audio.buffer import AudioBuffer
from app.audio.decoder import decode_pcm16
from app.audio.normalization import normalize_pcm16
from app.audio.vad import EnergyVAD, VADConfig
from app.audio.window import AudioWindow, WindowingStrategy
from app.core import metrics
from app.core.config import Settings
from app.core.logging import get_logger
from app.inference.lifecycle import ModelLifecycle
from app.schemas.audio import AudioFrameMetadata
from app.streaming.context import TranscriptContext


@dataclass(frozen=True, slots=True)
class PipelineTranscript:
    text: str
    sequence: int
    is_final: bool
    latency_ms: float
    stage_timings_ms: dict[str, float]
    first_result_latency_ms: float | None = None


class AudioPipeline:
    """Decode, gate, buffer, window, and transcribe session audio."""

    def __init__(
        self,
        settings: Settings,
        lifecycle: ModelLifecycle,
        context: TranscriptContext | None = None,
    ) -> None:
        self.settings = settings
        self.lifecycle = lifecycle
        self.context = context
        self._window_sequence = 0
        self._speech_started_at_ns: int | None = None
        self._first_result_recorded = False
        self._logger = get_logger(__name__)
        self.buffer = AudioBuffer(
            sample_rate=settings.audio_sample_rate,
            max_duration_seconds=settings.max_audio_buffer,
        )
        self.vad = EnergyVAD(
            VADConfig(
                threshold=settings.vad_threshold,
                min_speech_duration_ms=settings.vad_min_speech_duration_ms,
                min_silence_duration_ms=settings.vad_min_silence_duration_ms,
                speech_pad_ms=settings.vad_speech_pad_ms,
                segment_timeout_ms=settings.vad_segment_timeout_ms,
            ),
            sample_rate=settings.audio_sample_rate,
        )
        self.windowing = WindowingStrategy(
            sample_rate=settings.audio_sample_rate,
            window_size_ms=settings.window_size_ms,
            overlap_ms=settings.overlap_ms,
        )

    async def process(
        self,
        metadata: AudioFrameMetadata,
        payload: bytes,
        *,
        received_at_ns: int | None = None,
        enqueued_at_ns: int | None = None,
    ) -> list[PipelineTranscript]:
        processing_started_at = time.monotonic_ns()
        stage_timings = self._queue_timings(
            processing_started_at, received_at_ns, enqueued_at_ns
        )
        decoded = decode_pcm16(
            payload,
            sample_rate=self.settings.audio_sample_rate,
            channels=self.settings.audio_channels,
            max_bytes=self.settings.max_message_size,
        )
        normalized = normalize_pcm16(decoded)
        audio_seconds = len(normalized) / self.settings.audio_sample_rate
        metrics.audio_seconds_processed.inc(audio_seconds)
        vad_started_at = time.monotonic_ns()
        decision = self.vad.process(normalized)
        stage_timings["vad"] = (time.monotonic_ns() - vad_started_at) / 1_000_000
        metrics.observe_stage("vad", stage_timings["vad"] / 1_000)
        if decision.speech_started:
            self._speech_started_at_ns = time.monotonic_ns()
        if decision.is_speech:
            self.buffer.append(normalized)
        window_started_at = time.monotonic_ns()
        windows = self._ready_windows(flush=decision.speech_ended)
        stage_timings["window_formation"] = (time.monotonic_ns() - window_started_at) / 1_000_000
        metrics.observe_stage("window_formation", stage_timings["window_formation"] / 1_000)
        return await self._transcribe_windows(windows, metadata.sequence_number, stage_timings)

    async def flush(self, sequence: int) -> list[PipelineTranscript]:
        window_started_at = time.monotonic_ns()
        windows = self._ready_windows(flush=True)
        window_timing = (time.monotonic_ns() - window_started_at) / 1_000_000
        metrics.observe_stage("window_formation", window_timing / 1_000)
        return await self._transcribe_windows(
            windows,
            sequence,
            {"window_formation": window_timing},
        )

    def _ready_windows(self, *, flush: bool) -> list[AudioWindow]:
        windows: list[AudioWindow] = []
        while True:
            window = self.windowing.next_window(self.buffer, flush=flush)
            if window is None:
                return windows
            windows.append(window)
            if window.is_final:
                return windows

    async def _transcribe_windows(
        self,
        windows: list[AudioWindow],
        sequence: int,
        stage_timings: dict[str, float],
    ) -> list[PipelineTranscript]:
        results: list[PipelineTranscript] = []
        for window in windows:
            started = time.monotonic_ns()
            prompt = self.context.prompt if self.context is not None else None
            result = await self.lifecycle.transcribe(window.samples, prompt=prompt)
            finished = time.monotonic_ns()
            inference_timing = (finished - started) / 1_000_000
            metrics.observe_stage("inference", inference_timing / 1_000)
            self._window_sequence += 1
            if self.context is not None:
                overlap_samples = round(
                    self.settings.audio_sample_rate * self.settings.overlap_ms / 1_000
                )
                self.context.set_audio_overlap(window.samples, overlap_samples)
            first_result_latency: float | None = None
            if self._speech_started_at_ns is not None and not self._first_result_recorded:
                first_result_latency = (finished - self._speech_started_at_ns) / 1_000_000
                metrics.observe_first_result(first_result_latency / 1_000)
                self._first_result_recorded = True
            results.append(
                PipelineTranscript(
                    text=result.text,
                    sequence=self._window_sequence,
                    is_final=window.is_final,
                    latency_ms=inference_timing,
                    stage_timings_ms={**stage_timings, "inference": inference_timing},
                    first_result_latency_ms=first_result_latency,
                )
            )
        _ = sequence
        return results

    def _queue_timings(
        self,
        processing_started_at: int,
        received_at_ns: int | None,
        enqueued_at_ns: int | None,
    ) -> dict[str, float]:
        timings: dict[str, float] = {}
        if received_at_ns is not None and enqueued_at_ns is not None:
            network_ms = max(0, enqueued_at_ns - received_at_ns) / 1_000_000
            queue_ms = max(0, processing_started_at - enqueued_at_ns) / 1_000_000
            timings["network_receive"] = network_ms
            timings["queueing"] = queue_ms
            metrics.observe_stage("network_receive", network_ms / 1_000)
            metrics.observe_stage("queueing", queue_ms / 1_000)
        self._logger.info("audio_pipeline_started")
        return timings
