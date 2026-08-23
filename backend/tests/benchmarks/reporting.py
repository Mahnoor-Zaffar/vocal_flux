import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

WINDOW_FINAL = "window_final"
FIRST_TEXT = "first_text"


def count_errors(codes: list[str]) -> dict[str, int]:
    counts: Counter[str] = Counter(codes)
    return dict(sorted(counts.items()))


def evaluate_saturation(
    levels: list[dict[str, Any]],
    window_audio_seconds: float,
    *,
    p95_factor: float = 2.0,
    max_drop_rate: float = 0.01,
) -> dict[str, Any]:
    p95_limit = p95_factor * window_audio_seconds
    gate = {
        "p95_limit_seconds": round(p95_limit, 6),
        "max_drop_rate": max_drop_rate,
        "rule": (
            "highest streams where p95 window final service latency <= limit "
            "and drop rate < max"
        ),
    }
    passed_by_level: dict[int, bool] = {}
    for level in levels:
        summary = level[WINDOW_FINAL]
        passed = (
            summary["count"] > 0
            and summary["p95"] <= p95_limit
            and level["drop_rate"] < max_drop_rate
        )
        passed_by_level[level["streams"]] = passed
    saturation_level = max(
        (streams for streams, ok in passed_by_level.items() if ok), default=None
    )
    return {
        **gate,
        "passed_by_level": dict(sorted(passed_by_level.items())),
        "saturation_level": saturation_level,
        "suggested_max_concurrent_sessions": saturation_level,
    }


def render_latency_markdown(report: dict[str, Any]) -> str:
    config = report["configuration"]
    summary = report["summary"]
    header = (
        f"## Latency ({config['model']}, {config['device']} {config['compute_type']}, "
        f"beam {config['beam_size']})"
    )
    lines = [
        header,
        "",
        "| Metric | Count | Mean | p50 | p95 | p99 |",
        "|---|---|---|---|---|---|",
    ]
    labels = {
        WINDOW_FINAL: "Window final service latency (s)",
        FIRST_TEXT: "Time to first text (s)",
        "rtf": "Inference realtime factor",
    }
    for key, label in labels.items():
        block = summary[key]
        lines.append(
            f"| {label} | {block['count']:.0f} | {block['mean']:.3f} | {block['p50']:.3f} "
            f"| {block['p95']:.3f} | {block['p99']:.3f} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_concurrency_markdown(report: dict[str, Any]) -> str:
    config = report["configuration"]
    header = (
        f"## Concurrency sweep ({config['model']}, {config['device']} "
        f"{config['compute_type']}, beam {config['beam_size']})"
    )
    columns = (
        "| Streams | Window final p50 (s) | Window final p95 (s) "
        "| RTF p50 | Drop rate | Throughput (audio s/s) | Gate pass |"
    )
    lines = [
        header,
        "",
        columns,
        "|---|---|---|---|---|---|---|",
    ]
    for level in report["levels"]:
        final = level[WINDOW_FINAL]
        rtf = level["rtf"]
        passed = report["saturation"]["passed_by_level"].get(level["streams"])
        lines.append(
            f"| {level['streams']} | {final['p50']:.3f} | {final['p95']:.3f} | {rtf['p50']:.2f} "
            f"| {level['drop_rate']:.4f} | {level['throughput_audio_seconds']:.1f} "
            f"| {'yes' if passed else 'no'} |"
        )
    saturation = report["saturation"]
    lines.append("")
    lines.append(
        f"Saturation point: {saturation['saturation_level']} concurrent sessions "
        f"(gate: p95 <= {saturation['p95_limit_seconds']:.3f}s and drop rate < "
        f"{saturation['max_drop_rate']:.2%})."
    )
    lines.append("")
    return "\n".join(lines)


def write_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")
    os.replace(temp_path, path)


def write_fragment(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, path)


def load_average() -> list[float] | None:
    try:
        return [round(value, 2) for value in os.getloadavg()]
    except OSError:
        return None
