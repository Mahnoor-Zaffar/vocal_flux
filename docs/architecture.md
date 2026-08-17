# VocalFlux Architecture

**Status:** Draft v1  
**Scope:** System architecture, data flow, session lifecycle, clock model, cancellation semantics

---

## 1. Overview

VocalFlux is a real-time speech-to-text inference system. Audio is captured in the
browser, streamed over a persistent WebSocket as binary PCM16 frames, processed
through a bounded asynchronous pipeline, transcribed by faster-whisper on GPU, and
streamed back as incremental transcript events.

The system is deliberately a single-process, single-GPU service. Distributed
infrastructure is out of scope for V1 and reserved for a measured bottleneck (see
`adr/003-in-process-inference.md`).

```text
Browser (AudioWorklet → PCM16/16kHz/Mono)
    │  Binary WebSocket frames
    ▼
FastAPI WebSocket Gateway
    ▼
Session Manager (TranscriptionSession)
    ▼
Bounded Audio Queue (asyncio.Queue, maxsize=N)
    ▼
Audio Pipeline
    ├── Validation
    ├── Decoder
    ├── Normalization
    ├── VAD
    ├── Buffering
    └── Windowing
    ▼
Context Manager
    ▼
Inference Engine (faster-whisper / CTranslate2)
    ▼
Transcript State Manager (partial / committed)
    ▼
WebSocket Result Stream → Browser UI
```

---

## 2. Component Responsibilities

### 2.1 WebSocket Gateway (`app/api/websocket.py`)

- Accepts `/ws/v1/transcribe` connections.
- Reads binary audio frames and text control messages.
- Validates message size, framing, and protocol version.
- Delegates to the Session Manager.
- Owns no audio or inference logic.

### 2.2 Session Manager (`app/streaming/manager.py`)

- Creates and destroys `TranscriptionSession` objects.
- Enforces `MAX_CONCURRENT_SESSIONS`.
- Maps `session_id` → session.
- Cleans up on disconnect (see §6 Cancellation).

### 2.3 TranscriptionSession (`app/streaming/session.py`)

- Owns all per-connection mutable state:
  `session_id`, `created_at`, `state`, `sequence_number`, `audio_buffer`,
  `audio_queue`, `transcript_state`, `context`, `metrics`.
- Sessions never share mutable audio state.

### 2.4 Audio Pipeline (`app/audio/*`, `app/streaming/pipeline.py`)

Stages (defense in depth ordering):

1. **Validation** — reject malformed frames before any processing.
2. **Decoder** — raw PCM16 LE bytes → `numpy` float samples.
3. **Normalization** — scale to `[-1, 1]`.
4. **VAD** — Silero VAD; silence suppresses inference.
5. **Buffering** — bounded accumulation (`MAX_BUFFER_DURATION`, `MAX_BUFFER_BYTES`).
6. **Windowing** — slices buffered audio into windows for Whisper.

### 2.5 Context Manager (`app/streaming/context.py`)

Maintains cross-window context (audio overlap + committed transcript).
Strategy selected per `adr/005-transcript-context.md`.

### 2.6 Inference Engine (`app/inference/*`)

Isolated behind an abstraction. The pipeline depends on
`InferenceEngine`, not on `faster-whisper` directly. Implementations:
`FasterWhisperEngine`, `MockInferenceEngine`, future engines.

### 2.7 Transcript State Manager (`app/transcript/state.py`)

Distinguishes committed text (stable) from unstable partial hypotheses and
emits sequenced `transcript` events with `is_final`.

---

## 3. Session Lifecycle

```text
CONNECTING
    ↓
INITIALIZING
    ↓
ACTIVE
    ↓
PROCESSING      (inference in flight)
    ↓
ACTIVE
    ↓
STOPPING
    ↓
CLOSED
```

Error path (from any state):

```text
ANY STATE
    ↓
ERROR
    ↓
CLOSED
```

Transition rules:

- Only the session owner task may mutate session state.
- `PROCESSING` blocks normal-state transitions but not cancellation.
- `ERROR` is terminal with respect to processing; cleanup proceeds to `CLOSED`.

---

## 4. Concurrency Model

### 4.1 Event Loop

- All I/O and orchestration run on the asyncio event loop.
- No blocking calls in the request path.

### 4.2 GPU Boundary

GPU inference is CPU-blocking (CTranslate2 runs synchronously). To avoid
starving the event loop:

- Inference is bounded by `MAX_CONCURRENT_INFERENCES` (default 1).
- Inference is submitted through a dedicated worker task / executor with an
  `asyncio.Semaphore` gate.
- Backpressure flows from the inference gate back through the pipeline to the
  bounded queue (see `adr/004-inference-scheduling.md`).

```text
        ┌──────────────┐
  loop  │  asyncio     │   semaphore + worker task
────────►  pipeline  ──►  ───────────────►  GPU inference
        └──────────────┘
```

### 4.3 Concurrent Session Limits

| Limit                          | Owner        |
| ------------------------------ | ------------ |
| `MAX_CONCURRENT_SESSIONS`      | Session Mgr  |
| `MAX_CONCURRENT_INFERENCES`    | Inference    |
| `MAX_QUEUE_SIZE`               | Per-session  |

---

## 5. Clock and Timestamp Model

> The PRD states the requirement briefly; this section defines the model.

### 5.1 Definitions

- **wall clock**: `time.time()` for calendar timestamps and log correlation.
- **monotonic**: `time.monotonic_ns()` — strictly monotonic, used for all
  duration/latency measurement. Never mixed with wall clock for arithmetic.
- **generated_at_ms**: client-optional timestamp (epoch ms) attached to audio
  frames. Used for jitter observation only — never trusted for ordering.
- **seq**: logical sequence number assigned by the **backend** on receipt,
  used as the ordering authority (not network arrival).
- **speech_start_monotonic**: set at first sustained VAD speech detection
  (see VAD segment start event). Basis for `first_result_latency`.

### 5.2 Rules

1. All elapsed-time metrics (`latency_ms`, `RTF`, `first_result_latency`) use
   monotonic timestamps.
2. Wall clock is used for `created_at`, `session_duration`, and log timestamps.
3. Sequence numbers are single-sourced from the backend.
4. A client timestamp that is missing, malformed, or out of a sanity window is
   rejected or ignored, never used for ordering.

### 5.3 Metric Formula

```text
started                = time.monotonic_ns()
first_result_latency = first_transcript_monotonic - speech_start_monotonic
inference_latency    = inference_end_monotonic - inference_start_monotonic
RTF                  = inference_latency / audio_window_duration
session_duration     = wall(close) - wall(created_at)
```

Every pipeline stage owns its start/end timestamp pair. The stage timing
record includes audio capture (client diagnostic), network receive, queueing,
VAD, window formation, inference, and result emission/delivery. Server-side
durations use monotonic timestamps; client capture and delivery timestamps are
reported separately and are never used to establish event ordering.

---

## 6. Session Cancellation

> Requirement stated briefly in PRD; this section is the design.

### 6.1 Triggers

- Client WebSocket disconnect (any point).
- Client `stop` / `flush` control message.
- Resource limit exceeded (queue overflow policy, session duration cap, GPU OOM).
- Server shutdown (`SIGTERM`).

### 6.2 Protocol

On a session cancellation/disconnect:

```text
Disconnect
    ↓
Session
├── receiver
├── processor
├── inference
└── sender
    ↓
TaskGroup cancellation
    ↓
Drain / release bounded resources (queue, buffer, GPU slot, semaphore permits)
    ↓
Publish session_closed log + metrics
    ↓
Session → CLOSED
```

### 6.3 Guarantees

- In-flight inference is cancelled promptly and its GPU slot released.
- No task leaks: every per-session task is a child of a task group tied to the
  session scope.
- Cancellation is idempotent: double-close is a no-op.
- Server shutdown initiates a graceful drain: stop accepting sessions, finish or
  cancel active work, release resources, exit; a hard timeout forces exit.

---

## 7. Failure Handling

| Failure            | Behavior                                                    |
| ------------------ | ----------------------------------------------------------- |
| Client disconnect  | Cancellation path (§6)                                      |
| Malformed frame    | Structured error event, reject frame, session survives       |
| Queue overflow     | `QUEUE_OVERFLOW_POLICY`, emit metric                        |
| Inference timeout  | Cancel inference, emit `INFERENCE_TIMEOUT`, session survives |
| CUDA OOM           | Abort affected session, metric, attempted recovery           |
| Model load failure | Service stays unready until engine is ready                  |

---

## 8. Observability

- Structured logs via `structlog`; every event carries `session_id`,
  `sequence`, `model`, `latency`, `error_code` where relevant.
- Prometheus metrics (see `PRD §30–31`): `active_sessions`, `total_sessions`,
  `queue_depth`, `queue_overflows`, `inference_latency`, `first_result_latency`,
  `inference_errors`, `gpu_*`.
- Health endpoints: `/health` (process alive), `/ready` (inference ready).

---

## 9. Key Decisions

- WebSocket over WebRTC — `adr/001-websocket-over-webrtc.md`
- faster-whisper / CTranslate2 — `adr/002-faster-whisper.md`
- In-process inference — `adr/003-in-process-inference.md`
- Inference scheduling / bounded concurrency — `adr/004-inference-scheduling.md`
- Transcript context strategy — `adr/005-transcript-context.md`
- Ephemeral GPU deployment — `adr/006-ephemeral-gpu.md`
