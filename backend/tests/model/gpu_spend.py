import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_LEDGER_PATH = Path(__file__).resolve().parents[2] / "benchmark-results" / "gpu-spend.json"
DEFAULT_BUDGET_MINUTES = 120.0
DEFAULT_ESTIMATE_MINUTES = 30.0


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
    }


def load_rows(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or DEFAULT_LEDGER_PATH
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and isinstance(data.get("runs"), list):
        rows = data["runs"]
    else:
        raise ValueError(f"gpu spend ledger {path} has no runs array")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"gpu spend ledger {path} contains malformed rows")
    return rows


def committed_minutes(rows: list[dict[str, Any]]) -> float:
    return sum(float(row.get("duration_seconds", 0.0)) for row in rows) / 60.0


def estimate_minutes() -> float:
    raw = os.getenv("GPU_SPEND_ESTIMATE_MINUTES")
    return float(raw) if raw else DEFAULT_ESTIMATE_MINUTES


def budget_minutes() -> float:
    raw = os.getenv("GPU_SPEND_BUDGET_MINUTES")
    return float(raw) if raw else DEFAULT_BUDGET_MINUTES


def is_within_budget(committed: float, estimate: float, budget: float) -> bool:
    return committed + estimate <= budget


def build_row(
    *, model: str, device: str, compute_type: str, duration_seconds: float
) -> dict[str, Any]:
    return {
        **run_metadata(),
        "kind": "model-suite",
        "model": model,
        "device": device,
        "compute_type": compute_type,
        "duration_seconds": round(float(duration_seconds), 3),
    }


def append_row(row: dict[str, Any], path: Path | None = None) -> None:
    path = path or DEFAULT_LEDGER_PATH
    rows = load_rows(path)
    rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"runs": rows}, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")
