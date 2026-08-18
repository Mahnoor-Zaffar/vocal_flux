import asyncio
import time
from enum import StrEnum
from typing import NoReturn

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

    def __init__(
        self,
        engine: InferenceEngine,
        *,
        timeout_seconds: float = 10.0,
        sample_rate: int = 16_000,
        timeout_headroom: float = 3.0,
        timeout_margin: float = 2.0,
        recovery_delay_seconds: float = 3.0,
        recovery_probe_timeout_seconds: float = 8.0,
    ) -> None:
        if min(timeout_seconds, timeout_headroom,
               recovery_delay_seconds, recovery_probe_timeout_seconds) <= 0 or timeout_margin < 0:
            raise ValueError("lifecycle timeouts must be positive")
        self.engine = engine
        self.timeout_seconds = timeout_seconds
        self.sample_rate = sample_rate
        self.timeout_headroom = timeout_headroom
        self.timeout_margin = timeout_margin
        self.recovery_delay_seconds = recovery_delay_seconds
        self.recovery_probe_timeout_seconds = recovery_probe_timeout_seconds
        self._state = ModelState.STARTING
        self._startup_lock = asyncio.Lock()
        self._recovery_task: asyncio.Task | None = None
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
        audio_seconds = len(audio) / self.sample_rate
        budget = max(
            self.timeout_seconds,
            audio_seconds * self.timeout_headroom + self.timeout_margin,
        )
        started_at = time.monotonic_ns()
        self._logger.info(
            "inference_started",
            model=self.engine.config.model,
            audio_seconds=audio_seconds,
            budget_seconds=budget,
        )
        try:
            async with asyncio.timeout(budget):
                result = await self.engine.transcribe(audio, prompt=prompt)
                duration = (time.monotonic_ns() - started_at) / 1_000_000_000
                metrics.observe_inference(duration)
                self._logger.info(
                    "inference_completed",
                    model=self.engine.config.model,
                    audio_seconds=audio_seconds,
                    latency_ms=duration * 1_000,
                    budget_seconds=budget,
                )
                return result
        except TimeoutError as exc:
            return self._degrade(
                code="INFERENCE_TIMEOUT",
                error_type=InferenceTimeoutError,
                message=f"Inference exceeded {budget:g} seconds",
                cause=exc,
            )
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower() or "cuda oom" in str(exc).lower():
                return self._degrade(
                    code="GPU_OOM",
                    error_type=InferenceOutOfMemoryError,
                    message="GPU inference ran out of memory",
                    cause=exc,
                )
            metrics.inference_errors.labels(code="INFERENCE_ERROR").inc()
            self._logger.exception("inference_failed", error_code="INFERENCE_ERROR")
            raise

    def _degrade(
        self,
        *,
        code: str,
        error_type: type[InferenceTimeoutError | InferenceOutOfMemoryError],
        message: str,
        cause: BaseException,
    ) -> NoReturn:
        self._state = ModelState.DEGRADED
        metrics.inference_errors.labels(code=code).inc()
        self._logger.exception("inference_failed", error_code=code)
        self._schedule_recovery()
        raise error_type(message) from cause

    def _schedule_recovery(self) -> None:
        if self._recovery_task is None or self._recovery_task.done():
            self._recovery_task = asyncio.create_task(self._recover())

    async def _recover(self) -> None:
        recover_started_at = time.monotonic_ns()
        try:
            while self._state is ModelState.DEGRADED:
                await asyncio.sleep(self.recovery_delay_seconds)
                try:
                    async with asyncio.timeout(self.recovery_probe_timeout_seconds):
                        await self.engine.warmup()
                except Exception as exc:
                    self._logger.warning(
                        "recovery_probe_failed",
                        error=str(exc)[:200],
                    )
                    continue
                if self._state is ModelState.DEGRADED:
                    self._state = ModelState.READY
                    self._logger.info(
                        "model_recovered",
                        recovery_seconds=(time.monotonic_ns() - recover_started_at) / 1_000_000_000,
                    )
                return
        finally:
            self._recovery_task = None

    async def close(self) -> None:
        if self._state is ModelState.SHUTTING_DOWN:
            return
        self._state = ModelState.SHUTTING_DOWN
        if self._recovery_task is not None:
            self._recovery_task.cancel()
            await asyncio.gather(self._recovery_task, return_exceptions=True)
            self._recovery_task = None
        await self.engine.close()

    async def __aenter__(self) -> "ModelLifecycle":
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
