# 0002. Model tests against the real Whisper model

**Date**: 2026-08-19
**Status**: In Progress

## Summary

We will fill the empty `backend/tests/model/` directory with tests that run against the real Whisper model, not the mock engine. The suite loads and warms a true model, transcribes a fixed subset of the committed accuracy corpus, and asserts the transcripts stay close to the ground truth on base and small configurations on CPU. It also proves the degraded to recovery path live: a deliberately tight timeout on a long real window marks the lifecycle degraded, and the warmup probe restores it to ready. GPU runs append their spend to a small JSON ledger and honor a configurable budget cap, while CPU runs are free and stay the default.

Context and design alternatives: [rationale.md](rationale.md). Verification procedure: [verify.md](verify.md).

## Requirements

**User stories**:
- As a reviewer, I want behavior on a real Whisper model guarded by tests so a regression in the engine or the model adapter fails a run instead of passing silently.
- As an engineer, I want the degraded recovery path proven against a real model so the recoverable degraded state is trusted, not just mocked.
- As the operator, I want the suite's GPU spend recorded and capped so the limited GPU budget stays respected.

**Acceptance criteria** (the contract):
- **AC-1**: A test suite exists under `backend/tests/model/`, gated by a pytest marker `model` with a default marker expression that excludes it `addopts = "-m 'not model'"` in `pyproject.toml`, so the default `uv run pytest` skips it and `uv run pytest -m model` runs it; all real model construction happens lazily inside session scoped fixtures so mere collection never imports or builds a model, and the suite passes on CPU for the base and small configurations.
- **AC-2**: The suite loads and warms a real `FasterWhisperEngine`, transcribes a frozen subset of 5 committed accuracy clips per configuration with the beam pinned, and asserts each sample's WER and CER stay under a ceiling derived from that clip's own committed per sample row in `benchmark-results/accuracy-{base,small}.json` plus a 0.10 margin.
- **AC-3**: The suite proves degraded recovery live: a real inference over a long tiled window under a named tight budget wins the race and raises the timeout, marks the lifecycle degraded, and the warmup probe restores it to ready, asserted by the suite running once on the base configuration.
- **AC-4**: GPU runs append one row to `backend/benchmark-results/gpu-spend.json` (run id, timestamp, git sha, model, device, compute type, measured duration) at session finish, and a cuda run aborts before starting when the committed cumulative minutes plus a fixed per run estimate exceed the `GPU_SPEND_BUDGET_MINUTES` cap; CPU runs record nothing.
- **AC-5**: The ledger logic is covered by unit tests that need no GPU, so the budget guard is proven without a device.
- **AC-6**: A reviewer reproduces the documented `-m model` run from a clean checkout with the pinned lockfile and lands under the recorded bounds.

## Decision

**Chosen option**: Option 1: A gated integration suite against the real model (rationale and alternatives in [rationale.md](rationale.md))

Mark `backend/tests/model/` with a pytest marker excluded by a default marker expression so the default run skips it, run it explicitly with `uv run pytest -m model`, parametrize base and small on CPU int8 with the beam pinned, transcribe a frozen 5 clip subset from the committed accuracy corpus, bound each sample's WER and CER by its committed per sample ceiling plus margin, prove degraded recovery with a forced real timeout and the warmup probe, and keep GPU spend honest with an append only ledger plus a budget cap enforced before spending.

**Implementation skills**: `pytest-coverage` (awesome-copilot, `backend/.agents/skills/pytest-coverage/`) · `faster-whisper` (theplasmak/faster-whisper, `backend/.agents/skills/faster-whisper/`)

## Rationale

Reasoning, options weighed, and references: see [rationale.md](rationale.md).

## Feature design

**Data model sketch**:
- Frozen clip subset: a module constant listing 5 sample ids that exist in `backend/tests/fixtures/accuracy/manifest.json` (`1089-134691-0006`, `3570-5696-0009`, `7021-79740-0007`, `7729-102255-0042`, `61-70970-0013`), each resolving to its committed WAV and ground truth reference through `load_accuracy_manifest`.
- GPU spend ledger (`backend/benchmark-results/gpu-spend.json`): an object with a `rows` array; each row captures `run_id`, `timestamp`, `git_sha`, `model`, `device`, `compute_type`, and `duration_seconds`. Append only, one row per cuda suite invocation, read and summed to enforce the cap.
- No database is involved; the manifest and the ledger are the durable state.

**State transitions**:
The `ModelLifecycle` states already exist: `STARTING → READY → DEGRADED → READY` (recovered) and `READY → SHUTTING_DOWN`. The suite drives the first real instance of `DEGRADED → READY` against a real model and asserts both transitions.

**API surface**:
The suite exposes no HTTP surface. Its interface is the run command:

| Command | What it does | Why |
|---|---|---|
| `uv run pytest` | Skips the model suite (marker expression excludes it) | keeps the default run fast and offline |
| `uv run pytest -m model` | Runs the real model suite on CPU | the documented way to prove behavior on a real model |
| `MODEL_TESTS_DEVICE=cuda uv run pytest -m model` | Runs the suite through the GPU spend gate | exercise the budget path where a GPU is available |

**Value sourcing** (every value each action produces, computes, or displays names where it comes from; a required value with no named source is an undecided input):
| Action | Value produced / displayed | Source |
|---|---|---|
| Transcribe a clip | per sample WER and CER | `jiwer` over reference (manifest field) and hypothesis (real engine output), normalized by `normalize_for_scoring` |
| Assert a bound | the WER and CER ceiling per sample | that clip's own committed per sample row in `benchmark-results/accuracy-{base,small}.json` plus a 0.10 margin, so every clip bound traces to a measured row |
| Run a configuration | the base and small config rows | parametrization over the two names; `MODEL_TESTS_DEVICE` (default `cpu`) is mapped to `Settings(whisper_device=...)` in the model conftest, compute type `int8`, beam pinned to 1 |
| Exclude the suite by default | the default marker expression | `addopts = "-m 'not model'"` in `[tool.pytest.ini_options]`, overridden on the command line by `-m model` |
| Force degraded recovery | the tight budget that times out a long window | named constants in the recovery test: `timeout_seconds=1.0`, `timeout_headroom=0.1`, `timeout_margin=0.0`, window tiled to about 60 seconds on the base model, so budget `max(1.0, 60*0.1+0) = 6.0s` while base CPU needs tens of seconds |
| Sign a GPU run | run id, timestamp, git sha, model, device, compute type, duration | `run_metadata` plus measured wall time around the suite, appended at session finish |
| Enforce the cap | committed cumulative minutes and the decision to abort | sum of `duration_seconds` over ledger `rows` from `gpu-spend.json`, plus the fixed per run `GPU_SPEND_ESTIMATE_MINUTES` (default 30) for the run about to start, compared to `GPU_SPEND_BUDGET_MINUTES` (default 120) |
| Pick device | which compute device the suite runs on | `MODEL_TESTS_DEVICE` environment variable (default `cpu`), dry and free by default |

**Key invariants**:
- The default run never builds or imports a real model: the marker expression excludes the suite and all model construction sits inside session scoped fixtures, so collection alone is lazy and offline.
- The subset is a frozen module constant of ids that must exist in the committed manifest, so the suite is deterministic and offline.
- CPU runs never write to the GPU ledger; only cuda runs append, and only when the cap allows.
- A sample whose WER or CER exceeds its committed ceiling plus margin is a hard failure, never a warning.
- The degraded recovery test only passes if the real model actually times out, marks degraded, and the probe restores ready; a model too fast to time out fails the test rather than silently passing.
- The ledger row for a cuda run is appended at session finish with the measured duration, so the budget ledger never overstates or understates a paid run.

**Security model**:
No user data involved. The suite runs public benchmark audio fixtures and a public model under a local environment. `MODEL_TESTS_DEVICE` and `GPU_SPEND_BUDGET_MINUTES` are local test environment variables, not application credentials.

**Configuration required**:
- `GPU_SPEND_BUDGET_MINUTES`: the cap on committed GPU minutes for this suite, default 120, read from the environment when present.
- `GPU_SPEND_ESTIMATE_MINUTES`: the fixed per run estimate added to committed minutes before a cuda run starts, default 30, so the cap is enforced before spending rather than after.
- `MODEL_TESTS_DEVICE`: computes on `cpu` (default) or `cuda`, mapped to `Settings(whisper_device=...)` in the model conftest, off by default so the suite is free and dry.
- `[tool.pytest.ini_options]`: a `markers` entry for `model` and `addopts = "-m 'not model'"` so the marker is registered and excluded by default.

**Critical test scenarios** (each maps to an acceptance criterion in ## Requirements):
- Happy path: `uv run pytest -m model` on CPU loads and warms the real base and small models, transcribes the frozen 5 clip subset, and every sample lands under its committed ceiling, verifies **AC-1**, **AC-2**
- Failure case: the forced timeout test transcribes a 60 second tiled window with a 6 second budget, asserts `InferenceTimeoutError` and state `DEGRADED`, then polls until the warmup probe restores `READY`, verifies **AC-3**
- Budget case: a cuda run with the ledger near or over the cap (committed minutes plus the 30 minute estimate) aborts before it starts with a clear message and does not overspend; a cpu run appends nothing to the ledger, verifies **AC-4**
- Offline case: the ledger helper unit tests sum rows, add the per run estimate, and enforce the cap with no GPU and no model, verifies **AC-5**
- Reproducibility: a clean checkout with the pinned lockfile reruns the documented command and lands under the recorded bounds, verifies **AC-6**

## Build plan

1. [x] Register the `model` pytest marker in `backend/pyproject.toml`, set the default marker expression `addopts = "-m 'not model'"`, and scaffold `backend/tests/model/` with a conftest that builds a real `FasterWhisperEngine` plus `ModelLifecycle` lazily inside session scoped fixtures, mapping `MODEL_TESTS_DEVICE` to `Settings(whisper_device=...)`, satisfies **AC-1**
2. [x] Add the frozen clip subset constant and the transcription tests: parametrize base and small on CPU int8, beam 1, transcribe each of the 5 committed clips through the real engine and lifecycle, normalize both sides with `normalize_for_scoring`, and assert each sample's WER and CER against its committed per sample ceiling plus margin, satisfies **AC-1**, **AC-2**
3. [x] Add the live degraded recovery test on the base model: tile a committed clip to about 60 seconds and run under `timeout_seconds=1.0`, headroom `0.1`, margin `0.0`, assert the timeout degrades the lifecycle, then await the warmup probe and assert it returns to ready, satisfies **AC-3**
4. [x] Implement the GPU spend ledger module (read rows, sum committed minutes, add the fixed `GPU_SPEND_ESTIMATE_MINUTES`, enforce the cap before a cuda run starts, append one measured row at session finish) and wire it into the suite teardown, plus unit tests for the ledger that need no GPU, satisfies **AC-4**, **AC-5**
5. [ ] Document the `-m model` commands and the recorded bounds in `docs/benchmarking.md`, run the suite on CPU for base and small, and confirm it passes under the bounds from a clean checkout, satisfies **AC-6**

## Consequences

**Positive**:
- Real model behavior is guarded end to end: a regression in the adapter, the model download, or the runtime fails a run.
- The degraded to ready recovery path is proven live once, so the recoverable degraded state is credible.
- CPU stays free and offline by default; GPU use is opt in, recorded, and capped.

**Negative / tradeoffs**:
- The suite downloads and runs real Whisper weights, so the first run needs network and seconds to minutes of CPU per configuration.
- The data set is small (5 clips per config) and clean, so it guards gross regressions, not fine accuracy drift; the full number stays the accuracy benchmark's job.
- The forced timeout recovery test is timing dependent by design; a machine too fast to time out within the tiny budget will fail the test and need the window or budget adjusted.

**Neutral**:
- The frozen subset duplicates a slice of the accuracy corpus by design; the full 20 clip score remains owned by `evaluate_accuracy`.
- The suite reuses `load_accuracy_manifest`, `load_audio`, and `normalize_for_scoring`, so no new corpus plumbing is built.
- GPU spend is a test time concern only; the running service stays unaffected by the ledger.
- The recovery test builds its own lifecycle on the base model; the transcription tests use separate lifecycle instances, so a run sharing a tight budget lifecycle cannot silently pass transcription.
- The ledger is a tracked file under `backend/benchmark-results/`; a real cuda run appends to it and dirties the working tree, which is the expected cost of recording paid spend.

## Follow-up

- [ ] Consider wiring the `-m model` suite into a scheduled or manual workflow (not the default CI test job) so real model regressions surface without slowing every push.
- [ ] Consider a later slice that extends the subset or runs the suite on the RunPod GPU box, where the spend ledger records a real paid run.

## References

Decision record, context, options, and rationale: [rationale.md](rationale.md). Verification procedure: [verify.md](verify.md).
