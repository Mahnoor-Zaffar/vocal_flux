from prometheus_client import Counter, Gauge, Histogram

active_sessions = Gauge("vocalflux_active_sessions", "Number of active transcription sessions")
total_sessions = Counter("vocalflux_total_sessions", "Total sessions created")
rejected_sessions = Counter(
    "vocalflux_rejected_sessions", "Sessions rejected", ["reason"]
)
queue_overflows = Counter(
    "vocalflux_queue_overflows", "Audio queue overflow events", ["policy"]
)
session_duration = Histogram(
    "vocalflux_session_duration_seconds", "Session lifetime in seconds"
)
inference_errors = Counter("vocalflux_inference_errors", "Inference errors", ["code"])
audio_dropped = Counter("vocalflux_audio_dropped_seconds", "Dropped audio seconds")


def session_started() -> None:
    active_sessions.inc()
    total_sessions.inc()


def session_closed(duration_seconds: float) -> None:
    active_sessions.dec()
    session_duration.observe(duration_seconds)
