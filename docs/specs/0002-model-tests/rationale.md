# 0002. Rationale — Model tests against the real Whisper model

## Context

The backend ships an `InferenceEngine` contract with two implementations: `MockInferenceEngine` for unit and integration tests, and `FasterWhisperEngine` that wraps the real faster-whisper model, running blocking CTranslate2 work off the event loop in a thread (`backend/app/inference/whisper.py`). The `ModelLifecycle` owns startup, readiness, scaled timeouts, and a degraded state that recovers with a warmup probe (`backend/app/inference/lifecycle.py`).

Every existing test drives the mock engine. The behavior of the real model, the adapter's audio handling, and the true degraded to ready recovery path has no test coverage at all: a regression in the adapter, the model download, or the runtime would pass the unit suite silently. The directory `backend/tests/model/` exists and is empty, waiting for exactly this.

Two forces shape the design. First, the real model run is slow and heavy: loading weights, warming up, and transcribing takes seconds per clip on CPU and costs real GPU minutes when a GPU is present. The suite must be opt in, never part of the fast default run. Second, the project keeps a deliberately limited GPU budget (ADR 006: ephemeral, on demand GPU), so any test that runs on cuda must record its spend and respect a cap, or a developer could silently exhaust the budget by rerunning tests.

The committed accuracy corpus (spec 0001) gives the suite a free, deterministic ground truth: 20 clips, each with a reference transcript, plus committed WER and CER artifacts per configuration. Reusing it means the model suite needs no new fixtures and its assertions trace to real numbers, not guesses.

## Options considered

### Option 1: A gated integration suite against the real model

Mark `backend/tests/model/` with a pytest marker so the default run skips it, run it explicitly with `uv run pytest -m model`, parametrize base and small on CPU int8 with the beam pinned, transcribe a frozen 5 clip subset from the committed accuracy corpus, assert bounded WER and CER traced to the committed artifacts, force a real timeout to prove degraded to ready recovery, and keep GPU spend honest with an append only ledger and a budget cap.

**Pros**:
- Covers the real adapter, real model, and real lifecycle recovery path, the exact gaps in the current suite.
- The committed corpus gives deterministic ground truth and a directly traceable assertion bound, with no new fixtures.
- Marker gating keeps the default test run fast, offline, and free; GPU use is explicit, recorded, and capped.

**Cons**:
- Slower and heavier than mock tests: real weights, warmup, and seconds per clip on CPU.
- Circuit for the 5 clip subset revisits a slice of the accuracy benchmark territory; the two jobs must stay distinct (guard vs measure).

### Option 2: Full 20 clip corpus per configuration

Run the whole committed corpus for every configuration, giving the suite full fidelity with the accuracy benchmark.

**Pros**:
- The full WER number is guarded, not just a sample.
- No separate subset constant to freeze and maintain.

**Cons**:
- Roughly 40 CPU transcriptions per full run (base plus small), minutes of wall time, which pushes developers to skip the suite.
- Duplicates the accuracy benchmark's whole job, blurring the "guard" and "measure" split.

### Option 3: A lightweight smoke suite, no recovered state assertions

Load and warm the real model, transcribe a couple of clips, assert the output is non empty, and skip the forced timeout and the degraded recovery proof.

**Pros**:
- Fastest end to end, lowest maintenance, least likely to flake.

**Cons**:
- Leaves the highest value behavior untested: the real degraded to ready recovery path the scope names explicitly.
- A non empty output guard is weak; the committed corpus gives a real bound for almost no extra cost.

### Option 4: Mock driven degraded recovery, real model for transcription only

Keep the degraded to ready tests on `MockInferenceEngine` (as `tests/unit/test_lifecycle.py` already does) and use the real model only for transcription.

**Pros**:
- No timing dependent test to tune; recovery coverage exists already with the mock.

**Cons**:
- Contradicts the scope's Done when, which asks for the degraded recovery path proven live.
- A real adapter timeout still has no coverage, so a regression there stays silent.

## Rationale

Option 1 is the right shape for this codebase. The suite exists to prove real model behavior, so it must run the real engine and lifecycle, not the mock; that is the entire point of the empty `backend/tests/model/` directory, and it is why Option 3 and Option 4 fall short. Reusing the committed corpus keeps the suite deterministic and gives its assertions a source of truth, which the accuracy run already proved reproducible within 0.5 WER points on a pinned lockfile (spec 0001). Each clip's assertion bound derives from that clip's own committed per sample row plus a 0.10 margin, so no bound is a hand typed guess and a regression that matters blows well past it, while fine drift of a few points remains the 20 clip benchmark's job, the clean split asserted in the design. The frozen 5 clip subset keeps the run quick while staying a genuine guard.

Marker gating is the fit that matches how the project already runs: `uv run pytest` must stay fast and offline, and `uv run pytest -m model` is the explicit, documented way to pay for real inference. The forced timeout recovery test is the one risky piece: it is timing dependent by construction. The design holds it honest by tuning the budget so a real CPU model observably cannot finish a long tiled window, and by making the test fail (not silently pass) if the model turns out to be too fast. That tradeoff is the price of the scope's live requirement, and it is confined to a single test where a tuned window or budget is the documented fix.

The GPU ledger answers the budget rule without inventing infrastructure: a small append only JSON file next to the other benchmark artifacts, summed and capped against an environment variable. CPU is the default and free, cuda is opt in and gated, which matches ADR 006's ephemeral, on demand GPU posture. The ledger is unit tested offline so the budget guard is provable on any machine, GPU or not.

The winning alternative was Option 3 for cost and Option 2 for fidelity; Option 1 sits between them and gets the real coverage the scope asked for at a price a developer will actually pay. Referenced content: spec 0001 (accuracy corpus and artifacts), `backend/app/inference/` (the engines and lifecycle under test), `backend/tests/unit/test_lifecycle.py` (mock recovery coverage that the live test complements).

## References

**Project sources**:
- `AGENTS.md` and `backend/AGENTS.md`, the test split and pipeline conventions
- spec 0001, the committed accuracy corpus and artifacts this suite reuses and traces to
- `backend/app/inference/engine.py`, `whisper.py`, `lifecycle.py`, the code under test
- `backend/tests/unit/test_lifecycle.py`, the existing mock based recovery coverage
- `backend/tests/benchmarks/benchmark_utils.py` and `evaluate_accuracy.py`, the reused manifest, audio, metadata, and scoring helpers
- ADR 006, the ephemeral GPU posture that justifies the spend ledger

**Practices & standards**:
- Integration test suites for real dependencies stay opt in behind a marker so default runs stay fast
- Assertion bounds trace to measured artifacts, never hand typed guesses
- Resource consuming test paths record and cap their consumption instead of trusting self control