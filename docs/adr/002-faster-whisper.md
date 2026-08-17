# ADR-002: faster-whisper as the Inference Runtime

**Status:** Accepted  
**Date:** 2026-08-16  

## Context

VocalFlux must run Whisper-style transcription at low latency with bounded,
controllable GPU usage from a single Python process. The reference OpenAI
`whisper` implementation is pure PyTorch and slower to run without
optimizations; we need an efficiently compiled runtime.

## Decision

Use **faster-whisper** (CTranslate2 backend) as the default inference runtime,
with int8/float16 compute type options.

## Alternatives Considered

- **OpenAI `whisper` (PyTorch)** — simplest Python API but higher latency and
  memory; no native quantization.
- **Whisper.cpp** — fast and portable but C-based, awkward to embed in a
  FastAPI process for our abstractions.
- **ONNX Runtime (whisper exporter)** — possible but extra conversion/maintenance
  cost, smaller convenience ecosystem for streaming.
- **Custom Triton server** — overkill for a single-worker V1.

## Rationale

- faster-whisper exposes the same model sizes with CTranslate2's optimized,
  quantized kernels, giving a large latency/throughput win on CPU and GPU.
- It runs in-process, which matches `adr/003-in-process-inference.md`.
- Fit with the V1 performance goals (sub-second first result, RTF < 1).
- Python-native, integrates cleanly behind our `InferenceEngine` abstraction.

## Consequences

- Dependencies on `faster-whisper` and `ctranslate2` become part of the
  container image (verify licenses and pinned versions).
- Quantization tradeoffs (int8 vs float16 vs float32) must be benchmarked
  (see `docs/benchmarking.md`, Experiment Set C).
- The engine abstraction (`app/inference/`) isolates us from this choice; a
  `MockInferenceEngine` enables tests without the model.

## Future Work

- If accuracy/RTF needs diverge, swap the engine behind the same interface
  (`adr/002` does not preclude it).