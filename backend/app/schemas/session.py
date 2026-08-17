from typing import Literal

from pydantic import BaseModel, Field


class ControlMessage(BaseModel):
    type: Literal["start", "stop", "flush", "ping"]
    id: str | None = Field(default=None, max_length=128)
