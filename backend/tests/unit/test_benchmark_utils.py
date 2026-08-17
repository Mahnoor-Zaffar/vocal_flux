import json

import pytest

from tests.benchmarks.benchmark_utils import load_accuracy_manifest, percentile_summary


def test_percentile_summary_reports_distribution() -> None:
    summary = percentile_summary([1.0, 2.0, 3.0, 4.0, 5.0])

    assert summary["count"] == 5.0
    assert summary["mean"] == 3.0
    assert summary["p50"] == 3.0
    assert summary["p95"] == pytest.approx(4.8)


def test_accuracy_manifest_loads_relative_samples(tmp_path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "sample_rate": 16_000,
                "channels": 1,
                "samples": [
                    {
                        "id": "sample-1",
                        "audio": "sample.wav",
                        "reference": "hello",
                        "tags": ["clean"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    _, samples = load_accuracy_manifest(manifest_path)

    assert samples[0].audio_path == tmp_path / "sample.wav"
    assert samples[0].tags == ("clean",)
