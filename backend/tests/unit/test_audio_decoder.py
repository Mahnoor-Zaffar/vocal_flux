import numpy as np
import pytest

from app.audio.decoder import AudioFormatError, decode_pcm16
from app.audio.normalization import AudioNormalizationError, normalize_pcm16


def test_decode_and_normalize_pcm16_little_endian() -> None:
    payload = np.array([0, 32_767, -32_768], dtype="<i2").tobytes()

    decoded = decode_pcm16(payload)
    normalized = normalize_pcm16(decoded)

    np.testing.assert_array_equal(decoded, [0, 32_767, -32_768])
    np.testing.assert_allclose(normalized, [0.0, 32_767 / 32_768, -1.0])
    assert normalized.dtype == np.float32


def test_decoder_rejects_invalid_payloads() -> None:
    with pytest.raises(AudioFormatError, match="complete 2-byte"):
        decode_pcm16(b"\x00")
    with pytest.raises(AudioFormatError, match="sample rate"):
        decode_pcm16(b"\x00\x00", sample_rate=8_000)


def test_normalizer_rejects_non_integer_input() -> None:
    with pytest.raises(AudioNormalizationError, match="integer"):
        normalize_pcm16(np.zeros(4, dtype=np.float32))
