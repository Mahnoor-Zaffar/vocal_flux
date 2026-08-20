import gpu_spend
import pytest


def test_empty_ledger_commits_zero_minutes(tmp_path):
    path = tmp_path / "gpu-spend.json"
    assert gpu_spend.load_rows(path) == []
    assert gpu_spend.committed_minutes([]) == 0.0


def test_committed_minutes_sums_durations(tmp_path):
    path = tmp_path / "gpu-spend.json"
    path.write_text(
        '{"runs": [{"duration_seconds": 300}, {"duration_seconds": 600}]}', encoding="utf-8"
    )
    assert gpu_spend.committed_minutes(gpu_spend.load_rows(path)) == pytest.approx(15.0)


def test_budget_check_refuses_a_run_that_would_breach_the_cap():
    assert gpu_spend.is_within_budget(committed=90.0, estimate=30.0, budget=120.0)
    assert not gpu_spend.is_within_budget(committed=100.0, estimate=30.0, budget=120.0)


def test_append_row_persists_and_round_trips(tmp_path):
    path = tmp_path / "gpu-spend.json"
    gpu_spend.append_row(
        gpu_spend.build_row(
            model="small", device="cuda", compute_type="int8", duration_seconds=1.0
        ),
        path,
    )
    gpu_spend.append_row(
        gpu_spend.build_row(
            model="small", device="cuda", compute_type="int8", duration_seconds=2.0
        ),
        path,
    )
    rows = gpu_spend.load_rows(path)
    assert len(rows) == 2
    assert rows[0]["device"] == "cuda"
    assert sum(row["duration_seconds"] for row in rows) == pytest.approx(3.0)


def test_malformed_ledger_raises(tmp_path):
    path = tmp_path / "gpu-spend.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        gpu_spend.load_rows(path)


def test_env_vars_override_budget_and_estimate(monkeypatch):
    monkeypatch.setenv("GPU_SPEND_BUDGET_MINUTES", "60")
    monkeypatch.setenv("GPU_SPEND_ESTIMATE_MINUTES", "5")
    assert gpu_spend.budget_minutes() == 60.0
    assert gpu_spend.estimate_minutes() == 5.0
