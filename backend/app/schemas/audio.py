from typing import Literal

from pydantic import BaseModel, Field


class AudioFrameMetadata(BaseModel):
    type: Literal["audio_frame"]
    session_id: str = Field(min_length=1, max_length=128)
    stream_id: str = Field(min_length=1, max_length=128)
    sequence_number: int = Field(ge=0)
    capture_started_ms: int | None = Field(default=None, ge=0)
