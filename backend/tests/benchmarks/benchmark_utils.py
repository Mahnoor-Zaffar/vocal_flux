import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


@dataclass(frozen=True, slots=True)
class AccuracySample:
    sample_id: str
    audio_path: Path
    reference: str
    tags: tuple[str, ...]


def load_accuracy_manifest(path: Path) -> tuple[dict[str, Any], list[AccuracySample]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("version") != 1:
        raise ValueError("Unsupported accuracy manifest version")
    if manifest.get("sample_rate") != 16_000 or manifest.get("channels") != 1:
        raise ValueError("Accuracy fixtures must be 16 kHz mono audio")

    samples: list[AccuracySample] = []
    for item in manifest.get("samples", []):
        audio_path = path.parent / item["audio"]
        samples.append(
            AccuracySample(
                sample_id=item["id"],
                audio_path=audio_path,
                reference=item["reference"],
                tags=tuple(item.get("tags", [])),
            )
        )
    return manifest, samples


def load_audio(path: Path, *, expected_sample_rate: int = 16_000) -> np.ndarray:
    samples, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    if sample_rate != expected_sample_rate:
        raise ValueError(f"{path} uses {sample_rate} Hz, expected {expected_sample_rate} Hz")
    if samples.ndim != 1:
        raise ValueError(f"{path} is not mono")
    return np.ascontiguousarray(samples, dtype=np.float32)


def percentile_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": float(len(values)),
        "mean": float(np.mean(array)),
        "p50": float(np.percentile(array, 50)),
        "p95": float(np.percentile(array, 95)),
        "p99": float(np.percentile(array, 99)),
    }


def run_metadata() -> dict[str, Any]:
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        git_sha = "unknown"
    return {
        "run_id": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "timestamp": datetime.now(UTC).isoformat(),
        "git_sha": git_sha,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "executable": sys.executable,
    }


def write_report(path: Path | None, report: dict[str, Any]) -> None:
    payload = json.dumps(report, indent=2, sort_keys=True)
    if path is None:
        print(payload)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{payload}\n", encoding="utf-8")
    print(f"Wrote benchmark report to {path}")
