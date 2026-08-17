import argparse
import asyncio
import time
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.inference.lifecycle import ModelLifecycle
from app.inference.whisper import FasterWhisperEngine
from tests.benchmarks.benchmark_utils import (
    load_audio,
    percentile_summary,
    run_metadata,
    write_report,
)


async def benchmark_level(
    lifecycle: ModelLifecycle,
    audio: Any,
    streams: int,
) -> dict[str, Any]:
    started = time.monotonic_ns()

    async def run_one() -> float:
        call_started = time.monotonic_ns()
        await lifecycle.transcribe(audio)
        return (time.monotonic_ns() - call_started) / 1_000_000_000

    latencies = await asyncio.gather(*(run_one() for _ in range(streams)))
    wall_seconds = (time.monotonic_ns() - started) / 1_000_000_000
    audio_seconds = streams * len(audio) / 16_000
    return {
        "streams": streams,
        "wall_seconds": wall_seconds,
        "audio_seconds": audio_seconds,
        "throughput_audio_seconds": audio_seconds / wall_seconds,
        "latency_seconds": percentile_summary(list(latencies)),
        "rtf": percentile_summary(
            [latency / (len(audio) / 16_000) for latency in latencies]
        ),
    }


async def benchmark(args: argparse.Namespace) -> dict[str, Any]:
    audio = load_audio(Path(args.audio))
    settings = Settings(
        _env_file=None,
        whisper_model=args.model,
        whisper_device=args.device,
        whisper_compute_type=args.compute_type,
        whisper_language=args.language,
        whisper_beam_size=args.beam_size,
    )
    lifecycle = ModelLifecycle(
        FasterWhisperEngine(settings.whisper_config()),
        timeout_seconds=settings.inference_timeout,
    )
    await lifecycle.start()
    try:
        for _ in range(args.warmup):
            await lifecycle.transcribe(audio)
        levels = [int(value) for value in args.streams.split(",")]
        results = [
            await benchmark_level(lifecycle, audio, streams)
            for streams in levels
        ]
    finally:
        await lifecycle.close()

    return {
        **run_metadata(),
        "benchmark": "concurrency",
        "audio": str(args.audio),
        "audio_seconds": len(audio) / 16_000,
        "configuration": {
            "model": args.model,
            "device": args.device,
            "compute_type": args.compute_type,
            "language": args.language,
            "beam_size": args.beam_size,
        },
        "warmup_count": args.warmup,
        "run_count": 1,
        "levels": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark concurrent inference streams")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--language")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--streams", default="1,5,10,25,50")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    write_report(arguments.output, asyncio.run(benchmark(arguments)))
