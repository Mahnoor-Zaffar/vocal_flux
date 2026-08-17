import asyncio
from abc import ABC, abstractmethod

from app.core.config import WhisperConfig
from app.inference.model import AudioArray, TranscriptionResult


class InferenceEngine(ABC):
    """Async abstraction over a speech-to-text inference implementation."""

    def __init__(self, config: WhisperConfig) -> None:
        self.config = config
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    @abstractmethod
    async def load(self) -> None:
        """Load model weights and initialize the compute device."""

    @abstractmethod
    async def warmup(self) -> None:
        """Run a small inference to verify the engine is usable."""

    @abstractmethod
    async def transcribe(self, audio: AudioArray) -> TranscriptionResult:
        """Transcribe one audio window without blocking the event loop."""

    async def close(self) -> None:
        self._loaded = False


class MockInferenceEngine(InferenceEngine):
    """Deterministic engine for unit and integration tests."""

    def __init__(
        self,
        config: WhisperConfig,
        *,
        text: str = "mock transcript",
        delay_seconds: float = 0.0,
    ) -> None:
        super().__init__(config)
        self.text = text
        self.delay_seconds = delay_seconds

    async def load(self) -> None:
        self._loaded = True

    async def warmup(self) -> None:
        if not self.loaded:
            raise RuntimeError("Mock inference engine is not loaded")

    async def transcribe(self, audio: AudioArray) -> TranscriptionResult:
        if not self.loaded:
            raise RuntimeError("Mock inference engine is not loaded")
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        duration = len(audio) / 16_000
        return TranscriptionResult(
            text=self.text,
            segments=(),
            language=self.config.language,
            duration_seconds=duration,
        )
