import time
from dataclasses import dataclass

from app.audio.buffer import AudioBuffer
from app.audio.decoder import decode_pcm16
from app.audio.normalization import normalize_pcm16
from app.audio.vad import EnergyVAD, VADConfig
from app.audio.window import AudioWindow, WindowingStrategy
from app.core.config import Settings
from app.inference.lifecycle import ModelLifecycle
from app.schemas.audio import AudioFrameMetadata


@dataclass(frozen=True, slots=True)
class PipelineTranscript:
    text: str
    sequence: int
    is_final: bool
    latency_ms: float


class AudioPipeline:
    """Decode, gate, buffer, window, and transcribe session audio."""

    def __init__(self, settings: Settings, lifecycle: ModelLifecycle) -> None:
        self.settings = settings
        self.lifecycle = lifecycle
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
    ) -> list[PipelineTranscript]:
        received_at = time.monotonic_ns()
        decoded = decode_pcm16(
            payload,
            sample_rate=self.settings.audio_sample_rate,
            channels=self.settings.audio_channels,
            max_bytes=self.settings.max_message_size,
        )
        normalized = normalize_pcm16(decoded)
        decision = self.vad.process(normalized)
        if decision.is_speech:
            self.buffer.append(normalized)
        windows = self._ready_windows(flush=decision.speech_ended)
        return await self._transcribe_windows(windows, metadata.sequence_number, received_at)

    async def flush(self, sequence: int) -> list[PipelineTranscript]:
        windows = self._ready_windows(flush=True)
        return await self._transcribe_windows(windows, sequence, time.monotonic_ns())

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
        received_at: int,
    ) -> list[PipelineTranscript]:
        results: list[PipelineTranscript] = []
        for window in windows:
            started = time.monotonic_ns()
            result = await self.lifecycle.transcribe(window.samples)
            finished = time.monotonic_ns()
            results.append(
                PipelineTranscript(
                    text=result.text,
                    sequence=sequence,
                    is_final=window.is_final,
                    latency_ms=(finished - started) / 1_000_000,
                )
            )
        _ = received_at
        return results
