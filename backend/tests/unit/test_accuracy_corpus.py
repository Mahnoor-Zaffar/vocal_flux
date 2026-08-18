import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import scripts.rebuild_accuracy_corpus as corpus
from tests.benchmarks import evaluate_accuracy as harness
from tests.benchmarks.evaluate_accuracy import normalize_for_scoring


def test_normalize_for_scoring_lowercases_and_strips_punctuation() -> None:
    assert normalize_for_scoring("THE QUICK BROWN FOX!") == "the quick brown fox"
    assert normalize_for_scoring("It's, a: test.") == "it s a test"


def test_normalize_for_scoring_keeps_word_boundaries() -> None:
    assert normalize_for_scoring("Don't stop. No?") == "don t stop no"


def _write_synthetic_archive(tmp_path) -> object:
    archive = tmp_path / "mini.tar.gz"
    audio = np.zeros(16_000, dtype=np.float32)
    wav_bytes_path = tmp_path / "1089-134691-0006.flac"
    sf.write(
        wav_bytes_path,
        audio,
        samplerate=16_000,
        format="FLAC",
        subtype="PCM_16",
    )
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(
            wav_bytes_path,
            arcname="LibriSpeech/test-clean/1089/134691/1089-134691-0006.flac",
        )
        transcript = "1089-134691-0006 HE COULD WAIT NO LONGER\n"
        info = tarfile.TarInfo(
            "LibriSpeech/test-clean/1089/134691/1089-134691.trans.txt"
        )
        payload = transcript.encode("utf-8")
        info.size = len(payload)
        tar.addfile(info, __import__("io").BytesIO(payload))
    return archive


def test_transcript_for_reads_ground_truth(tmp_path) -> None:
    archive = _write_synthetic_archive(tmp_path)
    with tarfile.open(archive, "r:gz") as tar:
        assert (
            corpus.transcript_for(tar, "1089-134691-0006") == "HE COULD WAIT NO LONGER"
        )
        assert corpus.transcript_for(tar, "9999-99999-0000") is None


def test_reencode_wav_writes_16k_mono(tmp_path) -> None:
    archive = _write_synthetic_archive(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    with tarfile.open(archive, "r:gz") as tar:
        target, duration = corpus.reencode_wav(tar, "1089-134691-0006", output)

    samples, sample_rate = sf.read(target, dtype="float32", always_2d=False)
    assert sample_rate == 16_000
    assert samples.ndim == 1
    assert duration == pytest.approx(1.0)


def test_verify_archive_sha256_rejects_mismatch(tmp_path) -> None:
    archive = tmp_path / "different.tar.gz"
    archive.write_bytes(b"some other bytes")

    with pytest.raises(ValueError, match="does not match pinned"):
        corpus.verify_archive_sha256(archive)


def test_build_writes_manifest_and_notice(tmp_path, monkeypatch) -> None:
    archive = _write_synthetic_archive(tmp_path)
    monkeypatch.setattr(corpus, "SOURCE_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    monkeypatch.setattr(corpus, "CLIP_IDS", ("1089-134691-0006",))
    output = tmp_path / "fixtures"
    corpus.build(archive, output)

    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["version"] == 1
    assert manifest["sample_rate"] == 16_000
    assert len(manifest["samples"]) == 1
    sample = manifest["samples"][0]
    assert sample["id"] == "1089-134691-0006"
    assert sample["reference"] == "HE COULD WAIT NO LONGER"
    assert (output / sample["audio"]).exists()
    assert "CC BY 4.0" in (output / "NOTICE").read_text()


def test_build_fails_when_a_clip_has_no_transcript(tmp_path, monkeypatch) -> None:
    archive = _write_synthetic_archive(tmp_path)
    monkeypatch.setattr(corpus, "SOURCE_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    monkeypatch.setattr(corpus, "CLIP_IDS", ("9999-99999-0000",))
    output = tmp_path / "fixtures"

    with pytest.raises(ValueError, match="no transcript found"):
        corpus.build(archive, output)


def test_build_fails_when_a_clip_audio_is_missing(tmp_path, monkeypatch) -> None:
    archive = tmp_path / "ghost.tar.gz"
    audio = np.zeros(16_000, dtype=np.float32)
    flac = tmp_path / "clip.flac"
    sf.write(flac, audio, samplerate=16_000, format="FLAC", subtype="PCM_16")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(
            flac,
            arcname="LibriSpeech/test-clean/1089/134691/1089-134691-0006.flac",
        )
        transcript = "1089-134691-0006 HI\n"
        info = tarfile.TarInfo("LibriSpeech/test-clean/1089/134691/1089-134691.trans.txt")
        payload = transcript.encode("utf-8")
        info.size = len(payload)
        tar.addfile(info, __import__("io").BytesIO(payload))
        ghost = "9999-99999-0000 GHOST CLIP\n"
        ghost_info = tarfile.TarInfo("LibriSpeech/test-clean/9999/99999/9999-99999.trans.txt")
        ghost_payload = ghost.encode("utf-8")
        ghost_info.size = len(ghost_payload)
        tar.addfile(ghost_info, __import__("io").BytesIO(ghost_payload))

    monkeypatch.setattr(corpus, "SOURCE_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    monkeypatch.setattr(corpus, "CLIP_IDS", ("9999-99999-0000",))

    output = tmp_path / "fixtures"
    with pytest.raises(FileNotFoundError, match="not in archive"):
        corpus.build(archive, output)


def test_build_rejects_non_16000_hz_audio(tmp_path, monkeypatch) -> None:
    audio = np.zeros(16_000, dtype=np.float32)
    wav_bytes_path = tmp_path / "flac"
    sf.write(wav_bytes_path, audio, samplerate=22_050, format="FLAC", subtype="PCM_16")
    archive = tmp_path / "other.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(wav_bytes_path, arcname="LibriSpeech/test-clean/9999/99999/9999-99999-0000.flac")
        transcript = "9999-99999-0000 OTHER RATE\n"
        info = tarfile.TarInfo("LibriSpeech/test-clean/9999/99999/9999-99999.trans.txt")
        payload = transcript.encode("utf-8")
        info.size = len(payload)
        tar.addfile(info, __import__("io").BytesIO(payload))
    monkeypatch.setattr(corpus, "SOURCE_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    monkeypatch.setattr(corpus, "CLIP_IDS", ("9999-99999-0000",))
    output = tmp_path / "fixtures"

    with pytest.raises(ValueError, match="expected 16000"):
        corpus.build(archive, output)


def test_parse_args_requires_archive(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["rebuild", "--output", "/tmp/out"])
    with pytest.raises(SystemExit):
        corpus.parse_args()


def test_parse_args_default_output(tmp_path, monkeypatch) -> None:
    archive = tmp_path / "test-clean.tar.gz"
    monkeypatch.setattr(sys, "argv", ["rebuild", "--archive", str(archive)])
    args = corpus.parse_args()
    assert args.archive == archive
    assert args.output == Path("tests/fixtures/accuracy")


def test_accuracy_harness_parse_args_defaults_beam_to_one(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["evaluate"])
    args = harness.parse_args()
    assert args.beam_size == 1
    assert args.model == "small"
    assert args.device == "cpu"
    assert args.compute_type == "int8"
    assert args.manifest == "tests/fixtures/accuracy/manifest.json"


async def test_accuracy_harness_fails_deliberately_on_empty_manifest(tmp_path) -> None:
    manifest = tmp_path / "empty.json"
    manifest.write_text(
        json.dumps({"version": 1, "sample_rate": 16000, "channels": 1, "samples": []})
    )
    args = argparse.Namespace(
        manifest=str(manifest),
        model="tiny",
        device="cpu",
        compute_type="int8",
        language=None,
        beam_size=1,
    )

    with pytest.raises(ValueError, match="no samples"):
        await harness.evaluate(args)
