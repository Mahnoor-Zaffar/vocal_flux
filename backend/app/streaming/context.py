import numpy as np


class TranscriptContext:
    """Bounded committed-text prompt and recent-audio context for Whisper."""

    def __init__(self, *, max_prompt_chars: int = 1_000) -> None:
        if max_prompt_chars <= 0:
            raise ValueError("max_prompt_chars must be positive")
        self.max_prompt_chars = max_prompt_chars
        self._committed_text = ""
        self._audio_overlap = np.empty(0, dtype=np.float32)

    @property
    def prompt(self) -> str | None:
        if not self._committed_text:
            return None
        return self._committed_text[-self.max_prompt_chars :]

    @property
    def audio_overlap(self) -> np.ndarray:
        return self._audio_overlap.copy()

    def update_committed_text(self, text: str) -> None:
        self._committed_text = text[-self.max_prompt_chars :]

    def set_audio_overlap(self, samples: np.ndarray, max_samples: int) -> None:
        if max_samples < 0:
            raise ValueError("max_samples cannot be negative")
        values = np.asarray(samples, dtype=np.float32)
        self._audio_overlap = values[-max_samples:].copy() if max_samples else np.empty(
            0, dtype=np.float32
        )

    def reset(self) -> None:
        self._committed_text = ""
        self._audio_overlap = np.empty(0, dtype=np.float32)
