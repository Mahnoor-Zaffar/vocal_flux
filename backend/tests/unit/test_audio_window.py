import numpy as np

from app.audio.buffer import AudioBuffer
from app.audio.window import WindowingStrategy


def test_windowing_applies_overlap() -> None:
    buffer = AudioBuffer(sample_rate=1_000, max_duration_seconds=10)
    strategy = WindowingStrategy(sample_rate=1_000, window_size_ms=1_000, overlap_ms=200)
    buffer.append(np.arange(1_800, dtype=np.float32))

    first = strategy.next_window(buffer)
    second = strategy.next_window(buffer)

    assert first is not None
    assert second is not None
    assert len(first.samples) == 1_000
    assert len(second.samples) == 1_000
    assert first.start_sample == 0
    assert second.start_sample == 800


def test_flush_returns_partial_final_window() -> None:
    buffer = AudioBuffer(sample_rate=1_000, max_duration_seconds=10)
    strategy = WindowingStrategy(sample_rate=1_000, window_size_ms=1_000, overlap_ms=200)
    buffer.append(np.ones(400, dtype=np.float32))

    window = strategy.next_window(buffer, flush=True)

    assert window is not None
    assert window.is_final
    assert len(window.samples) == 400
    assert buffer.sample_count == 0
