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


async def benchmark(args: argparse.Namespace) -> dict[str, Any]:
    audio_path = Path(args.audio)
    audio = load_audio(audio_path)
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
        latencies: list[float] = []
        rtfs: list[float] = []
        for _ in range(args.runs):
            started = time.monotonic_ns()
            await lifecycle.transcribe(audio)
            latency = (time.monotonic_ns() - started) / 1_000_000_000
            latencies.append(latency)
            rtfs.append(latency / (len(audio) / 16_000))
    finally:
        await lifecycle.close()

    return {
        **run_metadata(),
        "benchmark": "latency",
        "audio": str(audio_path),
        "audio_seconds": len(audio) / 16_000,
        "configuration": {
            "model": args.model,
            "device": args.device,
            "compute_type": args.compute_type,
            "language": args.language,
            "beam_size": args.beam_size,
        },
        "warmup_count": args.warmup,
        "run_count": args.runs,
        "latency_seconds": percentile_summary(latencies),
        "rtf": percentile_summary(rtfs),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark single-stream inference latency")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--language")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=5)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    write_report(arguments.output, asyncio.run(benchmark(arguments)))
