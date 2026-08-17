from app.transcript.assembler import append_with_overlap
from app.transcript.events import TranscriptUpdate
from app.transcript.state import TranscriptState


def update(sequence: int, text: str, *, is_final: bool = False) -> TranscriptUpdate:
    return TranscriptUpdate(sequence, text, is_final, 10.0)


def test_assembler_removes_word_overlap() -> None:
    assert append_with_overlap("the quick brown", "brown fox") == "the quick brown fox"


def test_partial_hypothesis_is_replaced_without_duplicate_text() -> None:
    state = TranscriptState()

    first = state.apply(update(1, "the quick"))
    replacement = state.apply(update(1, "the quick brown"))
    next_window = state.apply(update(2, "the quick brown fox"))
    final = state.apply(update(3, "brown fox", is_final=True))

    assert first.text == "the quick"
    assert replacement.text == "the quick brown"
    assert next_window.committed_text == "the quick brown"
    assert next_window.unstable_text == "the quick brown fox"
    assert final.committed_text == "the quick brown fox"
    assert final.unstable_text == ""


def test_late_and_duplicate_final_updates_are_ignored() -> None:
    state = TranscriptState()
    state.apply(update(1, "hello"))
    state.apply(update(2, "hello world", is_final=True))

    late = state.apply(update(1, "old"))
    duplicate = state.apply(update(2, "hello world", is_final=True))

    assert late.ignored
    assert duplicate.ignored
    assert state.committed_text == "hello world"
