from dataclasses import dataclass

import numpy as np

from app.audio.buffer import AudioBuffer


@dataclass(frozen=True, slots=True)
class AudioWindow:
    samples: np.ndarray
    start_sample: int
    end_sample: int
    sample_rate: int = 16_000
    is_final: bool = False

    @property
    def duration_seconds(self) -> float:
        return (self.end_sample - self.start_sample) / self.sample_rate


class WindowingStrategy:
    """Create fixed-size windows with configurable overlap from an AudioBuffer."""

    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        window_size_ms: int = 1_000,
        overlap_ms: int = 300,
    ) -> None:
        if window_size_ms <= 0:
            raise ValueError("window_size_ms must be positive")
        if overlap_ms < 0 or overlap_ms >= window_size_ms:
            raise ValueError("overlap_ms must be less than window_size_ms")
        self.sample_rate = sample_rate
        self.window_samples = round(sample_rate * window_size_ms / 1_000)
        self.step_samples = round(sample_rate * (window_size_ms - overlap_ms) / 1_000)
        self._next_start_sample = 0

    def next_window(self, buffer: AudioBuffer, *, flush: bool = False) -> AudioWindow | None:
        available = buffer.sample_count
        if available < self.window_samples and not flush:
            return None
        if available == 0:
            return None

        count = min(available, self.window_samples)
        start = self._next_start_sample
        end = start + count
        samples = buffer.peek(count)
        is_final = flush
        buffer.discard(count if is_final else min(self.step_samples, count))
        self._next_start_sample += count if is_final else min(self.step_samples, count)
        return AudioWindow(
            samples=samples,
            start_sample=start,
            end_sample=end,
            sample_rate=self.sample_rate,
            is_final=is_final,
        )
