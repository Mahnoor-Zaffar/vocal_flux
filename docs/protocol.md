# VocalFlux WebSocket Protocol

**Status:** Draft v1  
**Version:** 1.0  
**Endpoint:** `ws://<host>/ws/v1/transcribe`

---

## 1. Goal

Define the wire protocol between the browser client and the backend for
real-time audio streaming and incremental transcription.

---

## 2. Transports and Frame Types

A single WebSocket connection carries two logical channels multiplexed by
frame type:

- **Text frame** — JSON audio-frame metadata, control, or status message.
- **Binary frame** — audio payload (PCM16 LE, 16 kHz, mono).

Text frames are `application/json` (UTF-8).

---

## 3. Audio Frame

### 3.1 Format

```text
Encoding:       PCM16 (signed little-endian)
Sample rate:    16,000 Hz
Channels:       1 (mono)
Bytes/sample:   2
Payload:        raw PCM bytes only
```

Each audio frame consists of a JSON `audio_frame` metadata message immediately
followed by one binary PCM payload. The metadata identifies the logical frame;
the binary frame contains only audio bytes.

```json
{
  "type": "audio_frame",
  "session_id": "abc123",
  "stream_id": "microphone-1",
  "sequence_number": 42,
  "capture_started_ms": 1200
}
```

`capture_started_ms` is optional and diagnostic only. The server assigns the
authoritative receive timestamp and must not use a client timestamp for
ordering.

### 3.2 Frame Size

A single frame should carry a fixed, small chunk (e.g. 20–100 ms of audio,
320–3200 bytes). Default recommended chunk: **40 ms → 1280 bytes**.

The backend rejects frames exceeding `MAX_MESSAGE_SIZE`.

---

## 4. Text Messages

All text frames are JSON objects with exactly one `type` field.

### 4.1 Client → Server

| Type    | Direction     | Purpose                                            |
| ------- | ------------- | -------------------------------------------------- |
| `start` | client→server | Session already created on connect; optional hello |
| `audio_frame` | client→server | Metadata for the immediately following binary audio payload |
| `stop`  | client→server | Gracefully end session, commit final transcripts   |
| `flush` | client→server | Commit pending partial, keep session open          |
| `ping`  | client→server | Keepalive / liveness check                         |

#### `ping`

```json
{
  "type": "ping",
  "id": "p-123"
}
```

The server replies with `pong` carrying the same `id`.

---

### 4.2 Server → Client

| Type              | Purpose                                            |
| ----------------- | -------------------------------------------------- |
| `session_started` | Confirms session creation                          |
| `transcript`      | A partial or final transcript result               |
| `error`           | Structured error (recoverable or fatal)            |
| `pong`            | Reply to `ping`                                    |
| `session_closed`  | Confirms termination                               |

#### `session_started`

```json
{
  "type": "session_started",
  "session_id": "abc123"
}
```

#### `transcript`

```json
{
  "type": "transcript",
  "sequence": 42,
  "text": "The quick brown",
  "is_final": false,
  "latency_ms": 210,
  "committed_text": "The quick",
  "unstable_text": "brown",
  "stage_timings_ms": {
    "queueing": 3.2,
    "vad": 1.1,
    "window_formation": 0.4,
    "inference": 210.0,
    "result_delivery": 0.3
  },
  "first_result_latency_ms": 247.0,
  "from_ms": 1200,
  "to_ms": 2700,
  "commit_ms": null
}
```

| Field       | Type    | Meaning                                          |
| ----------- | ------- | ------------------------------------------------ |
| `sequence`  | int     | Monotonic backend ordering (authority)           |
| `text`      | string  | Hypothesized text for the window                 |
| `is_final`  | bool    | True → committed segment; False → unstable       |
| `latency_ms`| int     | Inference latency for that result                |
| `committed_text` | string | Stable transcript accumulated so far          |
| `unstable_text` | string | Replaceable current hypothesis                 |
| `stage_timings_ms` | object | Server-measured pipeline stage durations    |
| `first_result_latency_ms` | number|null | Speech start to first transcript         |
| `from_ms`   | int     | Start of audio window (ms, session-local)        |
| `to_ms`     | int     | End of audio window (ms)                         |
| `commit_ms` | int|null| Monotonic-delta of commit, null while unstable    |

#### `error`

```json
{
  "type": "error",
  "code": "INFERENCE_TIMEOUT",
  "message": "Transcription inference exceeded the configured timeout.",
  "fatal": false,
  "session_id": "abc123"
}
```

#### `session_closed`

```json
{
  "type": "session_closed",
  "session_id": "abc123",
  "reason": "client_stop"
}
```

---

## 5. Ordering and Sequence Numbers

### 5.1 Source of Truth

- The client sends `session_id`, `stream_id`, and `sequence_number` with each
  audio frame.
- The backend validates the identifiers and assigns authoritative receive and
  transcript sequence values.
- Network arrival order is **not** the ordering authority.
- Clients must render by `sequence`, applying unstable results to the pending
  region and final results to the committed region.

### 5.2 Handling Requirements

The system must tolerate:

1. **Missing chunks** — gaps in `sequence_number` are detected and observable;
   they do not abort the session by default.
2. **Duplicate chunks** — identical
   `(session_id, stream_id, sequence_number)` audio is ignored without
   reprocessing.
3. **Old chunks** — a `sequence_number` older than the accepted stream cursor
   is rejected or ignored according to the stale-frame policy.
4. **Invalid chunks** — missing identifiers, wrong types, or invalid numeric
   values produce `INVALID_SEQUENCE` or `INVALID_FRAME`.
5. **Out-of-order chunks** — buffered by sequence and re-ordered before the
   pipeline; short windows of disorder are absorbed, beyond that a structured
   `error` (code `AUDIO_OUT_OF_ORDER`) is emitted.
6. **Delayed inference results** — a late result whose sequence is older than
   the current committed sequence is dropped and counted.

---

## 6. Idempotency / Duplicate Handling

> These rules live here; the PRD states the requirement.

### 6.1 Audio

- Each audio frame is identified by
  `(session_id, stream_id, sequence_number)`.
- The buffer is keyed by that tuple; an already-seen sequence is a no-op insert.
- Re-delivery on client reconnect/replay is therefore safe.

### 6.2 Control Messages

- `stop` is idempotent: the second `stop` (or `stop` after `CLOSED`) is a
  no-op and does not error.
- `flush` may be issued repeatedly; it only commits what is currently pending.
- `ping` is always valid while the session is open.

### 6.3 Transcript Commits

- A commit is uniquely identified by its final `sequence`.
- Re-sending the same final `sequence` (e.g. detection-time retry) does not
  duplicate text in the client.

---

## 7. Flow Control and Backpressure

- The server consumes from a bounded `asyncio.Queue(maxsize=MAX_QUEUE_SIZE)`.
- When the queue is full, the server applies `QUEUE_OVERFLOW_POLICY`:
  - `drop` — reject the incoming frame, emit metric + `error` (code
    `QUEUE_OVERFLOW`, non-fatal);
  - `disconnect` — terminate the unhealthy session with a fatal error.
- Clients SHOULD stop sending when a `QUEUE_OVERFLOW` error arrives and resume
  on `session` health signal or after a backoff.

---

## 8. Session Lifecycle over the Wire

```text
TCP connect → WebSocket handshake
   ↓
[server] session_started {session_id}
   ↓
client sends binary audio frames (+ optional ping/flush)
   ↓
server streams transcript {is_final:false|true}
   ↓
client sends stop  (or server detects disconnect / limits)
   ↓
server commits finals, sends session_closed, closes WS
```

---

## 9. Error Codes

| Code                    | Fatal  | Meaning                                   |
| ----------------------- | ------ | ----------------------------------------- |
| `INVALID_FRAME`         | no     | Malformed binary audio frame              |
| `MESSAGE_TOO_LARGE`     | no     | Frame exceeds `MAX_MESSAGE_SIZE`          |
| `INVALID_SEQUENCE`      | no     | Missing or invalid frame sequence metadata |
| `RATE_MISMATCH`         | no     | Sample rate/channels outside contract     |
| `AUDIO_OUT_OF_ORDER`    | no     | Sequence disorder beyond tolerance        |
| `QUEUE_OVERFLOW`        | no*    | Backpressure policy triggered             |
| `INFERENCE_TIMEOUT`     | no     | Inference exceeded timeout                |
| `GPU_OOM`               | yes    | CUDA out-of-memory, session aborted       |
| `SESSION_LIMIT`         | yes*   | `MAX_CONCURRENT_SESSIONS` reached         |
| `INTERNAL_ERROR`        | fatal  | Unexpected failure                         |

\* Per `QUEUE_OVERFLOW_POLICY` / severity configuration.

---

## 10. Example Flows

### 10.1 Happy Path

```text
C→S: start
S→C: {"type":"session_started","session_id":"x1"}
C→S: <binary 1280 bytes> × n
S→C: {"type":"transcript","sequence":1,"text":"The quick","is_final":false,...}
S→C: {"type":"transcript","sequence":1,"text":"The quick brown","is_final":false,...}
S→C: {"type":"transcript","sequence":1,"text":"The quick brown fox.","is_final":true,...}
C→S: stop
S→C: {"type":"session_closed","session_id":"x1","reason":"client_stop"}
S→C: <WS close>
```

### 10.2 Backpressure

```text
C→S: <binary>       (server queue full)
S→C: {"type":"error","code":"QUEUE_OVERFLOW","fatal":false,...}
C→S: <binary>       (client backoff)
```

### 10.3 Duplicate Commit on Replay

```text
S→C: {"type":"transcript","sequence":5,"text":"hello world.","is_final":true,...}
# client applies once; a re-delivered sequence 5 final is a no-op
```
