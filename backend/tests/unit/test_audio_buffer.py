import numpy as np
import pytest

from app.audio.buffer import AudioBuffer, AudioBufferOverflow


def test_buffer_preserves_fifo_samples_and_discards_prefix() -> None:
    buffer = AudioBuffer(sample_rate=1_000, max_duration_seconds=2)
    buffer.append(np.array([1, 2], dtype=np.float32))
    buffer.append(np.array([3, 4], dtype=np.float32))

    np.testing.assert_array_equal(buffer.peek(), [1, 2, 3, 4])
    buffer.discard(2)

    np.testing.assert_array_equal(buffer.peek(), [3, 4])
    assert buffer.duration_seconds == 0.002


def test_buffer_enforces_duration_limit() -> None:
    buffer = AudioBuffer(sample_rate=1_000, max_duration_seconds=0.003)

    buffer.append(np.zeros(3, dtype=np.float32))
    with pytest.raises(AudioBufferOverflow):
        buffer.append(np.zeros(1, dtype=np.float32))


def test_buffer_clear_releases_all_samples() -> None:
    buffer = AudioBuffer(sample_rate=1_000, max_duration_seconds=1)
    buffer.append(np.ones(100, dtype=np.float32))

    buffer.clear()

    assert buffer.sample_count == 0
    assert buffer.byte_count == 0
