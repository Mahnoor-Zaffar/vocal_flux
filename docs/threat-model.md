# VocalFlux Threat Model

**Status:** Draft v1  
**Scope:** Security posture for a public demo ASR service

---

## 1. Scope and Posture

VocalFlux is a portfolio / demo service, not a production SaaS. V1 explicitly
excludes accounts, auth, billing, and multi-tenant dashboards (PRD §5). The
security posture is therefore **"public demo with defensive hardening"**:

- The service must not crash on hostile input.
- The service must resist resource-exhaustion abuse.
- The service carries **no** secrets and **no** user PII beyond ephemeral
  audio/transcripts held only in memory for the session.
- Any unexpected persistence of transcripts in V1 is prohibited (non-goal).

Threat model is performed against that posture. Controls are centralized in
`app/core/config.py` limits and enforced server-side.

---

## 2. Assets

| Asset                 | Sensitivity | Notes                                  |
| --------------------- | ----------- | -------------------------------------- |
| Microphone audio      | High        | Captured in-memory, session-scoped only |
| Transcripts           | Medium      | Ephemeral; committed only to WS client  |
| GPU / compute         | Medium      | Expensive resource, abuse target        |
| Process / container   | Medium      | Escape → GPU meter + host exposure      |
| Logs                  | Low-Medium  | Must NOT log full transcript text       |

---

## 3. Threats and Controls

### 3.0 Required Boundary Controls

The V1 service must enforce the following controls at the HTTP/WebSocket
boundary and in the streaming pipeline:

- Maximum message size
- Maximum session duration
- Maximum concurrent connections
- Rate limiting
- WebSocket origin policy
- Input validation
- GPU resource limits
- CORS policy

These controls are configuration-backed, observable, and enforced server-side.
They are requirements even though V1 does not include user accounts or
authentication.

### T1 — Unauthenticated resource consumption (compute abuse)

**Threat:** Attacker opens many WebSockets / streams garbage audio to consume
GPU, memory, bandwidth.

**Controls:**
- `MAX_CONCURRENT_SESSIONS` (reject with `SESSION_LIMIT`)
- `MAX_SESSION_DURATION` (enforced server-side)
- `MAX_MESSAGE_SIZE`, `MAX_AUDIO_BUFFER`, `MAX_QUEUE_SIZE`
- Backpressure `QUEUE_OVERFLOW_POLICY`
- Rate limiting at the gateway or application middleware
- WebSocket origin allowlist and explicit CORS allowlist

### T2 — Malformed / hostile binary input

**Threat:** Truncated PCM, huge frames, wrong sample rate, binary URL trick,
NaN/Inf sample abuse via crafted bytes.

**Controls:**
- Validation stage before decode (size, encoding, rate, channels, sequence)
- Bounded decode (reject oversize, cap sample count)
- Float sanity clamp in Normalization
- Structured `error`, never an uncaught exception
- Invalid input must not crash the service (PRD §15)

### T3 — Out-of-order / replay / duplicate injection

**Threat:** Injecting stale or duplicate frames to confuse ordering or force
duplicate commits.

**Controls:**
- Backend is the sequence authority (`protocol.md §5`)
- Duplicate `(session, seq)` is a no-op
- Out-of-order beyond tolerance → structured drop + metric
- Transcript dedupe by final `sequence`

### T4 — WebSocket resource / lifespan abuse

**Threat:** Slowloris-style long-open idle sockets; ping floods; never closing.

**Controls:**
- `ping`/`pong` keepalive with server-side liveness timeout
- Idle session timeout
- `MAX_SESSION_DURATION`
- Graceful cancellation on disconnect (`architecture.md §6`)

### T5 — SSRF / external request abuse

**Threat:** A vector forcing the server to fetch from an attacker-controlled
URL (e.g. if model download or any HTTP client logic is reachable by input).

**Controls:**
- No user input ever reaches a URL/fetch path in V1 (no such feature)
- Model download is build-time/first-run, pinned and off the request path

### T6 — Information disclosure via errors/logs

**Threat:** Detailed stack traces or full transcripts leaking to clients or logs.

**Controls:**
- Client receives structured error `code`+`message`, never a stack trace
- Logging redacts transcript text (log event metadata, not content)
- `structlog` config suppresses full payloads

### T7 — GPU / compute denial by heavy inference

**Threat:** Streaming crafted high-entropy audio at max speed to pin the GPU.

**Controls:**
- Single inference worker, `MAX_CONCURRENT_INFERENCES` (default 1)
- `INFERENCE_TIMEOUT` + cancellation
- VAD reduces inference count on silence (also a cost control)
- Backpressure gates input when the GPU is the bottleneck

### T8 — Container / host compromise

**Threat:** Escape via native GPU libs (CTranslate2/ONNX runtime) or a
vulnerable dependency.

**Controls:**
- Run as non-root user in the container where possible
- Read-only root filesystem where practical
- Pinned, reproducible dependency versions (deterministic install)
- Optional: drop network egress after startup (block model download at runtime)

### T9 — Dependency / supply chain

**Threat:** Compromised PyPI package planted in the image.

**Controls:**
- Locked dependencies (`uv.lock` / `requirements.lock`)
- `pip-audit` / OSV scan in CI as a quality gate

### T10 — Upstream model runtime

**Threat:** Malicious ONNX/CT2 artifacts.

**Controls:**
- Model weights pulled from pinned, known-good sources (HF hub Identifiers
  pinned by SHA where supported) at build/run init, not per request.

---

## 4. Data Handling

| Data            | Lifetime                      | Location            |
| --------------- | ----------------------------- | ------------------- |
| Audio frames    | Session duration              | In-memory buffer    |
| Transcripts     | Session duration              | In-memory state     |
| Metrics         | Process lifetime (or scrape)  | Prometheus counters |
| Logs            | Process/9x rotation           | stdout               |

No disk persistence of audio or transcripts in V1. No secret storage.
Connection tokens: none (no auth in V1).

---

## 5. Deployment Considerations

- `docker-compose.yml` binds the app port to a controlled interface, never
  exposes Docker sockets or GPU host paths.
- Extelposed `/metrics` + `/health` are read-only, low-risk endpoints.
- In the ephemeral GPU demo (RunPod), the container should:
  - not run as root
  - set restrictive `ulimits`
  - inherit no host secrets
- Optional front-end TLS (reverse proxy) terminates; backend sees HTTP/WS only.

---

## 6. Assumptions and Residual Risks

| Assumption / risk                        | Notes                                        |
| ---------------------------------------- | -------------------------------------------- |
| No user authentication in V1             | Accepted; demo posture, documented           |
| CPU attacker same-box as GPU worker      | Single physical node per config              |
| Transcript remains ephemeral             | If persistence added later, re-evaluate T6   |
| Third-party model/runtime trusted        | Mitigated by pinning; residual accepted      |

---

## 7. Testing Security Controls

- Fuzz-ish unit tests: truncated frames, oversized frames, NaN bytes,
  out-of-order sequences, duplicates, oversize websocket text.
- Backpressure/limit tests assert `SESSION_LIMIT`, `QUEUE_OVERFLOW`,
  `MAX_SESSION_DURATION` enforcement.
- Health endpoints assert process-alive vs inference-ready separation.
