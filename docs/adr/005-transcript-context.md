# ADR-005: Transcript Context Strategy

**Status:** Accepted  
**Date:** 2026-08-16  

## Context

Whisper is window-based; naively transcribing consecutive 1–2 s windows
independently produces repeated words, dropped context, and inconsistent
punctuation at boundaries (PRD §20). VocalFlux must maintain context across
windows and select a documented strategy.

## Decision

Use a **Hybrid context strategy** (Strategy C) as the V1 default:

```text
window_input = (recent audio overlap)
             + (recent committed transcript as prompt, when the engine supports it)
```

with configurable `OVERLAP_MS` (default 300) and prompt length.

## Alternatives Considered

- **Strategy A: Previous-Transcript Prompt** — pass recent committed text as
  decoding context. Cheap, but without audio overlap boundary words can still
  be repeated/stuttered.
- **Strategy B: Overlapping Windows** — include `OVERLAP_MS` of prior audio in
  the next window. Fixes boundary continuity; adds compute per window.
- **Strategy C: Hybrid (A + B)** — audio overlap across the boundary plus
  committed transcript as a conditioning prompt.

> The PRD requires benchmarking before finalizing; both A and B are compared
> in Experiment Set B (`docs/benchmarking.md §7`) and the winning parameters
> committed here subsequently.

## Rationale

- Hybrid directly addresses the two failure modes (boundary repeats and lost
  context) at modest extra compute.
- The transcript-state model (partial vs committed) feeds the committed-prompt
  cleanly: only stable text is ever used as context, never unstable hypotheses.
- Configurability (`OVERLAP_MS`, context window) lets experiments tune the
  cost/accuracy point per PRD §19 tradeoff.

## Consequences

- Slightly higher inference cost per window because of overlap.
- Context must be reset for windows when VAD segment boundaries are absolute
  (to avoid carrying prompt from unrelated sentences) — part of the VAD
  segment lifecycle.
- If benchmarking shows overlap cost dominates with no accuracy gain, the
  strategy can downgrade to A with configuration only.

## Future Work

- Longer-term: cross-segment language model conditioning or diarization-aware
  context (PRD §49) once V1 metrics justify it.