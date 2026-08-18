import argparse
import asyncio
import re
import time
from pathlib import Path
from typing import Any

from jiwer import cer, wer

from app.core.config import Settings
from app.inference.lifecycle import ModelLifecycle
from app.inference.whisper import FasterWhisperEngine
from tests.benchmarks.benchmark_utils import (
    load_accuracy_manifest,
    load_audio,
    percentile_summary,
    run_metadata,
    write_report,
)

_PUNCTUATION = re.compile(r"[^\w\s]|_")
_WHITESPACE = re.compile(r"\s+")


def normalize_for_scoring(text: str) -> str:
    """Lowercase and strip punctuation so scoring matches docs/benchmarking.md 6.1."""
    lowered = text.lower()
    cleaned = _PUNCTUATION.sub(" ", lowered)
    return _WHITESPACE.sub(" ", cleaned).strip()


async def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = Path(args.manifest)
    manifest, samples = load_accuracy_manifest(manifest_path)
    if not samples:
        raise ValueError("Accuracy manifest contains no samples")

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
    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    try:
        for sample in samples:
            audio = load_audio(sample.audio_path)
            started = time.monotonic_ns()
            transcription = await lifecycle.transcribe(audio)
            latency_seconds = (time.monotonic_ns() - started) / 1_000_000_000
            latencies.append(latency_seconds)
            reference_norm = normalize_for_scoring(sample.reference)
            hypothesis_norm = normalize_for_scoring(transcription.text)
            results.append(
                {
                    "id": sample.sample_id,
                    "tags": sample.tags,
                    "audio_seconds": len(audio) / 16_000,
                    "latency_seconds": latency_seconds,
                    "rtf": latency_seconds / (len(audio) / 16_000),
                    "reference": sample.reference,
                    "hypothesis": transcription.text,
                    "wer": wer(reference_norm, hypothesis_norm),
                    "cer": cer(reference_norm, hypothesis_norm),
                }
            )
    finally:
        await lifecycle.close()

    return {
        **run_metadata(),
        "benchmark": "accuracy",
        "dataset": manifest,
        "configuration": {
            "model": args.model,
            "device": args.device,
            "compute_type": args.compute_type,
            "language": args.language,
            "beam_size": args.beam_size,
        },
        "warmup_count": 1,
        "run_count": 1,
        "latency_seconds": percentile_summary(latencies),
        "wer": sum(item["wer"] for item in results) / len(results),
        "cer": sum(item["cer"] for item in results) / len(results),
        "samples": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate VocalFlux WER/CER accuracy")
    parser.add_argument(
        "--manifest",
        default="tests/fixtures/accuracy/manifest.json",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--language")
    parser.add_argument("--beam-size", type=int, default=1)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        report = asyncio.run(evaluate(arguments))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    write_report(arguments.output, report)
