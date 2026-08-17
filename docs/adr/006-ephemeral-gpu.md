# ADR-006: Ephemeral GPU Deployment

**Status:** Accepted  
**Date:** 2026-08-16  

## Context

VocalFlux is a portfolio system whose GPU requirements only matter during
demonstrations, benchmarking, and GPU development (PRD §41). Standing up
permanent GPU infrastructure is unjustified. We need a reproducible path from
the repo to a running GPU-backed service, locally and on a rented GPU.

## Decision

Deploy via **container image + Docker Compose**, and for remote demos use an
**ephemeral GPU instance** (RunPod) launched on demand:

```text
GitHub ──► GitHub Actions ──► Container Image ──► RunPod ──► GPU ──► VocalFlux
```

Local development runs the same image with `docker compose up` (OrbStack on
macOS). GPU is provisioned only when needed.

## Alternatives Considered

- **Long-lived GPU VM / always-on inference host** — expensive, unnecessary for
  a demo cadence.
- **Serverless GPU (Modal/RunPod serverless, Cloud Run GPU)** — viable later;
  V1 uses a simple pod/instance to keep networking + WebSockets trivial.
- **Kubernetes + autoscaling** — explicitly non-goal for V1 (PRD §5).

## Rationale

- A single container defined in the repo is reproducible anywhere: `compose
  up` locally, same image on a GPU pod remotely.
- WebSockets over a public pod port are trivial to expose; serverless GPU
  ingress/websocket handling adds latency and plumbing that V1 does not need.
- Cost matches usage: pay for GPU only for the demo/benchmark window.

## Consequences

- The container must be self-contained: bundle config via env vars, download
  model at init (or bake pinned weights), health checks defined, GPU optional
  (CPU fallback via config).
- Shutdown lifecycle (PRD §42) must be honored so the rented GPU is released
  promptly: stop accepting sessions, drain, terminate.
- Public exposure lowers trust boundary → hardening rules from `threat-model.md`
  apply (limits, no secrets, ephemeral audio).

## Future Work

- If sustained demand emerges, migrate to serverless GPU or managed inference
  endpooints while keeping the same container + `InferenceEngine` contract.