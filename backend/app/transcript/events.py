from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TranscriptUpdate:
    sequence: int
    text: str
    is_final: bool
    latency_ms: float


@dataclass(frozen=True, slots=True)
class TranscriptEmission:
    sequence: int
    text: str
    committed_text: str
    unstable_text: str
    is_final: bool
    latency_ms: float
    ignored: bool = False
