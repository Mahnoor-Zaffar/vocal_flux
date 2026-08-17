import re

_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def append_with_overlap(existing: str, incoming: str) -> str:
    """Append text while removing the largest word overlap at the boundary."""

    left = normalize_text(existing)
    right = normalize_text(incoming)
    if not left:
        return right
    if not right:
        return left

    left_words = left.split(" ")
    right_words = right.split(" ")
    for overlap in range(min(len(left_words), len(right_words)), 0, -1):
        if left_words[-overlap:] == right_words[:overlap]:
            return " ".join(left_words + right_words[overlap:])
    return f"{left} {right}"
