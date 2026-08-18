# Frontend

## Overview

A deliberately thin Next.js app. It captures microphone audio with the Web Audio API (AudioWorklet), streams binary PCM16 frames over a WebSocket to the backend, and renders incremental transcript state plus performance metrics. The smart part lives in the backend.

## Key files

| File | Owns |
|---|---|
| hooks/useTranscription.ts | WebSocket session client and transcript state |
| hooks/useRecorder.ts | Microphone capture with the AudioWorklet processor |
| lib/audio.ts | PCM16 encode helpers and chunk sizing |
| lib/websocket.ts | WebSocket URL construction |
| lib/protocol.ts | Wire message types shared with the backend protocol |
| public/audio-processor.js | AudioWorklet processor that emits frames |
| components/ | Recorder, transcript, metrics, status UI |
| types/transcription.ts | TypeScript types for transcripts and events |

## Commands

```bash
cd frontend
pnpm install
pnpm dev
pnpm lint
pnpm typecheck
```

## Conventions

- The frontend stays thin; no business logic beyond capture, stream, and render.
- Frames are binary PCM16, 16 kHz mono; each chunk sizes to about 683 samples (42.7 ms) for low latency.
- The WebSocket client sends binary frames plus JSON control messages; metadata frames carry capture_started_ms and sequence numbers, and missing sequences surface as errors in the UI.
- UI is React with Tailwind; visualizer and metrics show live state.
- Types live in types/ and protocol wording mirrors docs/protocol.md.

## Gotchas

- The AudioWorklet processor runs off the main thread; message batching affects chunk size, keep chunk duration short.
- A hard refresh clears a stale session after a backend restart; the client reconnects on demand, not automatically.
- capture_started_ms must be an integer millisecond value, the backend schema rejects floats.

## Agent skills

- [vercel-react-best-practices](.agents/skills/vercel-react-best-practices/): vercel-labs/agent-skills, official React best practices
- [nextjs-app-router-patterns](.agents/skills/nextjs-app-router-patterns/): wshobson/agents, Next.js App Router conventions
- [tailwind-design-system](.agents/skills/tailwind-design-system/): wshobson/agents, Tailwind design system architecture
- [pnpm](.agents/skills/pnpm/): antfu/skills, pnpm install and workspace idioms

## Related specs