from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.websocket import router as websocket_router
from app.core.config import Settings, get_settings
from app.inference.engine import InferenceEngine
from app.inference.lifecycle import ModelLifecycle
from app.inference.whisper import FasterWhisperEngine
from app.streaming.manager import SessionManager


def create_app(
    *,
    settings: Settings | None = None,
    engine: InferenceEngine | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    inference_engine = engine or FasterWhisperEngine(app_settings.whisper_config())
    lifecycle = ModelLifecycle(
        inference_engine,
        timeout_seconds=app_settings.inference_timeout,
    )
    manager = SessionManager(app_settings, lifecycle)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await lifecycle.start()
        try:
            yield
        finally:
            await manager.close_all()
            await lifecycle.close()

    app = FastAPI(title="VocalFlux", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.model_lifecycle = lifecycle
    app.state.session_manager = manager
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(websocket_router)
    return app


app = create_app()
