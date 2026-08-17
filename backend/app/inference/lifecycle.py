import asyncio
from enum import StrEnum

from app.inference.engine import InferenceEngine
from app.inference.model import AudioArray, TranscriptionResult


class ModelState(StrEnum):
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    SHUTTING_DOWN = "shutting_down"
    FAILED = "failed"


class ModelLoadError(RuntimeError):
    pass


class EngineNotReadyError(RuntimeError):
    pass


class InferenceTimeoutError(TimeoutError):
    pass


class InferenceOutOfMemoryError(RuntimeError):
    pass


class ModelLifecycle:
    """Owns model startup, readiness, inference timeouts, and shutdown."""

    def __init__(self, engine: InferenceEngine, *, timeout_seconds: float = 10.0) -> None:
        self.engine = engine
        self.timeout_seconds = timeout_seconds
        self._state = ModelState.STARTING
        self._startup_lock = asyncio.Lock()

    @property
    def state(self) -> ModelState:
        return self._state

    @property
    def ready(self) -> bool:
        return self._state is ModelState.READY and self.engine.loaded

    async def start(self) -> None:
        async with self._startup_lock:
            if self.ready:
                return
            if self._state is ModelState.SHUTTING_DOWN:
                raise ModelLoadError("Cannot start a shutting-down model")
            self._state = ModelState.STARTING
            try:
                await self.engine.load()
                await self.engine.warmup()
            except Exception as exc:
                self._state = ModelState.FAILED
                raise ModelLoadError("Inference engine failed to start") from exc
            self._state = ModelState.READY

    async def transcribe(
        self,
        audio: AudioArray,
        *,
        prompt: str | None = None,
    ) -> TranscriptionResult:
        if not self.ready:
            raise EngineNotReadyError(f"Inference engine is {self._state.value}")
        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await self.engine.transcribe(audio, prompt=prompt)
        except TimeoutError as exc:
            self._state = ModelState.DEGRADED
            raise InferenceTimeoutError(
                f"Inference exceeded {self.timeout_seconds:g} seconds"
            ) from exc
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower() or "cuda oom" in str(exc).lower():
                self._state = ModelState.DEGRADED
                raise InferenceOutOfMemoryError("GPU inference ran out of memory") from exc
            raise

    async def close(self) -> None:
        if self._state is ModelState.SHUTTING_DOWN:
            return
        self._state = ModelState.SHUTTING_DOWN
        await self.engine.close()

    async def __aenter__(self) -> "ModelLifecycle":
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
