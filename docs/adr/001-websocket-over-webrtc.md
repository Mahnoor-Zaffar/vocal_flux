# ADR-001: WebSocket over WebRTC

**Status:** Accepted  
**Date:** 2026-08-16  

## Context

VocalFlux needs to stream browser microphone audio to a backend in near
real-time. Two candidate transports exist: **WebRTC** (peer-to-peer media
channels with SRTP) and **WebSocket** (message-based full-duplex TCP).

## Decision

Use a **binary WebSocket** transport at `/ws/v1/transcribe`.

## Alternatives Considered

- **WebRTC DataChannels / MediaStream** — built-in low-latency media transport
  with congestion control in the browser.
- **HTTP chunked/fetch streaming** — request/response only; no server push.
- **Server-Sent Events (SSE)** — one-way.

## Rationale

- The core engineering goal is a **streaming ASR pipeline**, not a media
  transport problem. WebSocket gives raw full-duplex binary framing with
  minimal browser/backend friction.
- We standardize the audio contract ourselves (PCM16/16kHz/mono) so we do not
  need WebRTC's codec/negotiation machinery.
- Simpler to test, instrument, and reason about: one persistent socket, pure
  bytes in, JSON events out.
- WebRTC requires SDP/ICE signaling infrastructure and codec handling that
  adds significant complexity to a single-worker V1.

## Consequences

- We are responsible for jitter/buffering/ordering at the application layer
  (addressed in `architecture.md` and `protocol.md`).
- No adaptive bitrate control from the transport; clients should use fixed
  PCM chunking and the backend applies backpressure via the bounded queue.
- WebSockets are well-suited to the single-node demo deployment.

## Future Work

- If bitrate adaptivity, DTX, or browser-native AEC become requirements,
  revisit WebRTC (see PRD §49 future capabilities).