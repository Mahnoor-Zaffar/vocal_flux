# VocalFlux

## Product Requirements Document

**Version:** 2.0  
**Status:** Ready for Implementation  
**Project Type:** Portfolio / Systems Engineering Project  
**Primary Domain:** Real-Time Speech-to-Text / ML Inference  
**Backend:** Python / FastAPI  
**Frontend:** Next.js / TypeScript  
**Inference:** faster-whisper / CTranslate2  
**Deployment:** Docker / OrbStack / Ephemeral GPU

---

# 1. Executive Summary

VocalFlux is a production-oriented **real-time speech-to-text inference system** built around Whisper.

The system captures microphone audio in a web browser, streams audio over a persistent WebSocket connection, processes the stream through a low-latency audio pipeline, performs GPU-accelerated speech recognition, and streams incremental transcript updates back to the client.

VocalFlux is intentionally designed as an **ML infrastructure and backend engineering project**, rather than a generic voice assistant.

The core engineering challenge is:

> How do you turn a fundamentally window-based speech recognition model into a reliable, low-latency, observable streaming inference service?

VocalFlux addresses this through:

- Browser-side audio capture
- Binary WebSocket streaming
- Per-session state management
- Bounded asynchronous queues
- Voice Activity Detection
- Audio buffering and windowing
- Context-aware Whisper inference
- Partial and final transcript state
- GPU inference
- Backpressure
- Resource limits
- Structured observability
- Accuracy and latency benchmarking
- Ephemeral GPU deployment

---

# 2. Product Vision

Build a compact but production-minded real-time ASR platform that demonstrates strong understanding of:

- Backend architecture
- Async Python
- WebSockets
- Streaming systems
- Audio processing
- ML inference
- GPU workloads
- Concurrency
- Backpressure
- Observability
- Performance engineering
- Reliability engineering
- Containerized deployment

The project should be small enough to understand completely but sophisticated enough to serve as a serious engineering portfolio artifact.

---

# 3. Problem Statement

Whisper is highly capable for speech recognition but was designed around audio windows rather than persistent real-time streaming.

A naive implementation looks like:

```text
Audio File
    ↓
Whisper
    ↓
Transcript
```

This works for batch transcription but does not provide a good real-time experience.

A streaming system introduces additional challenges:

```text
Microphone
    ↓
Continuous Audio
    ↓
Network Transport
    ↓
Buffering
    ↓
Speech Detection
    ↓
Windowing
    ↓
Inference
    ↓
Partial Results
    ↓
Final Results
```

The system must also deal with:

- Network jitter
- Out-of-order chunks
- Slow inference
- Queue buildup
- GPU exhaustion
- Session disconnects
- Context loss
- Duplicate transcript text
- Changing partial hypotheses
- Model loading
- Concurrent sessions

VocalFlux exists to solve these engineering problems.

---

# 4. Goals

## G1. Real-Time Speech Recognition

Provide responsive browser-based speech transcription.

## G2. Streaming Architecture

Support persistent WebSocket connections and incremental audio processing.

## G3. Low Latency

Target sub-second transcription feedback under normal demo conditions.

## G4. Correct Transcript Semantics

Support unstable partial hypotheses and committed final transcript segments without producing duplicate text.

## G5. Efficient Inference

Use VAD, buffering, windowing, and model configuration to reduce unnecessary computation.

## G6. Robust Session Management

Each client connection must have an isolated, bounded session.

## G7. Backpressure

Prevent slow inference from causing unbounded memory growth.

## G8. Observable Performance

Measure latency, throughput, inference speed, GPU utilization, and system health.

## G9. Measurable Accuracy

Evaluate transcription quality using WER/CER against known audio samples.

## G10. Reproducible Deployment

Run locally using Docker/OrbStack and remotely using an ephemeral GPU instance.

---

# 5. Non-Goals

The following are intentionally excluded from V1.

## Product Features

- User accounts
- Authentication
- Billing
- Subscriptions
- Multi-user dashboards
- Persistent user profiles
- Mobile applications

## AI Features

- Conversational agents
- LLM agents
- Function calling
- RAG
- Text summarization
- AI rewriting
- Grammar correction
- Text generation

## Audio Features

- Long-term audio storage
- Music transcription
- Audio editing
- Advanced studio processing

## Infrastructure

- Kubernetes
- Multi-region deployment
- Service mesh
- Complex microservice architecture
- Distributed inference in V1

Redis/Celery and GPU worker pools are considered future scalability extensions.

---

# 6. Target Users

## Primary

Developers evaluating the technical capabilities of the system.

## Secondary

Users who want to test real-time speech recognition through a browser.

## Portfolio Audience

The system should be understandable and compelling to:

- Backend engineers
- AI engineers
- ML infrastructure engineers
- Platform engineers
- Systems engineers
- Startup founders
- Technical recruiters

---

# 7. Core User Journey

```text
User opens VocalFlux
        ↓
Clicks "Start Recording"
        ↓
Browser requests microphone access
        ↓
AudioWorklet starts
        ↓
WebSocket connection established
        ↓
Session created
        ↓
PCM audio begins streaming
        ↓
Backend receives chunks
        ↓
Audio enters bounded queue
        ↓
VAD detects speech
        ↓
Audio buffer accumulates
        ↓
Inference window created
        ↓
Whisper performs inference
        ↓
Transcript hypothesis generated
        ↓
Partial transcript sent to browser
        ↓
Speech segment becomes stable
        ↓
Final transcript committed
        ↓
User clicks "Stop"
        ↓
Session gracefully terminates
```

---

# 8. System Architecture

```text
                           VOCALFLUX

┌──────────────────────────────────────────────────────────────┐
│                         BROWSER                              │
│                                                              │
│  Next.js + React + TypeScript                                │
│                                                              │
│  Microphone                                                  │
│      ↓                                                       │
│  MediaStream                                                 │
│      ↓                                                       │
│  AudioContext                                                │
│      ↓                                                       │
│  AudioWorklet                                                │
│      ↓                                                       │
│  PCM16 / 16kHz / Mono                                        │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               │ Binary WebSocket
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                         FASTAPI                              │
│                                                              │
│  WebSocket Gateway                                           │
│          ↓                                                   │
│  Session Manager                                              │
│          ↓                                                   │
│  Bounded Audio Queue                                         │
│          ↓                                                   │
│  Audio Pipeline                                              │
│    ├── Validation                                             │
│    ├── Decoder                                                │
│    ├── Normalization                                          │
│    ├── VAD                                                    │
│    ├── Buffering                                               │
│    └── Windowing                                               │
│          ↓                                                   │
│  Context Manager                                              │
│          ↓                                                   │
│  Inference Engine                                             │
│          ↓                                                   │
│  faster-whisper / CTranslate2                                │
│          ↓                                                   │
│  Transcript State Manager                                     │
│          ↓                                                   │
│  WebSocket Result Stream                                      │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
                         Browser UI

┌──────────────────────────────────────────────────────────────┐
│                      OBSERVABILITY                            │
│                                                              │
│  Prometheus + structured logging                              │
│                                                              │
│  Latency | RTF | WER | GPU | Sessions | Errors               │
└──────────────────────────────────────────────────────────────┘
```

---

# 9. Frontend Architecture

The frontend is deliberately thin.

## Technology

- Next.js
- React
- TypeScript
- Tailwind CSS
- Web Audio API
- AudioWorklet
- WebSocket API

## Responsibilities

The frontend owns:

1. Microphone permissions
2. Audio capture
3. PCM conversion
4. WebSocket communication
5. Transcript rendering
6. Connection state
7. Metrics display
8. Session controls

The frontend does **not** own:

- Whisper inference
- Audio model logic
- Session orchestration
- VAD decisions
- Inference scheduling

---

# 10. Frontend UI

The primary screen should be intentionally minimal.

```text
┌──────────────────────────────────────────────┐
│ VocalFlux                                    │
│ Real-Time Speech Inference                   │
│                                              │
│              [ Start Recording ]             │
│                                              │
│ Status: ● Connected                           │
│                                              │
│ ┌──────────────────────────────────────────┐ │
│ │ The quick brown fox jumps over...       │ │
│ │                                          │ │
│ │ the lazy dog.                            │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ ──────────────────────────────────────────── │
│                                              │
│ Model        Whisper Small                   │
│ First Result 247 ms                          │
│ Current      183 ms                          │
│ RTF          0.14x                           │
│ Audio        00:34                           │
│                                              │
│             [ Stop Recording ]               │
└──────────────────────────────────────────────┘
```

---

# 11. Browser Audio Architecture

The browser should use `AudioWorklet`.

```text
Microphone
    ↓
MediaStream
    ↓
AudioContext
    ↓
AudioWorklet
    ↓
PCM frames
    ↓
PCM16 encoding
    ↓
WebSocket
```

## Audio Contract

V1 standardizes on:

```text
Encoding:       PCM16
Sample rate:    16,000 Hz
Channels:       1
Byte order:     Little-endian
Transport:      Binary WebSocket frames
```

The browser should perform resampling when possible.

The backend must still validate the resulting audio stream.

---

# 12. WebSocket Architecture

Endpoint:

```text
/ws/v1/transcribe
```

The WebSocket is long-lived for the duration of a transcription session.

## Client → Server

Audio is sent as binary frames.

Each frame must have an associated logical sequence number.

The protocol should support control messages such as:

```text
start
stop
flush
ping
```

### 12.1 Audio Frame Identity and Ordering

Each audio frame must be associated with:

```text
session_id
stream_id
sequence_number
```

The protocol must define and enforce the following behavior:

- Duplicate sequence numbers are ignored without duplicating audio or transcript output.
- Old sequence numbers are rejected or ignored according to the protocol policy.
- Missing sequence numbers are detected and observable.
- Invalid sequence numbers produce a structured protocol error.

The exact wire format is defined in `docs/protocol.md`.

---

# 13. Session Management

Each WebSocket connection creates a `TranscriptionSession`.

A session contains:

```text
session_id
created_at
state
sequence_number
audio_buffer
audio_queue
transcript_state
context
metrics
```

## Session Lifecycle

```text
CONNECTING
    ↓
INITIALIZING
    ↓
ACTIVE
    ↓
PROCESSING
    ↓
ACTIVE
    ↓
STOPPING
    ↓
CLOSED
```

Error state:

```text
ANY STATE
    ↓
ERROR
    ↓
CLOSED
```

Sessions must not share mutable audio state.

### 13.1 Clock and Timestamp Requirements

Server-side latency measurements must use a monotonic clock. Audio receipt,
queueing, VAD, window formation, inference, and result emission timestamps must
be independently measurable.

The implementation-level clock and timestamp model is defined in
`docs/architecture.md`.

### 13.2 Session Cancellation Requirement

Session termination must cancel all session-owned asynchronous tasks and release
associated resources, including audio buffers, queue entries, inference permits,
and WebSocket resources.

---

# 14. Audio Pipeline

The backend audio pipeline is:

```text
Binary PCM
    ↓
Validation
    ↓
Decoder
    ↓
Normalization
    ↓
VAD
    ↓
Buffer
    ↓
Windowing
    ↓
Context Manager
    ↓
Inference
```

Each stage should have a clearly defined responsibility.

---

# 15. Audio Validation

The backend must validate:

- Message size
- Sample rate
- Channel count
- Encoding
- Sequence number
- Session ownership
- Maximum session duration

Invalid input must not crash the service.

Errors should be represented using structured protocol messages.

---

# 16. Audio Buffer

Each session owns a bounded audio buffer.

The buffer must have configurable limits:

```text
MAX_BUFFER_DURATION
MAX_BUFFER_BYTES
```

The buffer must never grow indefinitely.

If the system cannot process audio fast enough, backpressure must be applied.

---

# 17. Backpressure

Backpressure is a first-class architectural requirement.

Example failure scenario:

```text
Audio Arrival Rate
       │
       ▼
  100 chunks/sec
       │
       ▼
┌─────────────────┐
│ Audio Queue     │
│ ██████████████  │
└────────┬────────┘
         │
         ▼
    Whisper GPU
    20 chunks/sec
```

Without bounded queues, memory usage can grow indefinitely.

## Requirements

The system must implement:

```text
MAX_QUEUE_SIZE
MAX_BUFFER_DURATION
MAX_CONCURRENT_INFERENCES
QUEUE_OVERFLOW_POLICY
```

V1 should use:

```text
asyncio.Queue(maxsize=N)
```

When capacity is exhausted, the system must either:

- Apply backpressure
- Reject new audio
- Terminate an unhealthy session

The policy must be explicit and observable.

---

# 18. Voice Activity Detection

Silero VAD is used to identify speech.

```text
Audio
  │
  ▼
VAD
  │
  ├── Silence → avoid inference
  │
  └── Speech → buffer
```

VAD parameters must be configurable.

Important parameters include:

- Speech probability threshold
- Minimum speech duration
- Minimum silence duration
- Padding
- Segment timeout

---

# 19. Windowing Strategy

Whisper inference operates on temporal windows.

V1 should use configurable windows approximately in the:

```text
1-2 second
```

range.

The actual optimal configuration must be determined experimentally.

Tradeoff:

```text
Smaller window
    ↓
Lower latency
    ↓
Less context
    ↓
Potentially worse accuracy

Larger window
    ↓
Higher latency
    ↓
More context
    ↓
Potentially better accuracy
```

---

# 20. Whisper Context Management

Context loss between windows is a major challenge.

Naively:

```text
Window 1 → Whisper
Window 2 → Whisper
Window 3 → Whisper
```

can cause:

- Repeated words
- Missing context
- Inconsistent punctuation
- Boundary errors

VocalFlux must maintain a context representation.

Potential strategies:

### Strategy A: Previous Transcript Prompt

Pass recent committed text as inference context.

### Strategy B: Overlapping Windows

Include a small amount of previous audio in the next window.

### Strategy C: Hybrid

Use:

```text
Recent audio overlap
+
Recent transcript context
```

The initial implementation should select one strategy and benchmark it.

The strategy must be documented in an ADR.

---

# 21. Inference Engine

The inference layer must be isolated behind an abstraction.

Conceptually:

```text
InferenceEngine
      │
      ├── FasterWhisperEngine
      ├── MockInferenceEngine
      └── Future implementations
```

The WebSocket and streaming layers must not directly depend on `faster-whisper`.

This enables:

- Testing
- Model replacement
- API-based inference
- CPU fallback
- Future model routing

---

# 22. Model Lifecycle

The model must have an explicit lifecycle.

```text
CONTAINER START
      ↓
LOAD CONFIG
      ↓
LOAD MODEL
      ↓
MOVE MODEL TO DEVICE
      ↓
WARM-UP INFERENCE
      ↓
READY
      ↓
ACCEPT SESSIONS
```

The service must not report itself as fully ready until inference is actually available.

## Health States

```text
STARTING
READY
DEGRADED
SHUTTING_DOWN
FAILED
```

The health endpoint should distinguish:

```text
Process alive
```

from:

```text
Inference ready
```

---

# 23. GPU Resource Management

The inference layer must track:

- GPU memory
- Model memory
- Inference concurrency
- Inference duration
- GPU utilization where available

V1 should use a single GPU worker.

The architecture must avoid unrestricted concurrent GPU inference.

A configurable limit should exist:

```text
MAX_CONCURRENT_INFERENCES
```

### 23.1 CPU/GPU Concurrency Boundary

Network and session handling must remain non-blocking. GPU-bound inference must
be isolated behind a bounded inference scheduler and must not block the FastAPI
event loop.

---

# 24. Transcript State Model

This is a critical part of the system.

Whisper may repeatedly revise its interpretation of recent speech.

Therefore VocalFlux must distinguish:

```text
Committed Transcript
```

from:

```text
Unstable Transcript
```

Conceptually:

```text
┌──────────────────────────┬─────────────────────┐
│ Committed                │ Unstable            │
│                          │                     │
│ "The quick brown fox"    │ "jumps over..."     │
└──────────────────────────┴─────────────────────┘
```

The frontend should replace the unstable portion as new partial results arrive.

When the segment becomes stable:

```text
Unstable
   ↓
Commit
   ↓
Committed Transcript
```

This prevents duplicate transcript output.

---

# 25. Transcript Events

## Session Started

```json
{
  "type": "session_started",
  "session_id": "abc123"
}
```

## Partial

```json
{
  "type": "transcript",
  "sequence": 42,
  "text": "The quick brown",
  "is_final": false,
  "latency_ms": 210
}
```

## Final

```json
{
  "type": "transcript",
  "sequence": 43,
  "text": "The quick brown fox.",
  "is_final": true,
  "latency_ms": 190
}
```

## Error

```json
{
  "type": "error",
  "code": "INFERENCE_TIMEOUT",
  "message": "Transcription inference exceeded the configured timeout."
}
```

---

# 26. Ordering Guarantees

Transcript events must maintain logical ordering.

Each event contains a sequence number.

The system must handle:

- Missing audio chunks
- Duplicate chunks
- Out-of-order chunks
- Delayed inference results

The frontend must not assume that network arrival order alone represents logical transcript order.

---

# 27. Failure Model

The system must explicitly handle:

## Client Disconnect

```text
Disconnect
    ↓
Cancel session tasks
    ↓
Drain/release resources
    ↓
Close session
```

## Malformed Audio

```text
Invalid audio
    ↓
Structured error
    ↓
Reject chunk
```

## Queue Overflow

```text
Queue full
    ↓
Apply backpressure
    ↓
Reject/drop according to policy
    ↓
Emit metric
```

## Inference Timeout

```text
Inference timeout
    ↓
Cancel inference
    ↓
Emit error
    ↓
Keep service alive
```

## GPU Out-of-Memory

```text
CUDA OOM
    ↓
Abort affected session
    ↓
Record metric
    ↓
Attempt controlled recovery
```

The exact recovery strategy should depend on whether the model/runtime can safely recover without restarting the process.

## Model Loading Failure

The service must remain unavailable until the inference engine is ready.

---

# 28. Resource Limits

VocalFlux must protect itself from abusive or accidental resource consumption.

Configurable limits:

```text
MAX_MESSAGE_SIZE
MAX_SESSION_DURATION
MAX_AUDIO_BUFFER
MAX_QUEUE_SIZE
MAX_CONCURRENT_SESSIONS
MAX_CONCURRENT_INFERENCES
INFERENCE_TIMEOUT
```

These must be enforced server-side.

## 28.1 Security and Abuse Controls

VocalFlux must protect the service from untrusted streaming input and resource
exhaustion. V1 must define and enforce:

- Maximum message size
- Maximum session duration
- Maximum concurrent connections
- Rate limiting
- WebSocket origin policy
- Input validation
- GPU resource limits
- CORS policy

Detailed threats, assumptions, and mitigations are documented in
`docs/threat-model.md`.

---

# 29. API

## Health

```text
GET /health
```

## Readiness

```text
GET /ready
```

## Metrics

```text
GET /metrics
```

## WebSocket

```text
WS /ws/v1/transcribe
```

No additional REST API is required for V1.

---

# 30. Observability

VocalFlux must expose both logs and metrics.

## Structured Logging

Use `structlog`.

Important events:

```text
session_started
session_closed
audio_received
audio_dropped
vad_segment_started
vad_segment_finished
inference_started
inference_completed
inference_failed
queue_overflow
model_loaded
model_ready
```

Every event should include useful correlation fields:

```text
session_id
sequence
model
latency
error_code
```

---

# 31. Metrics

Prometheus metrics should include:

```text
active_sessions
total_sessions
audio_seconds_processed
audio_seconds_dropped
inference_count
inference_errors
inference_latency
first_result_latency
queue_depth
queue_overflows
session_duration
model_load_time
```

GPU metrics should include where available:

```text
gpu_memory_used
gpu_memory_total
gpu_utilization
```

---

# 32. Performance Metrics

VocalFlux should define:

## First Result Latency

Time from the start of speech to the first transcript event.

```text
FirstResultLatency =
FirstTranscriptTimestamp - SpeechStartTimestamp
```

## Inference Latency

Time spent inside model inference.

## Real-Time Factor

```text
RTF = inference_time / audio_duration
```

Target:

```text
RTF < 1.0
```

Lower is better.

### 32.1 Latency Requirement

Target first-result latency is:

```text
< 1 second
```

The system must expose independently measurable stage-level timing for:

- Audio capture
- Network receive
- Queueing
- VAD
- Window formation
- Inference
- Result delivery

The measurement methodology and latency budget are defined in
`docs/benchmarking.md`.

---

# 33. Accuracy Evaluation

Performance alone is insufficient.

VocalFlux must evaluate transcription quality.

## Metrics

### Word Error Rate

```text
WER
```

### Character Error Rate

```text
CER
```

## Evaluation Dataset

Create a small controlled dataset containing:

- Different speakers
- Different speaking speeds
- Short utterances
- Long utterances
- Quiet speech
- Background noise
- Different accents where practical

Initial target:

```text
10-30 representative audio samples
```

Each sample should have ground-truth transcription.

---

# 34. Accuracy Experiments

Evaluate the effect of:

```text
Model size
Window size
VAD threshold
Overlap duration
Context strategy
Compute type
```

Example experiment:

```text
                    Latency
                       ▲
                       │
                 Medium Model
                       │
          Small Model  │
                       │
                       └──────────────────► Accuracy
```

The project should document the tradeoffs rather than simply selecting the largest model.

---

# 35. Benchmark Suite

Benchmark:

```text
1 stream
5 streams
10 streams
25 streams
50 streams
```

Measure:

```text
p50 latency
p95 latency
p99 latency
RTF
throughput
GPU utilization
GPU memory
CPU utilization
error rate
```

The system should continue testing until a clear saturation point is identified.

## 35.1 Evaluation Requirements

VocalFlux must provide reproducible measurements for:

- p50, p95, and p99 latency
- First-result latency
- Real-time factor (RTF)
- WER/CER
- GPU utilization
- GPU memory
- Concurrent sessions

The reproducible benchmark methodology is defined in `docs/benchmarking.md`.

## 35.2 Model Configuration

The inference layer must support configuration of:

- Model
- Device
- Compute type
- Language
- Beam size
- VAD parameters
- Window size
- Overlap

The configuration matrix and comparison results belong in
`docs/benchmarking.md`.

---

# 36. Testing Strategy

## Unit Tests

Test:

- Audio buffer
- Windowing
- VAD state
- Session lifecycle
- Transcript state
- Protocol validation
- Backpressure
- Configuration

## Integration Tests

Test:

```text
WebSocket
    ↓
Session
    ↓
Audio Pipeline
    ↓
Mock Inference Engine
    ↓
Transcript Event
```

## Model Tests

Run selected tests against the actual Whisper model.

## Load Tests

Use Locust or a custom async client to simulate concurrent audio streams.

---

# 37. Python Project Structure

```text
backend/
│
├── app/
│   │
│   ├── main.py
│   │
│   ├── api/
│   │   ├── health.py
│   │   ├── metrics.py
│   │   └── websocket.py
│   │
│   ├── audio/
│   │   ├── decoder.py
│   │   ├── buffer.py
│   │   ├── vad.py
│   │   ├── window.py
│   │   └── normalization.py
│   │
│   ├── inference/
│   │   ├── engine.py
│   │   ├── model.py
│   │   ├── whisper.py
│   │   └── lifecycle.py
│   │
│   ├── streaming/
│   │   ├── session.py
│   │   ├── manager.py
│   │   ├── pipeline.py
│   │   ├── queue.py
│   │   └── context.py
│   │
│   ├── transcript/
│   │   ├── state.py
│   │   ├── assembler.py
│   │   └── events.py
│   │
│   ├── schemas/
│   │   ├── audio.py
│   │   ├── session.py
│   │   └── transcript.py
│   │
│   └── core/
│       ├── config.py
│       ├── logging.py
│       └── metrics.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── model/
│   └── benchmarks/
│
├── pyproject.toml
├── Dockerfile
└── README.md
```

---

# 38. Python Dependencies

Core:

```text
fastapi
uvicorn[standard]

pydantic
pydantic-settings

faster-whisper
ctranslate2

numpy
av
silero-vad

prometheus-client
structlog
```

Testing:

```text
pytest
pytest-asyncio
httpx
locust
```

Redis is intentionally excluded from the initial implementation.

---

# 39. Frontend Structure

```text
web/
│
├── app/
│   └── page.tsx
│
├── components/
│   ├── Recorder.tsx
│   ├── Transcript.tsx
│   ├── MetricsPanel.tsx
│   ├── ConnectionStatus.tsx
│   ├── SessionControls.tsx
│   └── AudioVisualizer.tsx
│
├── hooks/
│   ├── useRecorder.ts
│   └── useTranscription.ts
│
├── lib/
│   ├── websocket.ts
│   ├── audio.ts
│   └── protocol.ts
│
└── types/
    └── transcription.ts
```

---

# 40. Infrastructure

## Local

```text
macOS
  ↓
OrbStack
  ↓
Docker
  ↓
VocalFlux
```

The local environment should run with:

```text
docker compose up
```

---

# 41. Demo Deployment

VocalFlux does not require continuous GPU infrastructure.

The demo deployment should use an ephemeral GPU.

```text
GitHub
   ↓
GitHub Actions
   ↓
Container Image
   ↓
RunPod
   ↓
GPU
   ↓
VocalFlux
```

The GPU should only be provisioned during:

- Portfolio demonstrations
- Benchmarking
- Development requiring GPU inference

---

# 42. Deployment Lifecycle

## Startup

```text
Provision GPU
      ↓
Pull container
      ↓
Start application
      ↓
Load Whisper
      ↓
Warm up model
      ↓
Health check
      ↓
READY
```

## Shutdown

```text
Stop accepting sessions
      ↓
Finish/cancel active work
      ↓
Release resources
      ↓
Terminate GPU
```

---

# 43. Docker Requirements

The container must:

- Install dependencies deterministically
- Support GPU execution
- Expose the FastAPI port
- Include health checks
- Configure model/runtime through environment variables
- Log to stdout/stderr
- Shut down gracefully

The container must not depend on developer-specific filesystem paths.

---

# 44. Configuration

Configuration should be managed through environment variables.

Example:

```text
WHISPER_MODEL=small
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16

AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1

VAD_THRESHOLD=0.5

WINDOW_SIZE_MS=1500
OVERLAP_MS=300

MAX_SESSION_DURATION=3600
MAX_CONCURRENT_SESSIONS=10
MAX_CONCURRENT_INFERENCES=1

MAX_QUEUE_SIZE=10
INFERENCE_TIMEOUT=10
```

Exact values must be determined through benchmarking.

---

# 45. Architecture Decision Records

The repository should contain:

```text
docs/
├── architecture.md
├── protocol.md
├── benchmarking.md
└── adr/
    ├── 001-websocket-over-webrtc.md
    ├── 002-faster-whisper.md
    ├── 003-in-process-inference.md
    ├── 004-asyncio-over-celery.md
    ├── 005-ephemeral-gpu-deployment.md
    └── 006-transcript-context-strategy.md
```

Each ADR should explain:

- Problem
- Alternatives
- Decision
- Tradeoffs
- Consequences

Example:

> We initially use in-process inference because the target deployment is a single GPU worker. Distributed infrastructure will only be introduced once benchmarking demonstrates that a single worker is insufficient.

---

# 46. Development Phases

## Phase 1: Inference Engine

Implement:

- Model loading
- Model lifecycle
- Basic transcription
- Benchmarking

Deliverable:

```text
audio → Whisper → transcript
```

---

## Phase 2: Audio Pipeline

Implement:

- Audio validation
- Decoding
- Normalization
- Buffering
- Windowing
- VAD

---

## Phase 3: Streaming Backend

Implement:

- FastAPI
- WebSocket
- Sessions
- Async queues
- Backpressure
- Transcript events

Deliverable:

```text
microphone → WebSocket → live transcript
```

---

## Phase 4: Transcript State

Implement:

- Partial transcript
- Unstable transcript
- Committed transcript
- Context management
- Ordering guarantees

---

## Phase 5: Frontend

Implement:

- Microphone capture
- AudioWorklet
- WebSocket client
- Live transcript
- Metrics
- Session controls

---

## Phase 6: Reliability

Implement:

- Resource limits
- Timeouts
- Graceful shutdown
- Error handling
- GPU failure handling
- Structured logging

---

## Phase 7: Observability

Implement:

- Prometheus
- Metrics
- Structured logs
- Health checks
- Readiness checks

---

## Phase 8: Evaluation

Build:

- Accuracy dataset
- WER/CER evaluation
- Latency benchmarks
- Concurrency benchmarks
- GPU benchmarks

---

## Phase 9: Containerization

Implement:

- Dockerfile
- Docker Compose
- GPU configuration
- Health checks

Local target:

```text
OrbStack → Docker → VocalFlux
```

---

## Phase 10: Ephemeral GPU Demo

Deploy to RunPod.

Validate:

```text
Browser
  ↓
WebSocket
  ↓
RunPod
  ↓
GPU
  ↓
Whisper
  ↓
Live transcript
```

---

## Phase 11: Documentation

Complete:

- Architecture diagram
- Protocol specification
- Setup guide
- Deployment guide
- Benchmark report
- Accuracy report
- ADRs
- Known limitations

---

# 47. Success Criteria

VocalFlux V1 is successful when:

- [ ] Browser microphone audio works.
- [ ] Audio is transmitted using binary WebSocket frames.
- [ ] PCM16 / 16 kHz / mono is supported.
- [ ] Each connection gets an isolated session.
- [ ] Audio is validated.
- [ ] Audio buffering is bounded.
- [ ] Backpressure is implemented.
- [ ] VAD prevents unnecessary inference.
- [ ] Audio windows are configurable.
- [ ] Whisper inference works on CPU/GPU.
- [ ] Model lifecycle is observable.
- [ ] Partial transcripts are supported.
- [ ] Final transcript segments are committed correctly.
- [ ] Transcript ordering is guaranteed.
- [ ] Context strategy is implemented and documented.
- [ ] WebSocket disconnects are handled.
- [ ] Inference failures are isolated.
- [ ] GPU resource limits exist.
- [ ] Prometheus metrics are exposed.
- [ ] Structured logs are available.
- [ ] Unit tests exist for core components.
- [ ] Integration tests cover the streaming pipeline.
- [ ] WER/CER evaluation exists.
- [ ] Latency benchmarks exist.
- [ ] Concurrency benchmarks exist.
- [ ] Docker deployment works locally.
- [ ] Ephemeral GPU deployment works.
- [ ] Documentation explains architecture and tradeoffs.

---

# 48. Definition of Done

A developer should be able to clone VocalFlux and run:

```text
docker compose up
```

Then:

```text
Open browser
      ↓
Start Recording
      ↓
Speak
      ↓
See partial transcript
      ↓
See final transcript
      ↓
Inspect latency/RTF metrics
```

The project must also provide reproducible benchmark commands and documented results.

A portfolio reviewer should be able to understand:

1. Why Whisper needs a streaming layer.
2. How audio moves through the system.
3. How sessions are isolated.
4. How backpressure prevents resource exhaustion.
5. How partial transcripts differ from committed text.
6. How context is maintained between inference windows.
7. How GPU inference is managed.
8. How failures are handled.
9. How latency is measured.
10. How transcription accuracy is evaluated.
11. How the system would scale beyond a single GPU.

---

# 49. Future Architecture

Once V1 has measurable bottlenecks, VocalFlux can evolve into:

```text
                         Load Balancer
                              │
                              ▼
                       FastAPI Gateway
                              │
                              ▼
                         Redis Queue
                              │
               ┌──────────────┼──────────────┐
               ▼              ▼              ▼
          GPU Worker      GPU Worker      GPU Worker
               │              │              │
          Whisper          Whisper          Whisper
               │              │              │
               └──────────────┼──────────────┘
                              ▼
                       Result Stream
                              │
                              ▼
                           Client
```

Potential future capabilities:

- Distributed GPU inference
- Worker autoscaling
- Model routing
- Speaker diarization
- Language detection
- Persistent transcripts
- WebRTC
- LLM post-processing
- Multi-region deployment

These are deliberately outside V1.

---

# 50. Engineering Principles

VocalFlux follows these principles:

1. **Streaming first.** Audio is treated as a continuous stream rather than a collection of files.
2. **Bound everything.** Queues, buffers, sessions, inference, and resource consumption must have limits.
3. **Separate concerns.** Transport, session management, audio processing, transcript state, and inference remain independent.
4. **Measure before optimizing.** Performance decisions must be supported by benchmarks.
5. **Accuracy matters.** A fast transcription system that produces poor transcripts is not successful.
6. **Keep GPU work controlled.** Unbounded concurrent inference is unacceptable.
7. **Prefer simple architecture initially.** Distributed infrastructure must be justified by measured bottlenecks.
8. **Design for failure.** Client disconnects, GPU failures, malformed input, and inference errors are expected cases.
9. **Make inference replaceable.** The application must not be tightly coupled to a single model implementation.
10. **Document engineering decisions.** Important architectural tradeoffs belong in ADRs.

---

# 51. Final System Boundary

The definitive V1 boundary is:

```text
┌──────────────────────────────────────────────────────────┐
│                      VOCALFLUX                           │
│                                                          │
│  Browser Audio                                           │
│       ↓                                                  │
│  WebSocket Transport                                     │
│       ↓                                                  │
│  Session Management                                      │
│       ↓                                                  │
│  Bounded Queue / Backpressure                            │
│       ↓                                                  │
│  Audio Processing                                        │
│       ├── Validation                                      │
│       ├── VAD                                             │
│       ├── Buffering                                       │
│       └── Windowing                                       │
│       ↓                                                  │
│  Context Management                                      │
│       ↓                                                  │
│  Whisper Inference                                       │
│       ↓                                                  │
│  Transcript State                                        │
│       ├── Unstable                                       │
│       └── Committed                                      │
│       ↓                                                  │
│  Result Streaming                                        │
│       ↓                                                  │
│  Browser UI                                              │
│                                                          │
│  ──────────────────────────────────────────────────────  │
│                                                          │
│  Observability                                           │
│  ├── Metrics                                             │
│  ├── Structured Logs                                     │
│  ├── Latency                                             │
│  ├── RTF                                                 │
│  ├── GPU Metrics                                         │
│  └── Errors                                              │
│                                                          │
│  Evaluation                                              │
│  ├── WER                                                 │
│  ├── CER                                                 │
│  ├── Latency Benchmarks                                  │
│  └── Concurrency Benchmarks                              │
└──────────────────────────────────────────────────────────┘
```

**VocalFlux V1 is complete when this boundary works reliably, is measurable, is reproducible, and has documented performance and accuracy characteristics.**

The project should remain intentionally narrow: **real-time speech transport, streaming audio processing, GPU ASR inference, transcript state management, and measurable systems performance.** Anything beyond that should earn its place through a demonstrated engineering requirement.
