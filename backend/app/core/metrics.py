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
audio_seconds_processed = Counter(
    "vocalflux_audio_seconds_processed", "Audio seconds accepted for processing"
)
audio_seconds_dropped = Counter(
    "vocalflux_audio_seconds_dropped", "Audio seconds dropped before processing"
)
audio_dropped = audio_seconds_dropped
inference_count = Counter("vocalflux_inference_count", "Completed inference calls")
inference_latency = Histogram(
    "vocalflux_inference_latency_seconds", "Inference duration in seconds"
)
first_result_latency = Histogram(
    "vocalflux_first_result_latency_seconds", "Speech start to first transcript"
)
queue_depth = Gauge("vocalflux_queue_depth", "Current aggregate session queue depth")
model_load_time = Histogram("vocalflux_model_load_seconds", "Model load and warmup duration")
stage_latency = Histogram(
    "vocalflux_stage_latency_seconds",
    "Audio pipeline stage duration in seconds",
    ["stage"],
)
gpu_memory_used = Gauge("vocalflux_gpu_memory_used_bytes", "GPU memory used when available")
gpu_memory_total = Gauge("vocalflux_gpu_memory_total_bytes", "GPU memory total when available")
gpu_utilization = Gauge("vocalflux_gpu_utilization_ratio", "GPU utilization when available")


def session_started() -> None:
    active_sessions.inc()
    total_sessions.inc()


def session_closed(duration_seconds: float) -> None:
    active_sessions.dec()
    session_duration.observe(duration_seconds)


def observe_stage(stage: str, duration_seconds: float) -> None:
    stage_latency.labels(stage=stage).observe(max(0.0, duration_seconds))


def observe_inference(duration_seconds: float) -> None:
    inference_count.inc()
    inference_latency.observe(max(0.0, duration_seconds))


def observe_first_result(duration_seconds: float) -> None:
    first_result_latency.observe(max(0.0, duration_seconds))
