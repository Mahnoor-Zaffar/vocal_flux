# VocalFlux

## Stack

- **Backend**: Python 3.13, FastAPI, uvicorn, faster-whisper (CTranslate2)
- **Frontend**: TypeScript, Next.js 15 (App Router), React 19, Tailwind CSS
- **Key dependencies**: faster-whisper, ctranslate2, av, numpy (backend); next, react, tailwindcss (frontend)
- **Package managers**: uv (backend), pnpm (frontend)

## Build approach

Tracer Bullet (vertical slices, each feature built end to end and working before the next starts)

## Commands

```bash
# Backend install and sync
cd backend && uv sync

# Backend dev server (local)
cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Backend tests and lint
cd backend && uv run pytest && uv run ruff check

# Frontend dev
cd frontend && pnpm dev

# Frontend checks
cd frontend && pnpm lint && pnpm typecheck
```

## Specs

Stored in `docs/specs/`. Format: `docs/specs/NNNN-title.md`.

## Rules

- The backend is the primary artifact; the frontend stays thin and only captures audio, streams frames, and renders transcripts and metrics.
- Audio moves as binary PCM16 frames, 16 kHz mono, over a WebSocket, each with strict metadata and a sequence number; validation rejects anything incomplete.
- The pipeline is bounded: VAD gates what enters the buffer, windows are capped (4 s default), and the asyncio queue drops frames rather than blocking a session.
- Never run blocking work on the event loop; the engine transcribes in a thread.
- Model readiness is owned by the lifecycle, and a degraded state recovers with a warmup probe, it is not permanent.
- Configuration comes from environment through pydantic settings; a real value wins over a default.
- The service stays CPU first for local dev; GPU is opt in for demo environments.
- Docs that ground every design decision: docs/architecture.md, docs/protocol.md, docs/threat-model.md and the ADRs.

## Agent skills

- [audit](.agents/skills/audit/): bootstrap and refresh agent context (this skill)
- [architect](.agents/skills/architect/): load bearing design decisions and build specs
- [scope](.agents/skills/scope/): product scope in docs/scope/
- [develop](.agents/skills/develop/): build features from approved specs
- [check](.agents/skills/check/): verify behavior and review before merge
- [debug](.agents/skills/debug/): root cause a failing test or behavior
- [test](.agents/skills/test/): write tests for a change
- [document](.agents/skills/document/): PR, changelog, and release notes
- [sync](.agents/skills/sync/): keep context and scope current
- Area skills live in the nested docs below.
MCP servers: runpod/runpod-mcp (recommended), bitfarer/whisper-mcp (recommended)

## Context files

<!-- Nested AGENTS.md files are listed here as they are created -->
- [backend/AGENTS.md](backend/AGENTS.md): backend stack, commands, and pipeline conventions
- [frontend/AGENTS.md](frontend/AGENTS.md): frontend stack, commands, and capture conventions

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._