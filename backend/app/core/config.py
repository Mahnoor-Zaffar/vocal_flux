from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WhisperConfig(BaseModel):
    """Configuration needed to construct an inference engine."""

    model: str = Field(min_length=1)
    device: Literal["cpu", "cuda", "auto"]
    compute_type: str = Field(min_length=1)
    language: str | None = None
    beam_size: int = Field(default=5, ge=1, le=20)

    @field_validator("language", mode="before")
    @classmethod
    def normalize_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    log_level: str = "INFO"
    whisper_model: str = "small"
    whisper_device: Literal["cpu", "cuda", "auto"] = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str | None = None
    whisper_beam_size: int = Field(default=5, ge=1, le=20)
    audio_sample_rate: int = Field(default=16_000, ge=8_000)
    audio_channels: int = Field(default=1, ge=1, le=2)
    vad_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    vad_min_speech_duration_ms: int = Field(default=250, ge=0)
    vad_min_silence_duration_ms: int = Field(default=500, ge=0)
    vad_speech_pad_ms: int = Field(default=30, ge=0)
    vad_segment_timeout_ms: int = Field(default=30_000, ge=0)
    window_size_ms: int = Field(default=1_000, ge=1)
    overlap_ms: int = Field(default=300, ge=0)
    max_audio_buffer: float = Field(default=300.0, gt=0)
    max_message_size: int = Field(default=65_536, gt=0)
    max_queue_size: int = Field(default=10, gt=0)
    max_concurrent_sessions: int = Field(default=10, gt=0)
    inference_timeout: float = Field(default=10.0, gt=0)
    inference_timeout_headroom: float = Field(default=3.0, gt=0)
    inference_timeout_margin: float = Field(default=2.0, gt=0)
    inference_recovery_delay: float = Field(default=3.0, gt=0)
    queue_overflow_policy: Literal["drop", "disconnect"] = "drop"
    max_session_duration: float = Field(default=3_600, gt=0)
    allowed_websocket_origins: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"
    rate_limit_attempts: int = Field(default=30, gt=0)
    rate_limit_window_seconds: int = Field(default=60, gt=0)
    graceful_shutdown_timeout: float = Field(default=15.0, gt=0)

    def websocket_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_websocket_origins.split(",")
            if origin.strip()
        ]

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def whisper_config(self) -> WhisperConfig:
        return WhisperConfig(
            model=self.whisper_model,
            device=self.whisper_device,
            compute_type=self.whisper_compute_type,
            language=self.whisper_language,
            beam_size=self.whisper_beam_size,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
