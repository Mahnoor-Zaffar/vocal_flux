import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from app.core.config import Settings
from tests.benchmarks.benchmark_utils import (
    BENCH_CLIP_IDS,
    load_accuracy_manifest,
    load_audio,
    percentile_summary,
)
from tests.benchmarks.reporting import (
    FIRST_PARTIAL,
    WINDOW_FINAL,
    attribute_finals,
    render_latency_markdown,
    write_artifact,
    write_fragment,
)
from tests.benchmarks.service_harness import BenchmarkAbort, BenchmarkService, StreamSession

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark end to end window latency over live WebSocket sessions"
    )
    parser.add_argument("--model", default="small")
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--language")
    parser.add_argument("--beam-size", type=int, default=1)
    parser.add_argument("--warmup-sessions", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--output", type=Path, default=BACKEND_ROOT / "benchmark-results" / "latency-small.json"
    )
    return parser.parse_args()


async def run_session(service: BenchmarkService, name: str, clip_id: str, audio) -> StreamSession:
    session = StreamSession(service.ws_url, session_name=name, clip_id=clip_id, audio=audio)
    await session.run()
    return session


def window_final_events(
    session: StreamSession,
    clip_id: str,
    repeat: int,
    window_seconds: float,
    *,
    window_ms: float,
    overlap_ms: float,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    latencies = attribute_finals(
        session.finals,
        session.feed_timeline(),
        window_ms=window_ms,
        overlap_ms=overlap_ms,
    )
    for final, latency_seconds in zip(session.finals, latencies):
        events.append(
            {
                "repeat": repeat,
                "clip_id": clip_id,
                "event_type": WINDOW_FINAL,
                "window_index": final.get("sequence"),
                "audio_seconds": round(window_seconds, 3),
                "latency_seconds": round(latency_seconds, 6),
                "server_latency_seconds": round(final["latency_ms"] / 1_000, 6),
                "rtf": round(latency_seconds / window_seconds, 6)
                if window_seconds > 0
                else None,
                "stage_timings_ms": final["stage_timings_ms"],
            }
        )
    return events


async def benchmark(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = BACKEND_ROOT / "tests" / "fixtures" / "accuracy" / "manifest.json"
    manifest, samples = load_accuracy_manifest(manifest_path)
    by_id = {sample.sample_id: sample for sample in samples}
    missing = [clip_id for clip_id in BENCH_CLIP_IDS if clip_id not in by_id]
    if missing:
        raise BenchmarkAbort(f"corpus is missing frozen clips: {missing}")
    clips = [(clip_id, load_audio(by_id[clip_id].audio_path)) for clip_id in BENCH_CLIP_IDS]

    settings = Settings()
    window_seconds = float(settings.window_size_ms) / 1_000
    service = BenchmarkService(
        model=args.model,
        device=args.device,
        compute_type=args.compute_type,
        beam_size=args.beam_size,
        language=args.language,
    )
    events: list[dict[str, Any]] = []
    await service.start()
    try:
        for warmup_index in range(args.warmup_sessions):
            clip_id, audio = clips[0]
            await run_session(service, f"warmup-{warmup_index}", clip_id, audio)
        for repeat in range(1, args.repeats + 1):
            for clip_id, audio in clips:
                session = await run_session(service, f"r{repeat}-{clip_id}", clip_id, audio)
                events.extend(
                    window_final_events(
                        session,
                        clip_id,
                        repeat,
                        window_seconds,
                        window_ms=float(settings.window_size_ms),
                        overlap_ms=float(settings.overlap_ms),
                    )
                )
                first_text_ns = session.first_text_ns
                if first_text_ns is not None:
                    events.append(
                        {
                            "repeat": repeat,
                            "clip_id": clip_id,
                            "event_type": FIRST_PARTIAL,
                            "latency_seconds": round(
                                (first_text_ns - session.started_ns) / 1e9, 6
                            ),
                            "rtf": None,
                        }
                    )
    finally:
        await service.close()

    summary = {
        kind: percentile_summary(
            [event["latency_seconds"] for event in events if event["event_type"] == kind]
        )
        for kind in (WINDOW_FINAL, FIRST_PARTIAL)
    }
    summary["rtf"] = percentile_summary(
        [
            event["rtf"]
            for event in events
            if event["event_type"] == WINDOW_FINAL and event["rtf"] is not None
        ]
    )
    return {
        **benchmark_envelope(args, service),
        "corpus": {"manifest_version": manifest.get("version"), "sample_ids": list(BENCH_CLIP_IDS)},
        "events": events,
        "summary": summary,
    }


def benchmark_envelope(args: argparse.Namespace, service: BenchmarkService) -> dict[str, Any]:
    settings = Settings()
    return {
        "configuration": {
            "model": args.model,
            "device": args.device,
            "compute_type": args.compute_type,
            "language": args.language,
            "beam_size": args.beam_size,
        },
        "service_env": {
            "max_concurrent_sessions": service.max_concurrent_sessions,
            "window_seconds": round(float(settings.window_size_ms) / 1_000, 3),
            "overlap_seconds": round(float(settings.overlap_ms) / 1_000, 3),
        },
        "warmup_sessions": args.warmup_sessions,
        "repeats": args.repeats,
    }


def main() -> int:
    args = parse_args()
    try:
        report = asyncio.run(benchmark(args))
    except BenchmarkAbort as error:
        print(f"Benchmark aborted: {error}", file=sys.stderr)
        return 1
    output: Path = args.output
    write_artifact(output, report)
    fragment_path = output.with_suffix(".md")
    write_fragment(fragment_path, render_latency_markdown(report))
    print(f"Wrote latency artifact to {output}")
    print(f"Wrote markdown fragment to {fragment_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
