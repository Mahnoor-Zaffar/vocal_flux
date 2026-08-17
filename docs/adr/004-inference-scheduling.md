# ADR-004: Inference Scheduling and Bounded Concurrency

**Status:** Accepted  
**Date:** 2026-08-16  

## Context

Whisper inference via CTranslate2 is CPU-blocking (from the event loop's
perspective) and GPU-latency-heavy. If every session fired inference
unconstrained, the loop could stall, GPU memory could blow, and queue memory
could grow without bound. The PRD requires explicit
`MAX_CONCURRENT_INFERENCES`, backpressure, and an observable policy
(PRD §17, §23).

## Decision

Schedule inference through a **single-worker gate**:

```text
event loop → per-session pipeline → asyncio.Queue(maxsize=N)
            → single inference worker task
            → bounded GPU concurrency (default 1)
           → asyncio.Semaphore(MAX_CONCURRENT_INFERENCES)
           → InferenceEngine → result
```

Expose `QUEUE_OVERFLOW_POLICY` (`drop` default; `disconnect` option) and
metrics for `queue_depth` and `queue_overflows`.

## Alternatives Considered

- **Unbounded background thread pool** — simple but allows unbounded GPU
  concurrency; violates boundedness principle.
- **asyncio.to_thread per window** — unbounded; same problem, plus no
  ordering/backpressure story.
- **External job queue (Redis)** — deferred, `adr/003`.
- **Reactive pull model only** — correct but more complex; V1 chooses a
  gate + bounded queue.

## Rationale

- A single default GPU worker matches the single-GPU deployment; a semaphore
  keeps concurrency explicit and configurable.
- The bounded queue localizes backpressure at a single choke point, protecting
  both memory and the loop.
- The design is observable: `queue_depth`, `queue_overflows`, `inference_*`
  metrics tell us when the gate saturates (mirrors benchmarking §4).

## Consequences

- A slow GPU propagates pressure back to clients as `QUEUE_OVERFLOW` /
  policy decisions rather than unbounded memory growth.
- At most `MAX_CONCURRENT_INFERENCES` GPU requests run at once; oversubscription
  is impossible by construction.
- `INFERENCE_TIMEOUT` with task cancellation keeps a hung GPU call from
  deadlocking the worker.

## Future Work

- Benchmark-driven tuning of `MAX_CONCURRENT_INFERENCES` (1 by default; see
  benchmarking §4 for saturation evidence).
- If multiple workers are justified later, move the queue to Redis with the
  `InferenceEngine` abstractions providing compatibility (`PRD §49`).