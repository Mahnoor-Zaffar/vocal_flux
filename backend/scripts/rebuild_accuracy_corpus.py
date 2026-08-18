"""Rebuild the committed LibriSpeech test clean accuracy corpus.

This tool re creates the 20 clip fixture corpus deterministically from a local
copy of the LibriSpeech test clean archive. The committed clips are the source
of truth; this script is the documented way to reproduce them byte for byte.

The archive itself is not committed. Download it once (network needed only
here, at build time), pass its path, and the script re encodes the frozen clip
list into 16 kHz mono WAV files next to the manifest. The archive checksum is
pinned, so a changed archive fails loudly instead of silently changing the
corpus.

Usage:
    uv run python scripts/rebuild_accuracy_corpus.py \
        --archive /path/to/test-clean.tar.gz \
        --output tests/fixtures/accuracy
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import soundfile as sf

SOURCE_URL = "https://www.openslr.org/resources/12/test-clean.tar.gz"
SOURCE_SHA256 = "39fde525e59672dc6d1551919b1478f724438a95aa55f874b576be21967e6c23"
LICENSE = "CC BY 4.0"

# Frozen clip selection: one clip per speaker, chosen from LibriSpeech test clean.
# Spread covers 20 different speakers, utterance lengths from about 4 to 13
# seconds, and both long and short ground truth transcripts.
CLIP_IDS = (
    "1089-134691-0006",
    "1221-135767-0021",
    "1580-141084-0003",
    "1995-1837-0029",
    "2094-142345-0027",
    "2961-961-0007",
    "3570-5696-0009",
    "4077-13751-0009",
    "4507-16021-0033",
    "4992-41797-0010",
    "5105-28241-0012",
    "5639-40744-0036",
    "61-70970-0013",
    "6829-68771-0014",
    "7021-79740-0007",
    "7127-75947-0007",
    "7176-92135-0005",
    "7729-102255-0042",
    "8455-210777-0018",
    "8463-294828-0029",
)

MANIFEST = {
    "version": 1,
    "sample_rate": 16_000,
    "channels": 1,
}


def clip_path(archive: tarfile.TarFile, clip_id: str) -> tarfile.TarInfo | None:
    speaker, book, _ = clip_id.split("-", 2)
    name = f"LibriSpeech/test-clean/{speaker}/{book}/{clip_id}.flac"
    try:
        return archive.getmember(name)
    except KeyError:
        return None


def transcript_for(archive: tarfile.TarFile, clip_id: str) -> str | None:
    speaker, book, _ = clip_id.split("-", 2)
    name = f"LibriSpeech/test-clean/{speaker}/{book}/{speaker}-{book}.trans.txt"
    try:
        member = archive.getmember(name)
    except KeyError:
        return None
    lines = archive.extractfile(member).read().decode("utf-8").splitlines()
    for line in lines:
        line_id, text = line.split(" ", 1)
        if line_id == clip_id:
            return text
    return None


def reencode_wav(
    archive: tarfile.TarFile, clip_id: str, output: Path
) -> tuple[Path, float]:
    member = clip_path(archive, clip_id)
    if member is None:
        raise FileNotFoundError(f"clip {clip_id} not in archive")
    raw, sample_rate = sf.read(archive.extractfile(member), dtype="float32", always_2d=False)
    if sample_rate != 16_000:
        raise ValueError(f"{clip_id} is {sample_rate} Hz, expected 16000 Hz")
    if raw.ndim != 1:
        raise ValueError(f"{clip_id} is not mono")
    target = output / f"{clip_id}.wav"
    sf.write(
        target,
        np.ascontiguousarray(raw, dtype=np.float32),
        samplerate=16_000,
        subtype="PCM_16",
    )
    return target, len(raw) / sample_rate


def build_manifest(samples: list[dict]) -> dict:
    return {**MANIFEST, "samples": samples}


def write_manifest(manifest: dict, output: Path) -> None:
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_notice(output: Path, archive_name: str) -> None:
    (output / "NOTICE").write_text(
        "\n".join(
            [
                "VocalFlux accuracy corpus",
                "",
                "Source: LibriSpeech test-clean",
                f"Source URL: {SOURCE_URL}",
                f"Source archive: {archive_name}",
                f"Source SHA-256: {SOURCE_SHA256}",
                f"Built: {datetime.now(UTC).isoformat()}",
                f"License: {LICENSE}",
                "",
                "Audio files here are re encodings of LibriSpeech test clean clips,",
                "licensed under CC BY 4.0. Ground truth transcripts are the original",
                "LibriSpeech transcripts, reproduced without modification.",
                "",
                "Selection: one clip per speaker, 20 speakers, utterance lengths from",
                "about 4 to 13 seconds, long and short ground truth transcripts.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def verify_archive_sha256(archive: Path) -> None:
    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != SOURCE_SHA256:
        raise ValueError(
            f"archive {archive.name} sha256 {digest.hexdigest()} does not match pinned "
            f"{SOURCE_SHA256}"
        )


def build(archive: Path, output: Path) -> None:
    verify_archive_sha256(archive)
    output.mkdir(parents=True, exist_ok=True)
    samples: list[dict] = []
    with tarfile.open(archive, "r:gz") as tar:
        for clip_id in CLIP_IDS:
            reference = transcript_for(tar, clip_id)
            if reference is None:
                raise ValueError(f"no transcript found for {clip_id}")
            wav_path, duration = reencode_wav(tar, clip_id, output)
            speaker = clip_id.split("-", 1)[0]
            samples.append(
                {
                    "id": clip_id,
                    "audio": wav_path.name,
                    "reference": reference,
                    "tags": [f"speaker:{speaker}"],
                }
            )
    write_manifest(build_manifest(samples), output)
    write_notice(output, archive.name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild the committed LibriSpeech test clean accuracy corpus"
    )
    parser.add_argument("--archive", required=True, type=Path, help="local test-clean.tar.gz")
    parser.add_argument(
        "--output",
        default=Path("tests/fixtures/accuracy"),
        type=Path,
        help="fixture directory for the manifest, WAVs, and NOTICE",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    build(arguments.archive, arguments.output)
    print(f"Rebuilt accuracy corpus in {arguments.output}")
