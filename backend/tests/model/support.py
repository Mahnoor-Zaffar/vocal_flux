import json
import re
from pathlib import Path

import numpy as np
import soundfile as sf

_PUNCTUATION = re.compile(r"[^\w\s]|_")
_WHITESPACE = re.compile(r"\s+")

ACCURACY_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "accuracy" / "manifest.json"
)


def load_accuracy_manifest(path: Path = ACCURACY_MANIFEST_PATH) -> dict[str, tuple[Path, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data.get("sample_rate") != 16_000 or data.get("channels") != 1:
        raise ValueError("Unsupported accuracy manifest")
    return {
        item["id"]: (path.parent / item["audio"], item["reference"])
        for item in data.get("samples", [])
    }


def load_audio(path: Path) -> np.ndarray:
    samples, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    if sample_rate != 16_000 or samples.ndim != 1:
        raise ValueError(f"{path} must be 16 kHz mono")
    return np.ascontiguousarray(samples, dtype=np.float32)


def normalize_for_scoring(text: str) -> str:
    return _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", text.lower())).strip()


def committed_bounds(
    artifact_template: str, models: tuple[str, ...]
) -> dict[tuple[str, str], tuple[float, float]]:
    bounds: dict[tuple[str, str], tuple[float, float]] = {}
    for model in models:
        path = Path(artifact_template.format(model=model))
        data = json.loads(path.read_text(encoding="utf-8"))
        for sample in data.get("samples", []):
            bounds[(model, sample["id"])] = (float(sample["wer"]), float(sample["cer"]))
    return bounds
