from typing import Literal

from pydantic import BaseModel, Field


class SessionStartedEvent(BaseModel):
    type: Literal["session_started"] = "session_started"
    session_id: str


class TranscriptEvent(BaseModel):
    type: Literal["transcript"] = "transcript"
    session_id: str
    sequence: int
    text: str
    is_final: bool
    latency_ms: float = Field(ge=0)


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    fatal: bool = False
    session_id: str | None = None


class PongEvent(BaseModel):
    type: Literal["pong"] = "pong"
    id: str | None = None


class SessionClosedEvent(BaseModel):
    type: Literal["session_closed"] = "session_closed"
    session_id: str
    reason: str


ProtocolEvent = (
    SessionStartedEvent | TranscriptEvent | ErrorEvent | PongEvent | SessionClosedEvent
)
