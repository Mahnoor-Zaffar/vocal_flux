# 0003. Reproducible benchmark report

**Date**: 2026-08-23
**Status**: In Progress

## Summary

The latency and concurrency benchmarks exist but they measure the Whisper engine directly, skipping everything that makes VocalFlux a streaming service. This spec reworks them to drive real sessions through the running app over WebSockets, so the published numbers cover VAD, windowing, queueing, and the session manager. The runs commit JSON artifacts plus generated markdown tables, the saturation point gets a crisp pass or fail rule, and a reviewer can rerun the documented commands on their own machine and land near the same numbers.

## Context

Scope row F says the bench scripts, dataset, and methodology exist while the live runs and documented results are missing. Slice 3 closes exactly that gap for latency and concurrency. The forces at play:

- `docs/benchmarking.md` already promises a specific methodology: sessions fed over WebSocket against a started service (`§5.3`, `§5.4`), percentiles over per event observations (`§5.5`), and a concurrency sweep whose result justifies `MAX_CONCURRENT_SESSIONS` (`§4.1`). The current scripts in `backend/tests/benchmarks/` do not honor that promise: they call `lifecycle.transcribe()` directly, which measures raw model speed and bypasses decode, VAD, windowing, the bounded queue, and the capacity gate. Numbers from those scripts cannot back the realtime claim the doc makes.
- The service caps concurrent sessions at 10 by default, while the documented ladder sweeps 1, 5, 10, 25, 50. The sweep must therefore raise the cap through the environment and let the measured curve inform the shipped default, rather than letting the default censor the measurement.
- This is a CPU first project with a paid GPU story deferred to slice 6. The headline committed numbers must come from this machine, on the service default configuration (small, int8, beam 1), in minutes not hours.
- Reproducibility is the point of the slice: fixed committed corpus, pinned protocol, recorded environment metadata, and tolerance guidance, mirroring how slice 1 landed accuracy numbers.

Not deciding this leaves the doc promising numbers no command can produce, and the demo hardening slice would tune against guesses instead of measurements.

## Requirements

**User stories**:

- As a reviewer, I want to run documented commands that produce the published latency and concurrency numbers, so I can trust the V1 realtime claim.
- As the engineer tuning the demo experience, I want measured window latencies and a named saturation point, so slice 4 tunes against evidence instead of guesses.

**Acceptance criteria** (the contract):

- **AC-1**: Documented commands run the latency benchmark and the concurrency benchmark end to end on this machine with the service default configuration (small, int8, beam 1, CPU) and no network access beyond cached model weights.
- **AC-2**: Both benchmarks drive real WebSocket sessions against the booted app, so decode, VAD, windowing, queue overflow behavior, and the session manager are inside the measured path.
- **AC-3**: Each official run writes a JSON artifact to `backend/benchmark-results/` carrying the environment envelope, raw per event samples, percentile summaries for window final latency, first partial latency, and RTF, throughput, dropped frame counts, error counts, and (for concurrency) per session rollups; a markdown fragment renders beside it. Failures split into two classes: fatal breaks (connection lost, protocol violation, service crash) abort the run with a nonzero exit and leave previously committed artifacts untouched, while measured degradations (inference timeouts, dropped frames) are recorded in the artifact as data because they are exactly what high load produces.
- **AC-4**: The concurrency sweep covers levels 1, 5, 10, 25, 50 with `MAX_CONCURRENT_SESSIONS` raised above 50 through the harness booted environment, feeds only the frozen five clip subset shared with spec 0002, discards 2 warmup sessions per level, and takes 3 measured repeats per level.
- **AC-5**: Each concurrency artifact names the saturation point with an explicit gate: the highest level where p95 window final latency stays within twice the window audio duration AND the dropped frame rate stays below 1 percent, plus the suggested shipped `MAX_CONCURRENT_SESSIONS` derived from that level.
- **AC-6**: `docs/benchmarking.md` gains a new `## 9. Recorded performance results` section carrying the headline tables for small int8 beam 1 on CPU with a pointer to the committed artifacts, reproduction commands matching `§5.6`, tolerance bands (about 15 percent on the same hardware, about 25 percent across different hardware), and `§5.4` is amended to the pinned protocol (2 warmup sessions discarded, 3 measured repeats).

## Options considered

### Option 1: Session level harness driving the running service

Rework both scripts onto a shared harness module that boots uvicorn on a scratch port with environment overrides, polls `/ready`, connects N async WebSocket clients using the `websockets` library, streams PCM16 frames at real time pace, and records every transcript and metrics message.

**Pros**:
- Measures the actual service path including queue drops and the capacity gate, so the doc's promises and the numbers finally agree.
- Produces first partial and window final latencies the frontend really experiences, reused by slice 4.
- Matches `§5.3` through `§5.5` as written.

**Cons**:
- Most moving parts: process management, port picking, client bookkeeping.
- Real time pacing means a sweep takes minutes, and localhost timings vary more across machines than direct engine calls.

### Option 2: Keep the direct engine path and amend the doc

Leave `benchmark_latency.py` and `benchmark_concurrency.py` measuring `lifecycle.transcribe()`, and rewrite `docs/benchmarking.md` to admit it measures the engine alone.

**Pros**:
- Smallest change; scripts already work and run fast.
- Lower variance, easier reproduction.

**Cons**:
- The numbers say nothing about VAD, windowing, queueing, or session limits, which is where the realtime risk actually lives.
- The saturation point becomes fiction: concurrent `transcribe()` calls never exercise the session manager that would reject them.
- Retracts a documented commitment instead of fulfilling it.

### Option 3: Hybrid, engine baseline plus session sweep

Keep the direct path as a model baseline artifact and add the session harness for the concurrency claim.

**Pros**:
- Preserves cheap model to model comparisons.

**Cons**:
- Double the surface to maintain for information the model test suite already provides; the baseline adds no claim the service needs defended.

## Decision

**Chosen option**: Option 1: Session level harness driving the running service.

Both scripts are reworked onto one shared harness; the doc's existing methodology stands and finally gets honored end to end. The `websockets` library joins as a direct dev dependency for the clients; CPU pressure is recorded with `os.getloadavg()` and `cpu_count` from the standard library, keeping `psutil` out.

## Rationale

The doc already commits to sessions against a started service; option 2 would rewrite the commitment to match the tooling, which is backwards when the tooling is two hundred lines of dev script. The realtime claim this project defends lives in the streaming path, so the measurement must include it; an engine only number would be honest about the wrong thing. Option 3 pays double maintenance for a baseline that the accuracy artifacts and model tests already cover. Real time pacing costs minutes per sweep and buys numbers with the same semantics the browser produces, which is what slice 4 will tune against. Three measured repeats instead of the documented five trades a little statistical comfort for a sweep that actually gets run on CPU; the doc is amended so method and practice stay the same thing.

## Feature design

**Data model sketch** (JSON artifacts, stable filenames, overwrite in place on official runs):

Common envelope (both files): existing `run_metadata()` fields (`run_id`, `timestamp`, `git_sha`, `python`, `platform`, `machine`, `processor`) plus `benchmark`, `corpus.sample_ids` (the frozen five ids from spec 0002), `configuration` (model, device, compute type, beam size, language), `service_env` (`max_concurrent_sessions` the harness booted with, window seconds), `warmup_sessions: 2`, `repeats: 3`.

`latency-small.json`:
- `events[]`: one row per observation with `repeat`, `clip_id`, `event_type` (`first_partial` or `window_final`), `window_index`, `audio_seconds`, `latency_seconds`
- `summary.window_final`, `summary.first_partial`, `summary.rtf`: count, mean, p50, p95, p99 via the existing `percentile_summary`

`concurrency-small.json`:
- `levels[]`: `streams`, `wall_seconds`, `audio_seconds_total`, `throughput_audio_seconds`, `dropped_frames`, `drop_rate`, `errors`, `timeouts`, percentile blocks for `window_final`, `first_partial`, `rtf`, `loadavg_before_after`, `sessions[]` rollups (session id, clips fed, windows completed, drops, own p50 and p95)
- `saturation`: gate definition, pass boolean per level, `saturation_level`, `suggested_max_concurrent_sessions` (equal to the named saturation level; the shipped default is a human call made with margin)

Raw samples stay inside the artifacts so reviewers can recompute percentiles; files stay well under a megabyte.

**State transitions** (one run): boot service → poll `/ready` → warmup sessions (discarded) → measured repeats per level or clip → write artifact and fragment atomically → shut service down. A level counts as finished when every session has fed all of its frames AND every session has either received all expected finals or hit its per session timeout; only then are the level's statistics closed. Fatal breaks (connection lost, protocol violation, service crash) short circuit to teardown with a nonzero exit and no write; measured degradations (timeouts, drops) stay in the data and never abort.

**API surface** (CLI, no HTTP endpoints added):

| Command | Key inputs | Key outputs | Key errors |
|---|---|---|---|
| `uv run python -m tests.benchmarks.benchmark_latency` | `--model small --device cpu --compute-type int8 --beam-size 1 --warmup-sessions 2 --repeats 3 --output PATH` | `benchmark-results/latency-small.json` + `.md` fragment | nonzero exit on session failure or missing corpus clip |
| `uv run python -m tests.benchmarks.benchmark_concurrency` | previous flags plus `--levels 1,5,10,25,50` | `benchmark-results/concurrency-small.json` + `.md` fragment | same |

The positional `audio` argument disappears; the corpus is fixed inside the harness so runs cannot drift.

**Value sourcing**:

| Action | Value produced | Source |
|---|---|---|
| Boot | readiness confirmation, model load time | polling `GET /ready` until it responds ready |
| Window final latency | send to emit delay per window | ordering rule: the Nth final message received in a session maps to the Nth window whose frames were fully fed; client timestamps both ends |
| First partial latency | time to first text | client timestamp: session start → first partial message received; a session that produces no partial records none, never an error |
| RTF | realtime factor | latency divided by the window's audio seconds |
| Dropped frames | drop rate per level | sequence number gaps detected in received session messages (wire protocol metadata) |
| Throughput | audio seconds per second | total audio fed divided by wall time |
| Saturation level | gate verdict | computed over `levels[]` from the pinned thresholds |
| CPU pressure | load average context | `os.getloadavg()` sampled before and after each level |
| Environment envelope | provenance fields | existing `benchmark_utils.run_metadata()` |

**Key invariants**:

- Official artifacts are written only after a fully clean run; writes are atomic (temp file then rename) so a crash never truncates a committed artifact.
- Warmup observations never enter reported statistics; percentiles are computed over per event samples, never run averages (`§5.5`).
- The five corpus ids are byte identical to the spec 0002 frozen subset and rebuildable with `rebuild_accuracy_corpus.py`.
- The shipped application default `max_concurrent_sessions` stays 10 unless the measured curve justifies changing it in the doc; only the harness environment raises it.
- Timeout and drop observations are data, never abort causes; only fatal breaks (connection loss, protocol violation, service crash) end a run early.
- `os.getloadavg()` is wrapped so a platform without it records null instead of failing the run.

**Security model**: none touched. Scripts run locally, add no endpoints, hold no secrets, and transcribe public domain LibriSpeech audio already committed to the repo.

**Configuration required**:

- Harness sets `MAX_CONCURRENT_SESSIONS` (and reads the window size from settings) in the booted service environment only; no new persistent env vars, no credentials.
- Scratch port is picked ephemerally per run to avoid collisions.

**Critical test scenarios** (offline, no model needed in the default suite):

- Happy path: a scripted fake service (or recorded message flow) drives the harness end to end and produces both artifact shapes with correct percentile math, verifies **AC-3**
- Failure case: a client sees a session error mid sweep; the run exits nonzero and the preexisting artifact bytes are unchanged, verifies **AC-3**
- Gate logic: synthetic level tables classify saturation correctly at the boundary values (exactly 2x window audio, exactly 1 percent drops), verifies **AC-5**
- Drop accounting: injected sequence gaps produce exact dropped frame counts and rates, verifies **AC-3**, **AC-5**

## Build plan

Tracer Bullet ordering: stand up the thinnest real thread first (one session through the live service producing one honest number), then thicken to the full protocol, then the doc layer.

1. Shared session harness module in `tests/benchmarks/`: subprocess uvicorn on an ephemeral port with env overrides, `/ready` polling, N async `websockets` clients feeding PCM16 at real time pace, message collection, sequence gap drop detection, clean teardown, satisfies **AC-2**
2. Rework `benchmark_latency.py` onto the harness: sequential repeats over the frozen five clips, first partial and window final events, RTF, atomic artifact plus markdown fragment writer, satisfies **AC-1**, **AC-3**
3. Rework `benchmark_concurrency.py`: level sweep under the raised env cap, warmup discard, per session rollups, load average capture, abort on failure policy, satisfies **AC-4**, **AC-3**
4. Saturation gate evaluation with boundary covered by offline unit tests in the default suite, satisfies **AC-5**
5. Run both benchmarks officially on this machine, commit artifacts and fragments, satisfies **AC-1**, **AC-4**
6. Update `docs/benchmarking.md`: new recorded results section with pasted fragments and artifact pointers, `§5.4` amended to the pinned protocol, `§5.6` commands refreshed, tolerance bands stated, satisfies **AC-6**

## Consequences

**Positive**:
- The published numbers measure the real service path, so the V1 realtime claim and the doc finally describe the same system.
- Slice 4 inherits first partial distributions and a named saturation point for free.
- Reviewers get one command per table, committed artifacts, and explicit tolerance bands.

**Negative / tradeoffs**:
- Sweeps take minutes of real time pacing instead of seconds of dump and go.
- Localhost timings vary across reviewer machines more than engine only numbers would; tolerance bands absorb this honestly.
- Process orchestration (port, readiness, teardown) adds failure modes the old scripts never had.
- Raw sample artifacts are larger commits than aggregate only files.
- Statistics rest on 3 repeats per level, weaker than the originally documented 5.

**Neutral**:
- `websockets` becomes a direct dev dependency (it likely already sits in the lockfile through uvicorn).
- The scripts lose their positional audio argument; `§5.6` commands change accordingly.
- Doc gains `## 9. Recorded performance results`, and `§8` success gates gain pointers to it.

## Follow-up

- [ ] Wire the GPU spend ledger (`tests/model/gpu_spend.py`) into benchmark runs when device work lands in slice 6, so cuda benchmark passes respect the budget.
- [ ] Next `/sync` run should record the declined skill and MCP discovery for `websockets` so it is not offered again.
