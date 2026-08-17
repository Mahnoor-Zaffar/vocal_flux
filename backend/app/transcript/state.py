from dataclasses import dataclass

from app.transcript.assembler import append_with_overlap, normalize_text
from app.transcript.events import TranscriptEmission, TranscriptUpdate


@dataclass(slots=True)
class TranscriptState:
    """Track stable transcript text separately from the current hypothesis."""

    committed_text: str = ""
    unstable_text: str = ""
    last_sequence: int = -1
    last_final_sequence: int = -1

    @property
    def rendered_text(self) -> str:
        return append_with_overlap(self.committed_text, self.unstable_text)

    def apply(self, update: TranscriptUpdate) -> TranscriptEmission:
        text = normalize_text(update.text)
        if update.sequence < self.last_sequence:
            return self._ignored(update)
        if update.is_final and update.sequence <= self.last_final_sequence:
            return self._ignored(update)

        if update.sequence > self.last_sequence and self.unstable_text:
            self.committed_text = append_with_overlap(self.committed_text, self.unstable_text)
        self.last_sequence = max(self.last_sequence, update.sequence)

        if update.is_final:
            self.committed_text = append_with_overlap(self.committed_text, text)
            self.unstable_text = ""
            self.last_final_sequence = update.sequence
        else:
            self.unstable_text = text

        return TranscriptEmission(
            sequence=update.sequence,
            text=self.rendered_text,
            committed_text=self.committed_text,
            unstable_text=self.unstable_text,
            is_final=update.is_final,
            latency_ms=update.latency_ms,
        )

    def reset_unstable(self) -> None:
        self.unstable_text = ""

    def reset(self) -> None:
        self.committed_text = ""
        self.unstable_text = ""
        self.last_sequence = -1
        self.last_final_sequence = -1

    def _ignored(self, update: TranscriptUpdate) -> TranscriptEmission:
        return TranscriptEmission(
            sequence=update.sequence,
            text=self.rendered_text,
            committed_text=self.committed_text,
            unstable_text=self.unstable_text,
            is_final=update.is_final,
            latency_ms=update.latency_ms,
            ignored=True,
        )
