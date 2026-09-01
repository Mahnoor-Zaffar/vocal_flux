import json

from tests.benchmarks.reporting import (
    FIRST_PARTIAL,
    WINDOW_FINAL,
    attribute_finals,
    count_errors,
    count_sequence_gaps,
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


def make_timeline(window_ms: float, overlap_ms: float) -> list[tuple[float, int]]:
    started = 1_000_000_000
    return [
        ((index + 1) * 40.0, started + (index + 1) * 40_000_000)
        for index in range(int((window_ms * 4) // 40))
    ]


def test_attribute_finals_uses_sequence_and_overlap() -> None:
    finals = [
        {"sequence": 1, "received_ns": 1_000_000_000 + 5_000_000_000},
        {"sequence": 2, "received_ns": 1_000_000_000 + 9_000_000_000},
    ]

    latencies = attribute_finals(
        finals, make_timeline(4000.0, 1000.0), window_ms=4000.0, overlap_ms=1000.0
    )

    assert latencies == [1.0, 2.0]


def test_attribute_finals_is_nonnegative_with_realtime_pacing() -> None:
    timeline = make_timeline(4000.0, 0.0)
    final = {
        "sequence": 1,
        "received_ns": timeline[-1][1] + 500_000_000,
    }

    latency = attribute_finals([final], timeline, window_ms=4000.0, overlap_ms=0.0)[0]

    assert latency >= 0.0


def test_attribute_finals_clamps_to_last_feed_for_flush() -> None:
    started = 1_000_000_000
    timeline = [(2000.0, started + 2_000_000_000)]
    final = {"sequence": 2, "received_ns": started + 3_000_000_000}

    latency = attribute_finals([final], timeline, window_ms=4000.0, overlap_ms=0.0)[0]

    assert latency == 1.0


def test_attribute_falls_back_to_order_when_sequence_missing() -> None:
    started = 1_000_000_000
    timeline = [(4000.0, started + 4_000_000_000), (8000.0, started + 8_000_000_000)]
    finals = [
        {"received_ns": started + 5_000_000_000},
        {"received_ns": started + 9_000_000_000},
    ]

    latencies = attribute_finals(finals, timeline, window_ms=4000.0, overlap_ms=0.0)

    assert latencies == [1.0, 1.0]


def test_count_sequence_gaps_counts_non_consecutive_windows() -> None:
    assert count_sequence_gaps([]) == 0
    assert count_sequence_gaps([{"sequence": 1}, {"sequence": 2}, {"sequence": 3}]) == 0
    assert count_sequence_gaps([{"sequence": 1}, {"sequence": 3}]) == 1
    assert count_sequence_gaps([{"sequence": 1}, {"sequence": 1}]) == 1


def test_gate_boundaries_exact_limit_and_one_percent_drop() -> None:
    levels = [
        make_level(10, p95=4.0, drop_rate=0.009),  # p95 exactly 2x window, drop under 1%
        make_level(25, p95=4.0, drop_rate=0.010),  # drop exactly 1%
        make_level(50, p95=4.001, drop_rate=0.0),  # a hair over the latency limit
    ]

    result = evaluate_saturation(levels, window_audio_seconds=2.0)

    assert result["passed_by_level"] == {10: True, 25: False, 50: False}
    assert result["saturation_level"] == 10


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
            FIRST_PARTIAL: {"count": 15.0, "mean": 4.2, "p50": 4.19, "p95": 5.3, "p99": 6.4},
            "rtf": {"count": 15.0, "mean": 0.35, "p50": 0.34, "p95": 0.5, "p99": 0.6},
        },
    }

    markdown = render_latency_markdown(report)

    assert "## Latency (small, cpu int8, beam 1)" in markdown
    assert "| Window final service latency (s) | 15 | 0.500 | 0.450 | 0.800 | 1.000 |" in markdown
    assert "| First partial latency (s) | 15 | 4.200 | 4.190 | 5.300 | 6.400 |" in markdown
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
