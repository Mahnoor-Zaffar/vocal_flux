# VocalFlux

VocalFlux is a Python-first, real-time speech-to-text inference system built
around Whisper. It captures microphone audio in the browser, streams binary
PCM audio over a persistent WebSocket connection, processes each session
through a bounded asynchronous audio pipeline, runs faster-whisper inference,
and returns incremental transcript events to the browser.

The backend is the primary engineering artifact. The frontend is deliberately
thin and exists to capture audio, communicate with the API, render transcript
state, and display performance metrics.

## Architecture

```text
Browser
  Next.js + React + TypeScript
  Web Audio API + AudioWorklet
        │
        │ Binary PCM16 / 16 kHz / Mono WebSocket frames
        ▼
FastAPI WebSocket Gateway
        ▼
Session Manager
        ▼
Bounded asyncio Queue
        ▼
Audio Pipeline
  Validation → Decode → Normalize → VAD → Buffer → Window
        ▼
Inference Engine
  faster-whisper → CTranslate2 → CPU/GPU
        ▼
Transcript State
  Partial / Unstable → Committed / Final
        ▼
Browser UI
```

VocalFlux is designed around a single in-process inference worker for V1.
Queues, buffers, sessions, and inference concurrency are bounded. Redis and
distributed GPU workers are deferred until benchmarks demonstrate that the
single-process architecture has reached its limit.

## Core Requirements

- Real-time browser microphone transcription.
- Binary WebSocket audio streaming.
- PCM16, 16 kHz, mono audio support.
- Per-session state isolation and cancellation.
- Silero VAD, buffering, and configurable windowing.
- Bounded queues and explicit backpressure.
- Replaceable inference engine abstraction.
- Partial, unstable, and committed transcript state.
- Monotonic, stage-level latency measurements.
- Prometheus metrics and structured logging.
- WER/CER accuracy evaluation and reproducible benchmarks.
- Docker-based local deployment and ephemeral GPU demos.

## Technology Stack

### Backend

- Python 3.13
- FastAPI and Uvicorn
- asyncio
- Pydantic and pydantic-settings
- faster-whisper and CTranslate2
- NumPy, PyAV, and Silero VAD
- Prometheus client and structlog

### Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS
- Web Audio API and AudioWorklet
- WebSocket API

### Testing and Infrastructure

- pytest and pytest-asyncio
- httpx
- Locust
- Docker and Docker Compose
- OrbStack for local macOS development
- RunPod for ephemeral GPU demonstrations
- GitHub Actions for image/build automation

## API Surface

```text
GET /health
GET /ready
GET /metrics
WS  /ws/v1/transcribe
```

The WebSocket protocol uses text JSON messages for control and metadata, and
binary frames for audio payloads. Each audio frame is associated with a
`session_id`, `stream_id`, and `sequence_number`. Duplicate frames are
ignored, stale frames are rejected or ignored according to policy, missing
sequences are detected, and invalid sequences produce structured errors.

## Project Structure

```text
vocal_flux/
├── PRD.md
├── README.md
├── docs/
│   ├── architecture.md
│   ├── protocol.md
│   ├── benchmarking.md
│   ├── threat-model.md
│   └── adr/
│       ├── 001-websocket-over-webrtc.md
│       ├── 002-faster-whisper.md
│       ├── 003-in-process-inference.md
│       ├── 004-inference-scheduling.md
│       ├── 005-transcript-context.md
│       └── 006-ephemeral-gpu.md
├── backend/
├── frontend/
└── docker-compose.yml
```

## Configuration

Runtime configuration is supplied through environment variables rather than
being scattered through application code.

```text
WHISPER_MODEL=small
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16

AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1

VAD_THRESHOLD=0.5
WINDOW_SIZE_MS=1000
OVERLAP_MS=300

MAX_SESSION_DURATION=3600
MAX_CONCURRENT_SESSIONS=10
MAX_CONCURRENT_INFERENCES=1
MAX_QUEUE_SIZE=10
INFERENCE_TIMEOUT=10
```

Exact values are selected through benchmark results.

## Local Development

The target local workflow is:

```text
OrbStack → Docker → VocalFlux
```

The local container startup command is:

```bash
docker compose up
```

For CUDA/float16 demo environments, use the GPU override documented in
[`infrastructure/docker/README.md`](infrastructure/docker/README.md).

The service is ready only after the inference model has loaded and completed
its warm-up. `/health` reports process liveness; `/ready` reports inference
readiness.

## Performance and Evaluation

The primary latency target is first-result transcription in less than one
second under normal demo conditions. The system measures:

- Audio capture
- Network receive
- Queueing
- VAD
- Window formation
- Inference
- Result delivery
- p50, p95, and p99 latency
- Real-time factor (RTF)
- GPU utilization and memory
- Concurrent session capacity
- WER and CER

Benchmark runs must record hardware, software versions, model configuration,
audio dataset, warm-up procedure, concurrency, number of runs, and statistical
methodology.

## Engineering Principles

1. Treat audio as a continuous stream.
2. Bound queues, buffers, sessions, inference, and resource consumption.
3. Separate transport, session, audio, transcript, and inference concerns.
4. Measure before optimizing.
5. Keep GPU work explicitly controlled.
6. Design for disconnects, malformed input, timeouts, and GPU failures.
7. Keep inference replaceable.
8. Add distributed infrastructure only when measurements justify it.
9. Document important architectural decisions.

## Documentation

- [`PRD.md`](PRD.md) — product and system requirements.
- [`docs/architecture.md`](docs/architecture.md) — components, timestamps,
  concurrency, and cancellation.
- [`docs/protocol.md`](docs/protocol.md) — WebSocket messages, ordering, and
  duplicate handling.
- [`docs/benchmarking.md`](docs/benchmarking.md) — latency budgets, model
  matrix, accuracy, and reproducible methodology.
- [`docs/threat-model.md`](docs/threat-model.md) — security and abuse controls.
- [`docs/adr/`](docs/adr/) — architecture decision records and tradeoffs.

## Scope

V1 intentionally excludes authentication, accounts, billing, persistent audio
storage, conversational agents, RAG, mobile applications, Kubernetes,
multi-region deployment, and distributed inference. These may be considered
only after the core streaming system has measurable performance and accuracy
characteristics.
