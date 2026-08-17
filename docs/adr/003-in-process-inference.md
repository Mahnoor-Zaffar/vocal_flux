# ADR-003: In-Process Inference

**Status:** Accepted  
**Date:** 2026-08-16  

## Context

VocalFlux must decide where Whisper inference runs relative to the FastAPI
process. Options range from a private in-process engine to a distributed
worker pool (Redis/Celery) behind a queue.

## Decision

Run inference **in-process** in a single GPU worker for V1, behind the
`InferenceEngine` abstraction, with a bounded concurrency gate
(`MAX_CONCURRENT_INFERENCES`).

## Alternatives Considered

- **Redis/Celery worker pool** — decouples but adds infrastructure,
  serialization, and latency; explicitly deferred in PRD §5 and §49.
- **Separate sidecar process on the same GPU** — two processes competing for
  one GPU; more deployment complexity for no V1 benefit.
- **Triton/remote inference service** — could be revisited for distributed
  routing, but overkill now.

## Rationale

- The target deployment is a **single ephemeral GPU**; a single in-process
  worker satisfies the concurrency requirement without distributed transport.
- In-process inference avoids serialization/network overhead per window,
  helping the sub-second latency goal.
- Simplicity keeps the V1 system understandable end-to-end (a stated project
  goal, see PRD §47).
- The `InferenceEngine` abstraction preserves the future option to route to
  remote workers without rewriting the streaming layer.

## Consequences

- CPU-blocking CTranslate2 calls must be gated and scheduled carefully so the
  asyncio loop stays responsive (`adr/004-inference-scheduling.md`).
- GPU memory and inference are shared across sessions in one process; hard
  limits are required (`MAX_CONCURRENT_INFERENCES`, `GPU` limits).
- Distributed scaling is **reserved until benchmarking demonstrates a
  bottleneck** (PRD principle 7, 11).

## Future Work

- When concurrency saturation is measured (docs/benchmarking.md §4), evolve to
  the Redis/Celery GPU worker pool shown in PRD §49.