# VocalFlux Project Context

This file is the implementation reference for future work on VocalFlux. Read it
before making project changes.

## Project Identity

VocalFlux is a Python-first, real-time speech-to-text inference system. It is a
portfolio and systems-engineering project, not a general voice assistant.

The main engineering goal is to turn Whisper's window-based inference into a
reliable, low-latency, observable streaming service.

The backend is the primary project. The frontend must remain deliberately thin.

## Canonical Architecture

```text
Browser
  Next.js + React + TypeScript
  Web Audio API + AudioWorklet
        ↓
Binary WebSocket audio
        ↓
FastAPI WebSocket Gateway
        ↓
Session Manager
        ↓
Bounded per-session asyncio queue
        ↓
Audio Pipeline
  validation → decode → normalize → VAD → buffer → window
        ↓
Context Manager
        ↓
Bounded Inference Scheduler
        ↓
InferenceEngine
  faster-whisper → CTranslate2 → CPU/GPU
        ↓
Transcript State
  unstable/partial → committed/final
        ↓
WebSocket result events
        ↓
Browser UI
```

## Canonical Stack

### Backend

- Python 3.13
- FastAPI
- Uvicorn
- asyncio
- Pydantic and pydantic-settings
- faster-whisper and CTranslate2
- NumPy and PyAV
- Silero VAD
- Prometheus client
- structlog

### Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS
- Web Audio API
- AudioWorklet
- WebSocket API

### Testing and Infrastructure

- pytest
- pytest-asyncio
- httpx
- Locust
- Docker and Docker Compose
- OrbStack for local macOS development
- RunPod for ephemeral GPU demos
- GitHub Actions

Redis, Celery, Kubernetes, and distributed GPU workers are not V1
dependencies. They may be introduced only after benchmarks prove the
single-process architecture is insufficient.

## Audio Contract

The internal audio representation is predictable and normalized:

```text
Transport:   binary WebSocket frames
Encoding:    PCM16 signed little-endian
Sample rate: 16,000 Hz
Channels:    1 / mono
Internal:    float32 PCM
```

The browser captures audio with AudioWorklet and sends binary payloads rather
than base64 JSON.

## WebSocket Contract

Canonical endpoint:

```text
WS /ws/v1/transcribe
```

Each logical audio frame is associated with:

```text
session_id
stream_id
sequence_number
```

The protocol must handle:

- Duplicate sequence: ignore without reprocessing.
- Old sequence: reject or ignore according to policy.
- Missing sequence: detect and expose as an observable condition.
- Invalid sequence: return a structured protocol error.
- Transcript events: preserve logical ordering and distinguish unstable from
  committed text.

See `docs/protocol.md` for the exact wire contract.

## Non-Negotiable Backend Requirements

- Every WebSocket connection owns an isolated `TranscriptionSession`.
- Session-owned receiver, processor, inference, and sender tasks must be
  cancelled together during termination.
- Audio queues and buffers must be bounded.
- Backpressure policy must be explicit and observable.
- Network and session handling must not block the FastAPI event loop.
- GPU-bound inference must run behind a bounded scheduler.
- `InferenceEngine` must isolate the application from faster-whisper.
- Model lifecycle must distinguish process liveness from inference readiness.
- Failures must not crash the service or leak session resources.
- Audio and transcripts are ephemeral in V1; do not add persistence.

## Required Limits and Configuration

Configuration belongs in environment-backed settings, not scattered constants.

```text
WHISPER_MODEL
WHISPER_DEVICE
WHISPER_COMPUTE_TYPE
WHISPER_LANGUAGE
WHISPER_BEAM_SIZE
AUDIO_SAMPLE_RATE
AUDIO_CHANNELS
VAD_THRESHOLD
WINDOW_SIZE_MS
OVERLAP_MS
MAX_MESSAGE_SIZE
MAX_SESSION_DURATION
MAX_AUDIO_BUFFER
MAX_QUEUE_SIZE
MAX_CONCURRENT_SESSIONS
MAX_CONCURRENT_INFERENCES
INFERENCE_TIMEOUT
QUEUE_OVERFLOW_POLICY
```

## Observability Requirements

Use structured logs and Prometheus metrics. Correlate events with session and
sequence identity where applicable.

Stage-level timing must be independently measurable for:

```text
audio capture
network receive
queueing
VAD
window formation
inference
result delivery
```

Server-side latency calculations use a monotonic clock. The first-result
latency target is less than one second under normal demo conditions.

## Evaluation Requirements

Benchmarks must provide reproducible measurements for:

- p50, p95, and p99 latency
- First-result latency
- Real-time factor
- WER and CER
- GPU utilization
- GPU memory
- Concurrent sessions

Every benchmark run records hardware, software versions, model configuration,
audio dataset, warmup procedure, concurrency, number of runs, and statistical
methodology.

## V1 Boundaries

Do not add these without an explicit requirement and updated documentation:

- User accounts or authentication
- Billing or subscriptions
- Persistent audio/transcript storage
- Conversational agents, RAG, or text generation
- Mobile applications
- Kubernetes or service mesh
- Multi-region deployment
- Distributed inference
- Redis/Celery worker pools

## Repository Documentation

- `PRD.md` — product and system requirements; defines what must be true.
- `README.md` — project introduction and usage overview.
- `docs/architecture.md` — how components, clocks, concurrency, and cancellation work.
- `docs/protocol.md` — what client and server agree on over WebSocket.
- `docs/benchmarking.md` — how performance and accuracy are measured.
- `docs/threat-model.md` — security and abuse analysis.
- `docs/adr/` — why important architectural decisions were made.

When requirements conflict, prefer the latest explicit user instruction, then
`PRD.md`, then the detailed engineering documents. Update the documents when a
canonical decision changes; do not silently introduce a competing architecture.

## Implementation Sequence

1. Inference engine and model lifecycle.
2. Audio decoding, normalization, VAD, buffering, and windowing.
3. WebSocket gateway, sessions, queues, and backpressure.
4. Transcript state, context, ordering, and protocol events.
5. Thin frontend with AudioWorklet and live transcript rendering.
6. Limits, cancellation, errors, logging, and metrics.
7. Unit, integration, model, accuracy, latency, and load tests.
8. Docker Compose local deployment and ephemeral GPU deployment.

Do not optimize or distribute the system before collecting benchmark evidence.
