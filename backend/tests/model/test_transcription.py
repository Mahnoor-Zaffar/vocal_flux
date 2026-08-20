import math

import pytest
from jiwer import cer, wer
from support import load_audio, normalize_for_scoring

MODEL_NAMES = ("base", "small")
_SLACK = 0.10


@pytest.mark.model
@pytest.mark.parametrize("model", MODEL_NAMES)
async def test_transcription_stays_within_committed_ceiling(model_lifecycle, ceiling, clip, model):
    lifecycle = await model_lifecycle(model)
    audio = load_audio(clip.audio_path)
    transcription = await lifecycle.transcribe(audio)
    wer_ceiling, cer_ceiling = ceiling(model, clip.id, _SLACK)
    wer_norm = wer(
        normalize_for_scoring(clip.reference),
        normalize_for_scoring(transcription.text),
    )
    cer_norm = cer(
        normalize_for_scoring(clip.reference),
        normalize_for_scoring(transcription.text),
    )
    assert math.isfinite(wer_norm) and math.isfinite(cer_norm)
    assert wer_norm < wer_ceiling, (
        f"{clip.id} WER {wer_norm:.3f} exceeded ceiling {wer_ceiling:.3f}"
    )
    assert cer_norm < cer_ceiling, (
        f"{clip.id} CER {cer_norm:.3f} exceeded ceiling {cer_ceiling:.3f}"
    )
