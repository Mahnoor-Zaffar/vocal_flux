import numpy as np

from app.streaming.context import TranscriptContext


def test_context_bounds_prompt_and_copies_audio_overlap() -> None:
    context = TranscriptContext(max_prompt_chars=5)
    context.update_committed_text("hello world")
    source = np.arange(5, dtype=np.float32)
    context.set_audio_overlap(source, 2)

    assert context.prompt == "world"
    np.testing.assert_array_equal(context.audio_overlap, [3, 4])


def test_context_reset_clears_prompt_and_overlap() -> None:
    context = TranscriptContext()
    context.update_committed_text("hello")
    context.set_audio_overlap(np.ones(3, dtype=np.float32), 2)

    context.reset()

    assert context.prompt is None
    assert context.audio_overlap.size == 0
