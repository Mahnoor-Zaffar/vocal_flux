from app.core.config import Settings


def test_local_defaults_are_cpu_first() -> None:
    settings = Settings(_env_file=None)

    assert settings.whisper_model == "small"
    assert settings.whisper_device == "cpu"
    assert settings.whisper_compute_type == "int8"


def test_blank_language_becomes_none() -> None:
    settings = Settings(_env_file=None, whisper_language="   ")

    assert settings.whisper_config().language is None
