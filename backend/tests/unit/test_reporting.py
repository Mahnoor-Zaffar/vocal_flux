import json

from tests.benchmarks.reporting import (
    FIRST_TEXT,
    WINDOW_FINAL,
    count_errors,
    evaluate_saturation,
    render_concurrency_markdown,
    render_latency_markdown,
    write_artifact,
    write_fragment,
)


def test_count_errors_sorts_by_code() -> None:
    counts = count_errors(["QUEUE_OVERFLOW", "QUEUE_OVERFLOW", "INFERENCE_TIMEOUT"])
    assert counts == {"INFERENCE_TIMEOUT": 1, "QUEUE_OVERFLOW": 2}


def make_level(streams: int, *, p95: float, drop_rate: float) -> dict:
    return {
        "streams": streams,
        "drop_rate": drop_rate,
        "window_final": {"count": 10.0, "mean": p95 / 2, "p50": p95 / 2, "p95": p95, "p99": p95},
        "rtf": {"count": 10.0, "mean": 0.4, "p50": 0.4, "p95": 0.5, "p99": 0.6},
        "throughput_audio_seconds": 12.0,
    }


def test_evaluate_saturation_picks_highest_passing_level() -> None:
    levels = [
        make_level(1, p95=1.0, drop_rate=0.0),
        make_level(5, p95=2.0, drop_rate=0.005),
        make_level(10, p95=5.0, drop_rate=0.0),
    ]

    result = evaluate_saturation(levels, window_audio_seconds=2.0)

    assert result["passed_by_level"] == {1: True, 5: True, 10: False}
    assert result["saturation_level"] == 5
    assert result["suggested_max_concurrent_sessions"] == 5
    assert result["p95_limit_seconds"] == 4.0
    assert result["max_drop_rate"] == 0.01


def test_evaluate_saturation_handles_no_traffic() -> None:
    levels = [make_level(50, p95=0.0, drop_rate=0.0)]
    levels[0]["window_final"]["count"] = 0.0

    result = evaluate_saturation(levels, window_audio_seconds=2.0)

    assert result["passed_by_level"] == {50: False}
    assert result["saturation_level"] is None


def test_render_latency_markdown_includes_rows() -> None:
    report = {
        "configuration": {
            "model": "small",
            "device": "cpu",
            "compute_type": "int8",
            "beam_size": 1,
        },
        "summary": {
            WINDOW_FINAL: {"count": 15.0, "mean": 0.5, "p50": 0.45, "p95": 0.8, "p99": 1.0},
            FIRST_TEXT: {"count": 15.0, "mean": 4.2, "p50": 4.19, "p95": 5.3, "p99": 6.4},
            "rtf": {"count": 15.0, "mean": 0.35, "p50": 0.34, "p95": 0.5, "p99": 0.6},
        },
    }

    markdown = render_latency_markdown(report)

    assert "## Latency (small, cpu int8, beam 1)" in markdown
    assert "| Window final service latency (s) | 15 | 0.500 | 0.450 | 0.800 | 1.000 |" in markdown
    assert "| Time to first text (s) | 15 | 4.200 | 4.190 | 5.300 | 6.400 |" in markdown
    assert "| Inference realtime factor | 15 | 0.350 | 0.340 | 0.500 | 0.600 |" in markdown


def make_concurrency_report() -> dict:
    levels = [make_level(1, p95=1.0, drop_rate=0.0), make_level(5, p95=5.0, drop_rate=0.2)]
    return {
        "configuration": {
            "model": "small",
            "device": "cpu",
            "compute_type": "int8",
            "beam_size": 1,
        },
        "levels": levels,
        "saturation": evaluate_saturation(levels, window_audio_seconds=2.0),
    }


def test_render_concurrency_markdown_includes_table_and_saturation() -> None:
    markdown = render_concurrency_markdown(make_concurrency_report())

    assert "## Concurrency sweep (small, cpu int8, beam 1)" in markdown
    assert "| 1 | 0.500 | 1.000 |" in markdown
    assert "| yes |" in markdown
    assert "| no |" in markdown
    assert "Saturation point: 1 concurrent sessions" in markdown
    assert "p95 <= 4.000s" in markdown


def test_write_artifact_writes_sorted_json_and_leaves_no_temp(tmp_path) -> None:
    path = tmp_path / "nested" / "report.json"

    write_artifact(path, {"b": 1, "a": 2})

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {"a": 2, "b": 1}
    assert list(payload.keys()) == ["a", "b"]
    assert not list(tmp_path.rglob("*.tmp"))


def test_write_fragment_writes_text_atomically(tmp_path) -> None:
    path = tmp_path / "fragment.md"

    write_fragment(path, "# hello")

    assert path.read_text(encoding="utf-8") == "# hello"
    assert not list(tmp_path.rglob("*.tmp"))
