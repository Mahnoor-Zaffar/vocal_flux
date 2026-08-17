from dataclasses import dataclass
from typing import Any

import numpy as np

from app.core.config import WhisperConfig


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: str
    segments: tuple[TranscriptSegment, ...]
    language: str | None
    duration_seconds: float


AudioArray = np.ndarray[Any, np.dtype[np.float32]]


__all__ = [
    "AudioArray",
    "TranscriptSegment",
    "TranscriptionResult",
    "WhisperConfig",
]
