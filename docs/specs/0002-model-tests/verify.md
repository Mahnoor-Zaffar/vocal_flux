# 0002. Verification — Model tests against the real Whisper model

**Date**: 2026-08-19
**Status**: Proposed

Drives the real app against the spec's acceptance criteria. Build: [index.md](index.md). Decision record: [rationale.md](rationale.md). Each step names the criterion it proves. Run from `backend/` with the project lockfile. The suite needs network on the first run to download real weights; it needs no GPU, `MODEL_TESTS_DEVICE` stays unset (default `cpu`).

## Verify steps

1. [x] **Default run skips the suite (AC-1)**: run `uv run pytest -q`. Pass: the run finishes fast, offline, and collects zero tests under `tests/model`; the default marker expression `-m 'not model'` excludes them and mere collection imports no model.
2. [x] **Real model transcription passes on CPU (AC-1, AC-2)**: run `uv run pytest -m model -q`. Pass: base and small load, warm, and each sample of the frozen 5 clip subset transcribes with WER and CER under its committed per sample ceiling plus 0.10.
3. [x] **Degraded recovery proven live (AC-3)**: locate the recovery test's run. Pass: the suite records a real `InferenceTimeoutError` over a 60 second tiled window with a 6.0 second budget, the lifecycle is observed `DEGRADED`, and the warmup probe restores `READY`, all asserted in the test output.
4. [x] **GPU ledger honored with no GPU (AC-5)**: run the ledger unit tests, `uv run pytest tests/model/test_gpu_spend.py -q`. Pass: rows sum, the fixed per run estimate is added, the cap is enforced, and a cpu invocation appends no row. Inspect `backend/benchmark-results/gpu-spend.json` after the CPU runs: it holds no cpu rows.
5. [x] **Budget cap blocks an over budget cuda run (AC-4)**: point `GPU_SPEND_BUDGET_MINUTES` at a spent ledger (e.g. a temp ledger pre loaded with minutes over the cap) and run with `MODEL_TESTS_DEVICE=cuda` if a GPU is present; otherwise read the enforcement path in the unit tests. Pass: the cuda invocation aborts with a clear over budget message and appends no row.
6. [x] **Reproduce from a clean checkout (AC-6)**: on a clone with the pinned lockfile, run the documented `-m model` command. Pass: the suite completes under the recorded bounds, matching the doc rows.

## Value sourcing

| Action | Value produced or displayed | Source |
|---|---|---|
| Transcribe a clip | per sample WER and CER | `jiwer` over reference (manifest field) and hypothesis (real engine output), normalized |
| Assert a bound | WER and CER ceilings | that clip's committed per sample row in `accuracy-{base,small}.json` plus 0.10, so every bound traces to a measured row |
| Run a configuration | base and small rows | parametrization and `MODEL_TESTS_DEVICE` (default `cpu`) mapped to `Settings(whisper_device=...)` |
| Force degraded recovery | tight budget over a long window | named constants: `timeout_seconds=1.0`, headroom `0.1`, margin `0.0`, 60 second tiled window on base |
| Sign a GPU run | ledger row fields | `run_metadata` plus measured wall time, appended at session finish |
| Enforce the cap | committed minutes and the abort | sum of ledger rows plus `GPU_SPEND_ESTIMATE_MINUTES` (default 30) vs `GPU_SPEND_BUDGET_MINUTES` |

## Coverage gaps

- The suite guards the engine and lifecycle on the real model; it does not verify the streaming pipeline (VAD, windowing, partial assembly) end to end, which is out of scope (see index.md Follow-up).
- The accuracy number for the full 20 clip corpus stays owned by `evaluate_accuracy`; this suite uses a 5 clip subset by design.
- On a machine with no GPU, step 5 exercises the cap only through the unit tests, not a live cuda run.
