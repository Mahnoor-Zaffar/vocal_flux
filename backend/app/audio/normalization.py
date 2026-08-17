import numpy as np


class AudioNormalizationError(ValueError):
    """Raised when audio cannot be safely normalized."""


def normalize_pcm16(samples: np.ndarray) -> np.ndarray:
    """Convert PCM16 samples into finite float32 values in [-1.0, 1.0]."""

    if samples.ndim != 1:
        raise AudioNormalizationError("Audio must be a one-dimensional mono array")
    if not np.issubdtype(samples.dtype, np.integer):
        raise AudioNormalizationError("PCM16 input must use an integer dtype")

    normalized = samples.astype(np.float32) / 32_768.0
    if not np.isfinite(normalized).all():
        raise AudioNormalizationError("Audio contains non-finite samples")
    return np.clip(normalized, -1.0, 1.0)
