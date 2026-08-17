# VocalFlux Benchmarking

**Status:** Draft v1  
**Scope:** Latency budget, model configuration matrix, benchmark methodology, accuracy evaluation

---

## 1. Latency Budget

### 1.1 Targets

| Metric               | Target (normal demo) | Notes                          |
| -------------------- | -------------------- | ------------------------------ |
| First result latency | ≤ 500 ms (G3: <1 s)  | Speech start → first event     |
| Inference latency    | ≤ 300 ms             | Single window on GPU           |
| End-to-end echo      | ≤ 700 ms             | User speech → text on screen   |
| RTF                  | < 1.0 (target < 0.2) | real-time factor, lower better |

### 1.2 Budget decomposition

```text
browser chunk interval      ~40 ms
network (RTT local)        ~5–20 ms
queue + pipeline upstream   ~5–20 ms
windowing accumulation      ~1000–1500 ms  ← dominant, tunable
vad gate                    ~0–30 ms
inference (GPU)             ~150–300 ms
serialize + network (down)  ~5–20 ms
----------------------------------------------------
first transcript horizon    ~1.3–1.8 s
```

First-result latency is bounded by the windowing accumulation horizon plus
inference; this is the primary lever for the G3 sub-second targeting decision.

### 1.3 Stage-Level Timing

The server records independent monotonic timestamps for every processed
audio frame/window:

```text
capture_started
network_received
queue_entered / queue_exited
vad_started / vad_finished
window_started / window_formed
inference_started / inference_finished
result_emitted
```

The browser supplies `capture_started` as an optional diagnostic timestamp.
Official latency measurements use server-side monotonic timestamps; the client
timestamp is never used for ordering or trusted latency arithmetic.

Derived stage durations are:

```text
network_receive  = network_received - capture_started
queueing         = queue_exited - queue_entered
vad              = vad_finished - vad_started
window_formation = window_formed - vad_finished
inference        = inference_finished - inference_started
result_delivery  = client-local socket delivery interval  # best effort
first_result     = first_result_emitted - speech_started
```

Each benchmark result must include p50, p95, and p99 for first-result,
inference, and available stage-level timings. Client delivery is reported as a
separate client-local measurement and is not arithmetically combined with
server monotonic timestamps. Missing stages are reported as missing rather
than silently folded into another stage.

### 1.4 What is measured

Measured on server monotonic clocks. Client-side measurement of "time to text"
is mirrored for reporting but is not the official metric.
See `architecture.md §5` for clock rules and timestamp ownership.

---

## 2. Model Configuration Matrix

### 2.1 Dimensions

| Dimension       | Candidate values                      |
| --------------- | ------------------------------------- |
| Model size      | tiny, base, small, medium             |
| Compute type    | float16, float32, int8                |
| Device          | cuda, cpu                             |
| Model (quant)   | standard vs int8 quantization         |
| Beam size       | 1–5                                   |
| Window size     | 500, 1000, 1500, 2000 ms              |
| Overlap         | 0, 150, 300, 500 ms                   |
| VAD threshold   | 0.3, 0.5, 0.7                          |
| Context strategy| None / overlap / transcript prompt / hybrid |

### 2.2 Matrix selection

| Config | Model    | Compute | Window | Overlap | VAD  | Context       | Use                     |
| ------ | -------- | ------- | ------ | ------- | ---- | -------------- | ----------------------- |
| dev-cpu| base     | float32 | 1500   | 300     | 0.5  | hybrid         | local CPU dev            |
| demo   | small    | float16 | 1500   | 300     | 0.5  | hybrid         | target demo config       |
| fast   | tiny      | float16 | 1000   | 200     | 0.5  | overlap        | latency experiment       |
| acc    | medium   | float16 | 2000   | 500     | 0.5  | hybrid         | accuracy experiment      |

Exact winning values are decided empirically in **Experiment set A/B** below.

### 2.3 Results Matrix

This table is the canonical comparison format for measured model
configurations. Placeholder values remain empty until the benchmark is run.

| Model  | Device | Compute | RTF  | WER  | VRAM |
| ------ | ------ | ------- | ---- | ---- | ---- |
| Tiny   | CPU    | int8    | ...  | ...  | ...  |
| Small  | GPU    | float16 | ...  | ...  | ...  |
| Medium | GPU    | float16 | ...  | ...  | ...  |

---

## 3. Performance Metrics

| Metric             | Formula                                     | Notes                          |
| ------------------ | ------------------------------------------- | ------------------------------ |
| First result latch | `first_transcript - speech_start`           | monotonic clocks               |
| Inference latency  | `end_monotonic - start_monotonic` (per call)| histogram p50/p95/p99          |
| RTF                | `inference_latency / window_audio_duration` | averaged over windows         |
| Throughput         | `audio_seconds_processed / wall_seconds`    | per stream and aggregate       |
| Jitter (network)   | packet inter-arrival spread (server side)   | diagnostic                     |
| Drop/reject rate   | `dropped / received frames`                 | backpressure observability     |

### 3.1 Latency reporting distribution

Report `p50`, `p95`, `p99` for: first-result latency, inference latency, and
end-to-end (client-observed, best-effort).

---

## 4. Benchmark Suite

### 4.1 Concurrency sweep

```text
streams:  1, 5, 10, 25, 50
```

For each concurrency level, feed identical audio sources into N parallel
sessions. Continue until a **saturation point** is identified (throughput
plateaus or latency grows non-linearly). This is the documented
`MAX_CONCURRENT_SESSIONS` justification.

### 4.2 Per-run measurements

```text
p50 / p95 / p99 latency
RTF
throughput (streams and audio-seconds)
GPU utilization (nvidia-smi / dcgm where available)
GPU memory used / total
CPU utilization
error rate
```

### 4.3 Compare

- Different configs from **Configuration Matrix**.
- GPU vs CPU device.
- Post-benchmark vs latency budget (§1).

---

## 5. Reproducible Methodology

> Requirement stated in PRD; this is the engineering spec.

### 5.1 Benchmark Environment

Every run records:

- Hardware: host OS, CPU model/count, RAM, GPU model, VRAM, driver, and CUDA runtime.
- Software versions: Git SHA, Python, backend dependencies, Docker image,
  CTranslate2, faster-whisper, and benchmark harness versions.
- Model configuration: model, device, compute type, language, beam size, VAD,
  window, overlap, and context strategy.

### 5.2 Baseline audio corpus

A fixed, versioned set of reference WAV clips (16 kHz mono) stored in
`backend/tests/fixtures/audio/` (see PRD §33 evaluation dataset). The same
clips are used for:

- Unit/integration fixture streams,
- Accuracy evaluation,
- Load/concurrency benchmarks.

This guarantees benchmark results are comparable across runs, machines, and
time.

### 5.3 Benchmark harness (`tests/benchmarks/`)

- Deterministic: fixed seeds, fixed corpus, fixed config file.
- VAD disabled for pure inference benchmarks where isolation is desired.
- Reuses the AsyncWebSocketClient (same as load test) unless a real WS client
  is needed.
- Writes structured JSON results to `benchmarks/results/<run-id>.json`.

### 5.4 Warmup and Run Protocol

1. Start the service with the selected immutable configuration.
2. Wait for `/ready` and record model load time.
3. Run at least one warmup inference per process/session configuration; exclude
   warmup from reported latency and accuracy statistics.
4. Run the fixed corpus at the selected concurrency level for a fixed duration
   or fixed number of audio samples.
5. Repeat each configuration for at least five independent measured runs.
6. Record all successful, dropped, timed-out, and failed samples.

Concurrency levels are `1, 5, 10, 25, 50` unless a documented capacity limit
requires a lower maximum.

### 5.5 Statistical Methodology

Report sample count, completed runs, dropped/error count, mean, median (p50),
p95, and p99. Percentiles are calculated over per-event observations, not over
run averages. A run is reproducible only when the corpus, configuration,
hardware/software metadata, warmup policy, and run count are all recorded.

### 5.6 Commands (offer)

```text
cd backend
uv run pytest tests/benchmarks -k "wer"           # accuracy
uv run pytest tests/benchmarks -k "latency"       # single-stream latency
uv run locust -f tests/benchmarks/locustfile.py   # concurrency sweep
```

### 5.7 Reporting

Every result record includes:

```text
run_id, date, git_sha, host_summary (os, cpu, gpu, driver), software_versions,
model, compute_type, device, window_ms, overlap_ms, vad_threshold,
context_strategy, streams, duration_s, warmup_count, run_count, metrics{...}
```

Results are documented in the Benchmark Report (see PRD Phase 11 / §47).

---

## 6. Accuracy Evaluation

### 6.1 Metrics

```text
WER = (S + D + I) / N     (substitutions + deletions + insertions) / ref words
CER = same at character level
```

Computed with the `jiwer` library. Case-insensitive, reference-punctuation
stripped normalization.

### 6.2 Dataset (PRD §33)

10–30 representative samples:

- different speakers
- different speaking speeds
- short and long utterances
- quiet speech
- background noise
- different accents where practical

Each sample has a ground-truth transcript in a manifest
(`backend/tests/fixtures/accuracy/manifest.json`).

### 6.3 Reporting table

| Config            | WER   | CER   | samples |
| ----------------- | ----- | ----- | ------- |
| demo (small/f16)  | 0.xx  | 0.xx  | 20      |
| acc (medium/f16)  | 0.xx  | 0.xx  | 20      |
| fast (tiny/f16)   | 0.xx  | 0.xx  | 20      |

---

## 7. Experiment Sets

### Set A — Window sweep (accuracy vs latency)

Vary `window_ms` over [500,1000,1500,2000]; fix model small, f16, overlap 300,
context hybrid. Plot accuracy vs first-result latency for each. This decides
the V1 window default.

### Set B — Context/overlap sweep

Vary context strategy (none/overlap/transcript/hybrid) and overlap duration.
Decides `adr/005-transcript-context.md` parameters.

### Set C — Compute type

Compare float16 vs int8 vs float32 on the same model; documents the
accuracy/throughput tradeoff.

### Set D — Model size

tiny/base/small/medium at the winning window config; documents the
latency/accuracy tradeoff curve (explicitly *not* "choose the biggest model").

### Set E — Concurrency saturation (from §4)

---

## 8. Success Gates

- Demo config meets latency budget (§1) on target GPU.
- Saturation point published and `MAX_CONCURRENT_SESSIONS` justified.
- WER/CER report produced for at least model sizes and compute types.
- All benchmark runs reproducible via documented commands.
