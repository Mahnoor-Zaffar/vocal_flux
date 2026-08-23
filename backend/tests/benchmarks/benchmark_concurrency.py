import argparse
import asyncio
import sys
import time
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
    FIRST_TEXT,
    WINDOW_FINAL,
    count_errors,
    evaluate_saturation,
    load_average,
    render_concurrency_markdown,
    write_artifact,
    write_fragment,
)
from tests.benchmarks.service_harness import (
    SAMPLE_RATE,
    BenchmarkAbort,
    BenchmarkService,
    StreamSession,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark concurrent streaming sessions against the live service"
    )
    parser.add_argument("--model", default="small")
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--language")
    parser.add_argument("--beam-size", type=int, default=1)
    parser.add_argument("--warmup-sessions", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--streams", default="1,5,10,25,50")
    parser.add_argument(
        "--output",
        type=Path,
        default=BACKEND_ROOT / "benchmark-results" / "concurrency-small.json",
    )
    return parser.parse_args()


async def run_level(
    service: BenchmarkService,
    clips: list[tuple[str, Any]],
    streams: int,
    repeat: int,
) -> tuple[float, list[StreamSession]]:
    sessions = [
        StreamSession(
            service.ws_url,
            session_name=f"l{streams}-r{repeat}-s{index}",
            clip_id=clips[index % len(clips)][0],
            audio=clips[index % len(clips)][1],
        )
        for index in range(streams)
    ]
    started_ns = time.monotonic_ns()
    await asyncio.gather(*(session.run() for session in sessions))
    wall_seconds = (time.monotonic_ns() - started_ns) / 1e9
    return wall_seconds, sessions


async def run_warmups(service: BenchmarkService, clips: list[tuple[str, Any]], count: int) -> None:
    clip_id, audio = clips[0]
    for warmup_index in range(count):
        session = StreamSession(
            service.ws_url,
            session_name=f"warmup-{warmup_index}",
            clip_id=clip_id,
            audio=audio,
        )
        await session.run()


def level_report(
    *,
    streams: int,
    sessions: list[StreamSession],
    wall_seconds: float,
    window_seconds: float,
    clip_audio_seconds: float,
    repeats: int,
    load_before: list[float] | None,
    load_after: list[float] | None,
) -> dict[str, Any]:
    window_final_latencies: list[float] = []
    first_text_latencies: list[float] = []
    rtf_values: list[float] = []
    dropped_frames = 0
    frames_sent = 0
    error_codes: list[str] = []
    session_rollups: list[dict[str, Any]] = []

    for session in sessions:
        latencies = [final["latency_ms"] / 1_000 for final in session.finals]
        window_final_latencies.extend(latencies)
        if window_seconds > 0:
            rtf_values.extend(latency / window_seconds for latency in latencies)
        first_text_ns = session.first_text_ns
        if first_text_ns is not None:
            first_text_latencies.append((first_text_ns - session.started_ns) / 1e9)
        dropped_frames += session.dropped_frames
        frames_sent += session.frames_sent
        error_codes.extend(session.error_codes)
        rollup_summary = percentile_summary(latencies)
        session_rollups.append(
            {
                "session_id": session.session_name,
                "clip_ids": [session.clip_id],
                "windows_completed": len(session.finals),
                "dropped_frames": session.dropped_frames,
                "p50": rollup_summary["p50"] if latencies else None,
                "p95": rollup_summary["p95"] if latencies else None,
            }
        )

    total_audio_seconds = clip_audio_seconds * streams * repeats
    return {
        "streams": streams,
        "wall_seconds": round(wall_seconds, 3),
        "audio_seconds_total": round(total_audio_seconds, 3),
        "throughput_audio_seconds": round(
            total_audio_seconds / wall_seconds if wall_seconds else 0.0, 3
        ),
        "dropped_frames": dropped_frames,
        "drop_rate": round(dropped_frames / max(frames_sent, 1), 6),
        "errors": count_errors(error_codes),
        WINDOW_FINAL: percentile_summary(window_final_latencies),
        FIRST_TEXT: percentile_summary(first_text_latencies),
        "rtf": percentile_summary(rtf_values),
        "loadavg_before_after": [load_before, load_after],
        "sessions": session_rollups,
    }


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
    levels = [int(value) for value in args.streams.split(",")]
    top_level = max(levels)

    service = BenchmarkService(
        model=args.model,
        device=args.device,
        compute_type=args.compute_type,
        beam_size=args.beam_size,
        language=args.language,
        max_concurrent_sessions=max(64, top_level + 10),
    )
    level_reports: list[dict[str, Any]] = []
    await service.start()
    try:
        await run_warmups(service, clips, args.warmup_sessions)
        for streams in levels:
            collected: list[StreamSession] = []
            total_wall_seconds = 0.0
            load_before = load_average()
            for repeat in range(1, args.repeats + 1):
                wall_seconds, sessions = await run_level(service, clips, streams, repeat)
                total_wall_seconds += wall_seconds
                collected.extend(sessions)
            load_after = load_average()
            clip_audio_seconds = sum(len(audio) for _, audio in clips) / SAMPLE_RATE
            level_reports.append(
                level_report(
                    streams=streams,
                    sessions=collected,
                    wall_seconds=total_wall_seconds,
                    window_seconds=window_seconds,
                    clip_audio_seconds=clip_audio_seconds,
                    repeats=args.repeats,
                    load_before=load_before,
                    load_after=load_after,
                )
            )
    finally:
        await service.close()

    report = {
        **benchmark_envelope(args, service),
        "corpus": {"manifest_version": manifest.get("version"), "sample_ids": list(BENCH_CLIP_IDS)},
        "levels": level_reports,
        "saturation": evaluate_saturation(level_reports, window_seconds),
    }
    return report


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
    write_fragment(fragment_path, render_concurrency_markdown(report))
    print(f"Wrote concurrency artifact to {output}")
    print(f"Wrote markdown fragment to {fragment_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
