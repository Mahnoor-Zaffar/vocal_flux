import asyncio
from typing import Any

import numpy as np

from app.core.config import WhisperConfig
from app.inference.engine import InferenceEngine
from app.inference.model import AudioArray, TranscriptionResult, TranscriptSegment


class FasterWhisperEngine(InferenceEngine):
    """faster-whisper adapter with blocking work moved off the event loop."""

    def __init__(self, config: WhisperConfig) -> None:
        super().__init__(config)
        self._model: Any | None = None

    async def load(self) -> None:
        self._model = await asyncio.to_thread(self._load_sync)
        self._loaded = True

    def _load_sync(self) -> Any:
        from faster_whisper import WhisperModel

        return WhisperModel(
            self.config.model,
            device=self.config.device,
            compute_type=self.config.compute_type,
        )

    async def warmup(self) -> None:
        if not self.loaded:
            raise RuntimeError("Faster-whisper engine is not loaded")
        silence = np.zeros(16_000, dtype=np.float32)
        await self.transcribe(silence)

    async def transcribe(
        self,
        audio: AudioArray,
        *,
        prompt: str | None = None,
    ) -> TranscriptionResult:
        if not self.loaded or self._model is None:
            raise RuntimeError("Faster-whisper engine is not loaded")
        samples = np.ascontiguousarray(audio, dtype=np.float32)
        return await asyncio.to_thread(self._transcribe_sync, samples, prompt)

    def _transcribe_sync(self, audio: AudioArray, prompt: str | None) -> TranscriptionResult:
        segments, info = self._model.transcribe(
            audio,
            language=self.config.language,
            beam_size=self.config.beam_size,
            vad_filter=False,
            initial_prompt=prompt,
        )
        collected = tuple(
            TranscriptSegment(
                start=float(segment.start),
                end=float(segment.end),
                text=segment.text.strip(),
            )
            for segment in segments
        )
        return TranscriptionResult(
            text=" ".join(segment.text for segment in collected).strip(),
            segments=collected,
            language=getattr(info, "language", self.config.language),
            duration_seconds=len(audio) / 16_000,
        )

    async def close(self) -> None:
        self._model = None
        await super().close()
