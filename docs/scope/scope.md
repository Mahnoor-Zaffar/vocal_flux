# Scope: VocalFlux

A realtime speech to text system: the browser streams microbi audio over a WebSocket, the backend transcribes with faster-whisper, and incremental transcript and metrics render live. The V1 boundary is nearly built; this scope plans the slice that finishes it and proves its claims.

**Build approach:** Tracer Bullet (vertical slices, each feature built end to end and working before the next starts).
**Workflow:** Beta (after /develop runs /check verify then /test; /architect is the first stop for a feature with a real decision, skippable when you already know the build). Any feature can carry its own tag (e.g. `· GA`) to do more or less.

_These are recommendations to keep your build orderly, not requirements. Skip anything that does not fit: if you already know how to build a feature, use /develop and skip /architect. You decide when a feature is `done`._

## At a glance

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| A | Streaming backend core | Existing | existing |
| B | Frontend capture and UI | Existing | existing |
| C | Inference engine and lifecycle | Existing | existing |
| D | Observability and reliability | Existing | existing |
| E | Architecture docs and ADRs | Existing | existing |
| F | Evaluation and benchmark scaffolding | Existing | in-progress |
| 1 | Accuracy evaluation (WER/CER) | Slice 1 | done |
| 2 | Model tests | Slice 2 | in-progress |
| 3 | Reproducible benchmark report | Slice 3 | planned |
| 4 | Demo hardening | Slice 4 | planned |
| 5 | Container run validation | Slice 5 | planned |
| 6 | RunPod GPU demo | Slice 6 | planned |

## Existing (for context)

### A. Streaming backend core · existing
WebSocket gateway, session lifecycle, bounded asyncio queue, audio validation, VAD, buffering, windowing, and transcript state. This is the engine room of the product. code in `backend/app/streaming/`, `backend/app/audio/`, `backend/app/transcript/`, `backend/app/api/websocket.py`

### B. Frontend capture and UI · existing
AudioWorklet microphone capture, PCM16 encoding, the WebSocket client, and the minimal recorder, transcript, metrics, and status UI. The frontend stays thin by design. code in `frontend/`

### C. Inference engine and lifecycle · existing
The faster-whisper adapter behind an engine abstraction, plus model readiness, scaled timeouts, and recoverable degraded state. code in `backend/app/inference/`

### D. Observability and reliability · existing
Structured logs, Prometheus metrics, health and ready endpoints, rate limiting, origin policy, and session resource limits. code in `backend/app/core/`, `backend/app/api/`

### E. Architecture docs and ADRs · existing
The docs that ground every decision: architecture, protocol, threat model, benchmarking, and six ADRs. code in `docs/`

### F. Evaluation and benchmark scaffolding · in-progress
Latency, concurrency, and accuracy scripts exist in tests/benchmarks and methodology lives in docs/benchmarking.md, but the dataset, live runs, and documented results are missing. code in `backend/tests/benchmarks/`, `docs/benchmarking.md`

## Slice 1: Accuracy evaluation

### 1. Accuracy evaluation (WER/CER) · done

A small controlled dataset with ground truth plus a working Word Error Rate and Character Error Rate run, so V1 has a defensible accuracy number, which is a stated V1 goal.
**Done when:** a 10 to 30 sample dataset with ground truth exists, `evaluate_accuracy` records WER/CER against it, and docs/benchmarking.md carries the results.
**Spec:** [0001](../specs/0001-accuracy-evaluation/index.md) [verify](../specs/0001-accuracy-evaluation/verify.md)
**Code:** `backend/tests/benchmarks/evaluate_accuracy.py`, `backend/scripts/rebuild_accuracy_corpus.py`, `backend/tests/fixtures/accuracy/`, `backend/benchmark-results/`
- [x] Design it (spec): `/architect accuracy evaluation`
- [x] Build it: `/develop accuracy evaluation`
  - [x] Scoring normalization, corpus tool, and tests, satisfies AC-1, AC-2, AC-6
  - [x] Materialize and commit the 20 clip corpus and manifest, satisfies AC-1, AC-6
  - [x] Run tiny, base, and small on CPU int8 and commit the JSON artifacts, satisfies AC-2, AC-3
  - [x] Reconcile benchmarking doc paths and the §6.3 table, satisfies AC-4, AC-6
  - [x] Reproduce from a clean checkout within tolerance, satisfies AC-5
- [x] Verify it: `/check verify accuracy evaluation`
- [x] Test it: `/test accuracy evaluation`

## Slice 2: Model tests

### 2. Model tests · in-progress
Fill the empty tests/model directory with tests that run against the real Whisper model, so behavior on a real model is guarded and the degraded recovery path is proven live.
**Done when:** a model test suite runs against the real model, passes on CPU for base and small, and records its GPU spend so the limited GPU budget stays respected.
**Spec:** [0002](../specs/0002-model-tests/index.md) [verify](../specs/0002-model-tests/verify.md)
- [x] Design it (spec): `/architect model tests`
- [ ] Build it: `/develop model tests`
  - [ ] Marker gating and lazy session fixtures, satisfies AC-1
  - [ ] Frozen subset transcription tests with committed ceilings, satisfies AC-1, AC-2
  - [ ] Live degraded recovery test with a forced real timeout, satisfies AC-3
  - [ ] GPU spend ledger with upfront cap plus offline unit tests, satisfies AC-4, AC-5
  - [ ] Document commands and confirm the bounds on CPU from a clean checkout, satisfies AC-6
- [ ] Verify it: `/check verify model tests`
- [ ] Test it: `/test model tests`

## Slice 3: Reproducible benchmark report

### 3. Reproducible benchmark report · needs a decision
Run the latency and concurrency benchmarks and document p50, p95, p99 latency, realtime factor, and the saturation point, so a reviewer can reproduce the numbers.
**Done when:** the benchmark scripts run from documented commands, the results live in docs/benchmarking.md, and a reviewer can rerun them and land near the same numbers.
- [ ] Design it (spec): `/architect reproducible benchmark report`

## Slice 4: Demo hardening

### 4. Demo hardening · needs a decision
Use the benchmark numbers to tune the live experience: first result latency, window size, VAD settings, and the CPU versus GPU feel, without breaking the bounded pipeline guarantees.
**Done when:** the demo shows sub second first result latency on CPU for tuned windows, and the tuning choices are recorded against the measured numbers, not guesses.
- [ ] Design it (spec): `/architect demo hardening`

## Slice 5: Container run validation

### 5. Container run validation · needs a decision
Prove the definition of done: `docker compose up` boots the app locally and the browser flow works, so the compose path is the real entry point a reviewer uses.
**Done when:** `docker compose up` brings up backend and frontend, the browser records and transcribes, and the CPU image builds with the health checks wired.
- [ ] Design it (spec): `/architect container run validation`

## Slice 6: RunPod GPU demo

### 6. RunPod GPU demo · needs a decision
Deploy the ephemeral GPU demo from the existing RunPod scaffolding and the published GPU image, the V1 goal that needs a real GPU only for the demo.
**Done when:** the GPU image publishes from CI, the RunPod pod boots the app and passes ready checks, and the browser flow transcribes over the network.
- [ ] Design it (spec): `/architect RunPod GPU demo`

## Deferred

Out of scope for this pass, kept so the plan stays honest.

- **Persistent transcripts**: store and re open past sessions · needs a decision
- **WebRTC transport**: alternate to the binary WebSocket path · needs a decision
- **Speaker diarization**: separate speakers in a transcript · needs a decision
- **Language detection**: auto detect the spoken language · needs a decision
- **LLM post processing**: rewrite or summarize transcript text · needs a decision
- **Distributed inference**: a worker pool behind a queue, only after a measured bottleneck · needs a decision
- **Pipeline accuracy run**: score VAD, windowing, and partial assembly on the same corpus, from spec 0001 · needs a decision

## Legend

**The decision box.** Every feature carries exactly one box whose label ends with `(spec)`. Its wording varies (`Design it (spec)` normally, `Decide the stack (spec)` on foundations), so skills locate it by that `(spec)` suffix, never by an exact label. Every other box is an execution box and /architect never ticks one.

**Feature lifecycle** (the scope updates as a feature moves; each row is what it shows and who sets it):

| State | Set by | The feature shows |
|---|---|---|
| `planned` · needs a decision | /scope | one box: `Design it (spec): /architect <feature>` |
| `in-progress` (designed) | /architect at spec capture | this box ticked, a spec link, `/develop <feature>` with 2 to 5 milestones, and the tier boxes (verify, test) |
| `in-progress` (building) | /develop | milestone boxes tick one by one, a code pointer |
| `done` | you, when you decide it is; /sync reconciles | boxes you ran ticked, skipped ones marked skipped |
| `existing` | /scope | pre-workflow rows, no task list; /develop and /sync leave them alone |

- **Next step** = the first unticked box, always a command or a tracked milestone.
- **needs a decision** = run `/architect` first; otherwise straight to `/develop`. The tag drops once the spec is captured.
- **Workflow tier** beside a heading (`· GA`) overrides the Beta default for that one feature; no tag inherits the default.
- **Beta** default = `/check verify` then `/test` after /develop; GA would add a fresh model `/check review` then `/document`.