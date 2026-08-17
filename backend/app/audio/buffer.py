from collections import deque

import numpy as np


class AudioBufferError(ValueError):
    """Base error for bounded audio buffer violations."""


class AudioBufferOverflow(AudioBufferError):
    """Raised when appending audio would exceed a configured bound."""


class AudioBuffer:
    """A bounded FIFO buffer for normalized mono float32 audio."""

    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        max_duration_seconds: float = 300.0,
        max_bytes: int | None = None,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be positive")
        self.sample_rate = sample_rate
        self.max_duration_seconds = max_duration_seconds
        self.max_bytes = max_bytes
        self._chunks: deque[np.ndarray] = deque()
        self._sample_count = 0

    @property
    def sample_count(self) -> int:
        return self._sample_count

    @property
    def byte_count(self) -> int:
        return self._sample_count * np.dtype(np.float32).itemsize

    @property
    def duration_seconds(self) -> float:
        return self._sample_count / self.sample_rate

    def append(self, samples: np.ndarray) -> None:
        chunk = np.asarray(samples, dtype=np.float32)
        if chunk.ndim != 1:
            raise AudioBufferError("Audio buffer accepts one-dimensional mono arrays")
        if not np.isfinite(chunk).all():
            raise AudioBufferError("Audio buffer cannot contain non-finite samples")

        next_samples = self._sample_count + len(chunk)
        if next_samples / self.sample_rate > self.max_duration_seconds:
            raise AudioBufferOverflow("Audio buffer duration limit exceeded")
        next_bytes = next_samples * np.dtype(np.float32).itemsize
        if self.max_bytes is not None and next_bytes > self.max_bytes:
            raise AudioBufferOverflow("Audio buffer byte limit exceeded")
        if len(chunk):
            self._chunks.append(np.ascontiguousarray(chunk))
            self._sample_count = next_samples

    def peek(self, sample_count: int | None = None) -> np.ndarray:
        if sample_count is None:
            sample_count = self._sample_count
        if sample_count < 0 or sample_count > self._sample_count:
            raise ValueError("sample_count must be within the available buffer")
        if sample_count == 0:
            return np.empty(0, dtype=np.float32)

        chunks: list[np.ndarray] = []
        remaining = sample_count
        for chunk in self._chunks:
            take = min(len(chunk), remaining)
            chunks.append(chunk[:take])
            remaining -= take
            if remaining == 0:
                break
        return np.concatenate(chunks).astype(np.float32, copy=False)

    def discard(self, sample_count: int) -> None:
        if sample_count < 0 or sample_count > self._sample_count:
            raise ValueError("sample_count must be within the available buffer")
        remaining = sample_count
        while remaining and self._chunks:
            chunk = self._chunks[0]
            if len(chunk) <= remaining:
                remaining -= len(chunk)
                self._chunks.popleft()
            else:
                self._chunks[0] = chunk[remaining:]
                remaining = 0
        self._sample_count -= sample_count

    def clear(self) -> None:
        self._chunks.clear()
        self._sample_count = 0
