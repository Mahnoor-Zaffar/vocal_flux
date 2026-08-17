import numpy as np

from app.audio.vad import EnergyVAD, VADConfig, VADStateMachine


def test_vad_requires_sustained_speech_and_silence() -> None:
    vad = EnergyVAD(
        VADConfig(
            threshold=0.5,
            min_speech_duration_ms=200,
            min_silence_duration_ms=200,
        ),
        sample_rate=1_000,
    )
    speech = np.ones(100, dtype=np.float32)
    silence = np.zeros(100, dtype=np.float32)

    first = vad.process(speech)
    second = vad.process(speech)
    third = vad.process(silence)
    fourth = vad.process(silence)

    assert not first.is_speech
    assert second.speech_started
    assert second.is_speech
    assert not third.speech_ended
    assert fourth.speech_ended
    assert not fourth.is_speech


def test_vad_state_machine_times_out_long_segments() -> None:
    state = VADStateMachine(
        VADConfig(
            threshold=0.5,
            min_speech_duration_ms=0,
            min_silence_duration_ms=500,
            segment_timeout_ms=300,
        ),
        sample_rate=1_000,
    )

    state.update(1.0, 100)
    decision = state.update(1.0, 200)

    assert decision.speech_ended
    assert not decision.is_speech
