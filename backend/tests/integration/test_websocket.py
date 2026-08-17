import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.inference.engine import MockInferenceEngine
from app.main import create_app


def test_websocket_streams_partial_and_final_transcripts() -> None:
    settings = Settings(_env_file=None, window_size_ms=1_000, overlap_ms=200)
    app = create_app(settings=settings, engine=MockInferenceEngine(settings.whisper_config()))

    with TestClient(app) as client:
        with client.websocket_connect("/ws/v1/transcribe") as websocket:
            started = websocket.receive_json()
            assert started["type"] == "session_started"
            session_id = started["session_id"]

            samples = np.full(16_000, 30_000, dtype="<i2")
            websocket.send_json(
                {
                    "type": "audio_frame",
                    "session_id": session_id,
                    "stream_id": "microphone",
                    "sequence_number": 0,
                }
            )
            websocket.send_bytes(samples.tobytes())

            partial = websocket.receive_json()
            assert partial["type"] == "transcript"
            assert not partial["is_final"]
            assert partial["text"] == "mock transcript"

            websocket.send_json({"type": "stop"})
            final = websocket.receive_json()
            closed = websocket.receive_json()

            assert final["type"] == "transcript"
            assert final["is_final"]
            assert closed == {
                "type": "session_closed",
                "session_id": session_id,
                "reason": "client_stop",
            }


def test_readiness_is_separate_from_process_health() -> None:
    settings = Settings(_env_file=None)
    app = create_app(settings=settings, engine=MockInferenceEngine(settings.whisper_config()))

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_websocket_rejects_disallowed_origin() -> None:
    settings = Settings(_env_file=None, allowed_websocket_origins="http://localhost:3000")
    app = create_app(settings=settings, engine=MockInferenceEngine(settings.whisper_config()))

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as disconnected:
            with client.websocket_connect(
                "/ws/v1/transcribe", headers={"origin": "https://attacker.example"}
            ):
                pass

    assert disconnected.value.code == 1008
