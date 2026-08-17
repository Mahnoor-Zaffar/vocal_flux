import asyncio
import time
from enum import StrEnum

from app.core import metrics
from app.core.logging import get_logger
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
        self._logger = get_logger(__name__)

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
            started_at = time.monotonic_ns()
            self._logger.info("model_loading", model=self.engine.config.model)
            try:
                await self.engine.load()
                self._logger.info("model_loaded", model=self.engine.config.model)
                await self.engine.warmup()
            except Exception as exc:
                self._state = ModelState.FAILED
                self._logger.exception("model_load_failed", model=self.engine.config.model)
                raise ModelLoadError("Inference engine failed to start") from exc
            metrics.model_load_time.observe((time.monotonic_ns() - started_at) / 1_000_000_000)
            self._state = ModelState.READY
            self._logger.info(
                "model_ready",
                model=self.engine.config.model,
                device=self.engine.config.device,
                compute_type=self.engine.config.compute_type,
            )

    async def transcribe(
        self,
        audio: AudioArray,
        *,
        prompt: str | None = None,
    ) -> TranscriptionResult:
        if not self.ready:
            raise EngineNotReadyError(f"Inference engine is {self._state.value}")
        started_at = time.monotonic_ns()
        self._logger.info("inference_started", model=self.engine.config.model)
        try:
            async with asyncio.timeout(self.timeout_seconds):
                result = await self.engine.transcribe(audio, prompt=prompt)
                duration = (time.monotonic_ns() - started_at) / 1_000_000_000
                metrics.observe_inference(duration)
                self._logger.info(
                    "inference_completed",
                    model=self.engine.config.model,
                    latency_ms=duration * 1_000,
                )
                return result
        except TimeoutError as exc:
            self._state = ModelState.DEGRADED
            metrics.inference_errors.labels(code="INFERENCE_TIMEOUT").inc()
            self._logger.exception("inference_failed", error_code="INFERENCE_TIMEOUT")
            raise InferenceTimeoutError(
                f"Inference exceeded {self.timeout_seconds:g} seconds"
            ) from exc
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower() or "cuda oom" in str(exc).lower():
                self._state = ModelState.DEGRADED
                metrics.inference_errors.labels(code="GPU_OOM").inc()
                self._logger.exception("inference_failed", error_code="GPU_OOM")
                raise InferenceOutOfMemoryError("GPU inference ran out of memory") from exc
            metrics.inference_errors.labels(code="INFERENCE_ERROR").inc()
            self._logger.exception("inference_failed", error_code="INFERENCE_ERROR")
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
