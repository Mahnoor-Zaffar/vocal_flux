# Backend

## Overview

The primary engineering artifact. A FastAPI app (app/main.py) that wires a FasterWhisperEngine, a ModelLifecycle, and a SessionManager behind a WebSocket route at /ws/v1/transcribe. Browser audio streams in, is decoded, normalized, gated by VAD, windowed, transcribed by faster-whisper, and partial or final text pushes back to the browser.

## Key files

| File | Owns |
|---|---|
| app/main.py | App factory and wiring of engine, lifecycle, manager |
| app/streaming/manager.py | Session lifecycle, capacity gate, origin allowlist |
| app/streaming/session.py | Per session state machine and processing loop |
| app/streaming/pipeline.py | Decode, normalize, VAD, window, transcribe stages |
| app/audio/vad.py | Energy VAD by default, Silero is optional |
| app/audio/window.py | Fixed size windows with overlap |
| app/inference/lifecycle.py | Model readiness, scaled timeouts, degraded recovery |
| app/api/websocket.py | WebSocket route and the wire envelope |
| app/transcript/ | Transcript assembly and partial and final states |
| app/core/config.py | pydantic settings driven by environment |

## Commands

```bash
cd backend
uv sync
uv run pytest
uv run ruff check
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Conventions

- Blocking work leaves the event loop, run it with asyncio.to_thread.
- Every frame carries full metadata and a sequence number; validation rejects partial frames.
- Windows are bounded (4 s default) and inference concurrency is gated by the session manager.
- Tests split into unit, integration, model, and benchmarks; pytest runs in asyncio auto mode and the bench scripts live in tests/benchmarks.
- Logging uses structlog, metrics use prometheus_client.
- Dependencies are pinned in uv.lock; the dev group carries locust, jiwer, and soundfile for load and accuracy checks.

## Gotchas

- A slow inference marks the model degraded briefly; a background warmup probe restores readiness, so do not treat degraded as fatal.
- Queue overflow drops frames instead of killing the session, and the client learns about missing sequences.
- Windowing emits a window as soon as the buffer holds the target size, even mid speech; silence frames the VAD does not call speech never enter the buffer, so a transcript can skip short non speech audio.
- FasterWhisperEngine.warmup runs a real inference over one second of silence, expect a small delay when the model recovers.

## Agent skills

- [fastapi](.agents/skills/fastapi/): fastapi/fastapi, official FastAPI patterns
- [websocket-engineer](.agents/skills/websocket-engineer/): jeffallan/claude-skills, WebSocket lifecycle and backpressure
- [faster-whisper](.agents/skills/faster-whisper/): theplasmak/faster-whisper, CTranslate2 transcription patterns
- [pytest-coverage](.agents/skills/pytest-coverage/): github/awesome-copilot, pytest coverage discipline
- [ruff-recursive-fix](.agents/skills/ruff-recursive-fix/): github/awesome-copilot, ruff auto fixing workflow

## Related specs