import asyncio
import math
import os
import time
from pathlib import Path
from types import SimpleNamespace

import gpu_spend
import numpy as np
import pytest
from support import committed_bounds, load_accuracy_manifest, load_audio

from app.core.config import Settings
from app.inference.lifecycle import ModelLifecycle
from app.inference.whisper import FasterWhisperEngine

MODEL_TESTS_DEVICE = os.getenv("MODEL_TESTS_DEVICE", "cpu")
MODEL_TESTS_COMPUTE_TYPE = os.getenv("MODEL_TESTS_COMPUTE_TYPE", "int8")
MODEL_TESTS_LANGUAGE = os.getenv("MODEL_TESTS_LANGUAGE") or None
MODEL_NAMES = ("base", "small")
FROZEN_SUBSET = (
    "1089-134691-0006",
    "1580-141084-0003",
    "2961-961-0007",
    "4077-13751-0009",
    "7176-92135-0005",
)
_ACCURACY_ARTIFACT_TEMPLATE = str(
    Path(__file__).resolve().parents[1] / "benchmark-results" / "accuracy-{model}.json"
)


def build_settings(model: str, device: str, compute_type: str) -> Settings:
    return Settings(
        _env_file=None,
        whisper_model=model,
        whisper_device=device,
        whisper_compute_type=compute_type,
        whisper_language=MODEL_TESTS_LANGUAGE,
        whisper_beam_size=1,
    )


def build_engine(model: str, device: str, compute_type: str) -> FasterWhisperEngine:
    return FasterWhisperEngine(build_settings(model, device, compute_type).whisper_config())


@pytest.fixture(scope="session")
def device() -> str:
    return MODEL_TESTS_DEVICE


@pytest.fixture(scope="session")
def compute_type() -> str:
    return MODEL_TESTS_COMPUTE_TYPE


@pytest.fixture(scope="session")
def accuracy_manifest() -> dict[str, tuple[Path, str]]:
    return load_accuracy_manifest()


@pytest.fixture(scope="session", params=FROZEN_SUBSET)
def clip(accuracy_manifest, request):
    clip_id = request.param
    audio_path, reference = accuracy_manifest[clip_id]
    return SimpleNamespace(id=clip_id, audio_path=audio_path, reference=reference)


@pytest.fixture(scope="session")
def committed_bounds_fixture() -> dict[tuple[str, str], tuple[float, float]]:
    return committed_bounds(_ACCURACY_ARTIFACT_TEMPLATE, MODEL_NAMES)


@pytest.fixture(scope="session")
def ceiling(committed_bounds_fixture):
    def _ceiling(model: str, clip_id: str, slack: float) -> tuple[float, float]:
        committed_wer, committed_cer = committed_bounds_fixture[(model, clip_id)]
        return committed_wer + slack, committed_cer + slack

    return _ceiling


@pytest.fixture(scope="session")
def long_audio(accuracy_manifest) -> np.ndarray:
    clip_id = FROZEN_SUBSET[0]
    audio_path, _ = accuracy_manifest[clip_id]
    audio = load_audio(audio_path)
    target = 240 * 16_000
    repeats = math.ceil(target / len(audio))
    return np.tile(audio, repeats)[:target].copy()


_loaded_lifecycles: dict[str, ModelLifecycle] = {}


@pytest.fixture
async def model_lifecycle(device, compute_type):
    async def _make(model: str) -> ModelLifecycle:
        if model not in _loaded_lifecycles:
            lifecycle = ModelLifecycle(build_engine(model, device, compute_type))
            await lifecycle.start()
            _loaded_lifecycles[model] = lifecycle
        return _loaded_lifecycles[model]

    return _make


@pytest.fixture(scope="session", autouse=True)
def _close_model_lifecycles():
    yield
    for lifecycle in _loaded_lifecycles.values():
        asyncio.run(lifecycle.close())
    _loaded_lifecycles.clear()


@pytest.fixture(scope="session", autouse=True)
def _gpu_spend_gate(device):
    started = time.monotonic()
    if device == "cuda":
        committed = gpu_spend.committed_minutes(gpu_spend.load_rows())
        estimate = gpu_spend.estimate_minutes()
        budget = gpu_spend.budget_minutes()
        if not gpu_spend.is_within_budget(committed, estimate, budget):
            pytest.exit(
                f"GPU spend cap exceeded: committed {committed:.1f} min + estimate "
                f"{estimate:.0f} min > budget {budget:.0f} min (raise "
                "GPU_SPEND_BUDGET_MINUTES to allow another run)",
                returncode=3,
            )
    yield
    if device == "cuda":
        gpu_spend.append_row(
            gpu_spend.build_row(
                model="+".join(MODEL_NAMES),
                device=device,
                compute_type=MODEL_TESTS_COMPUTE_TYPE,
                duration_seconds=time.monotonic() - started,
            )
        )
