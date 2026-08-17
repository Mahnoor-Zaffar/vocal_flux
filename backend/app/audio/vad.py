from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class VADConfig:
    threshold: float = 0.5
    min_speech_duration_ms: int = 250
    min_silence_duration_ms: int = 500
    speech_pad_ms: int = 30
    segment_timeout_ms: int = 30_000

    def __post_init__(self) -> None:
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        if self.min_speech_duration_ms < 0 or self.min_silence_duration_ms < 0:
            raise ValueError("VAD durations cannot be negative")


@dataclass(frozen=True, slots=True)
class VADDecision:
    is_speech: bool
    speech_started: bool = False
    speech_ended: bool = False
    probability: float = 0.0


class VADStateMachine:
    """Apply duration and timeout rules to per-chunk speech probabilities."""

    def __init__(self, config: VADConfig, *, sample_rate: int = 16_000) -> None:
        self.config = config
        self.sample_rate = sample_rate
        self.is_speech = False
        self._speech_samples = 0
        self._silence_samples = 0
        self._segment_samples = 0

    def update(self, probability: float, sample_count: int) -> VADDecision:
        if sample_count <= 0:
            raise ValueError("sample_count must be positive")
        probability = float(np.clip(probability, 0.0, 1.0))
        speech = probability >= self.config.threshold
        min_speech = self._samples(self.config.min_speech_duration_ms)
        min_silence = self._samples(self.config.min_silence_duration_ms)
        timeout = self._samples(self.config.segment_timeout_ms)

        started = False
        ended = False
        if not self.is_speech:
            self._speech_samples = self._speech_samples + sample_count if speech else 0
            if speech and self._speech_samples >= min_speech:
                self.is_speech = True
                self._segment_samples = self._speech_samples
                self._silence_samples = 0
                started = True
        else:
            self._segment_samples += sample_count
            self._silence_samples = self._silence_samples + sample_count if not speech else 0
            timed_out = timeout > 0 and self._segment_samples >= timeout
            if (not speech and self._silence_samples >= min_silence) or timed_out:
                self.is_speech = False
                self._speech_samples = 0
                self._silence_samples = 0
                self._segment_samples = 0
                ended = True

        return VADDecision(
            is_speech=self.is_speech,
            speech_started=started,
            speech_ended=ended,
            probability=probability,
        )

    def reset(self) -> None:
        self.is_speech = False
        self._speech_samples = 0
        self._silence_samples = 0
        self._segment_samples = 0

    def _samples(self, duration_ms: int) -> int:
        return round(self.sample_rate * duration_ms / 1_000)


class EnergyVAD:
    """Deterministic local VAD useful for tests and CPU-only development."""

    def __init__(self, config: VADConfig, *, sample_rate: int = 16_000) -> None:
        self._state = VADStateMachine(config, sample_rate=sample_rate)

    def process(self, samples: np.ndarray) -> VADDecision:
        if samples.ndim != 1 or len(samples) == 0:
            raise ValueError("VAD expects a non-empty mono audio array")
        probability = float(np.clip(np.sqrt(np.mean(np.square(samples))), 0.0, 1.0))
        return self._state.update(probability, len(samples))

    def reset(self) -> None:
        self._state.reset()


class SileroVAD:
    """Lazy Silero adapter; PyTorch is only required when this class is used."""

    def __init__(self, config: VADConfig, *, sample_rate: int = 16_000) -> None:
        self.config = config
        self.sample_rate = sample_rate
        self._iterator: Any | None = None
        self._is_speech = False

    def _ensure_loaded(self) -> None:
        if self._iterator is not None:
            return
        import torch
        from silero_vad import VADIterator, load_silero_vad

        model = load_silero_vad()
        self._iterator = VADIterator(
            model,
            threshold=self.config.threshold,
            sampling_rate=self.sample_rate,
            min_silence_duration_ms=self.config.min_silence_duration_ms,
            speech_pad_ms=self.config.speech_pad_ms,
        )
        self._torch = torch

    def process(self, samples: np.ndarray) -> VADDecision:
        if samples.ndim != 1 or len(samples) == 0:
            raise ValueError("VAD expects a non-empty mono audio array")
        self._ensure_loaded()
        event = self._iterator(self._torch.from_numpy(samples.astype(np.float32, copy=False)))
        started = isinstance(event, dict) and "start" in event
        ended = isinstance(event, dict) and "end" in event
        if started:
            self._is_speech = True
        if ended:
            self._is_speech = False
        return VADDecision(
            is_speech=self._is_speech,
            speech_started=started,
            speech_ended=ended,
            probability=1.0 if self._is_speech else 0.0,
        )

    def reset(self) -> None:
        if self._iterator is not None:
            self._iterator.reset_states()
        self._is_speech = False
