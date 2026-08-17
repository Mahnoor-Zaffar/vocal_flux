from typing import Final

import numpy as np

DEFAULT_SAMPLE_RATE: Final = 16_000
DEFAULT_CHANNELS: Final = 1


class AudioFormatError(ValueError):
    """Raised when an audio payload violates the transport contract."""


def decode_pcm16(
    payload: bytes,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    expected_sample_rate: int = DEFAULT_SAMPLE_RATE,
    expected_channels: int = DEFAULT_CHANNELS,
    max_bytes: int | None = None,
) -> np.ndarray:
    """Decode a validated PCM16 little-endian payload into int16 samples."""

    if max_bytes is not None and len(payload) > max_bytes:
        raise AudioFormatError("Audio payload exceeds the configured byte limit")
    if sample_rate != expected_sample_rate:
        raise AudioFormatError(
            f"Unsupported sample rate: {sample_rate}; expected {expected_sample_rate}"
        )
    if channels != expected_channels:
        raise AudioFormatError(
            f"Unsupported channel count: {channels}; expected {expected_channels}"
        )
    if len(payload) % 2:
        raise AudioFormatError("PCM16 payload must contain complete 2-byte samples")
    if not payload:
        raise AudioFormatError("Audio payload cannot be empty")

    return np.frombuffer(payload, dtype="<i2").copy()
