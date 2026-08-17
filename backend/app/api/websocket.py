import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.schemas.audio import AudioFrameMetadata
from app.schemas.session import ControlMessage
from app.streaming.manager import InferenceUnavailable, SessionLimitExceeded

router = APIRouter()


@router.websocket("/ws/v1/transcribe")
async def transcribe(websocket: WebSocket) -> None:
    manager = websocket.app.state.session_manager
    try:
        session = await manager.create()
    except InferenceUnavailable:
        await websocket.close(code=1013, reason="Inference engine is not ready")
        return
    except SessionLimitExceeded:
        await websocket.close(code=1013, reason="Session limit reached")
        return

    await websocket.accept()
    pending_metadata: AudioFrameMetadata | None = None

    async def receive_loop() -> None:
        nonlocal pending_metadata
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                await session.close(reason="client_disconnect")
                return
            if message.get("bytes") is not None:
                if pending_metadata is None:
                    await session.emit_error("INVALID_FRAME", "Binary audio has no metadata")
                    continue
                payload = message["bytes"]
                if len(payload) > session.settings.max_message_size:
                    await session.emit_error("MESSAGE_TOO_LARGE", "Audio frame exceeds size limit")
                else:
                    await session.submit_audio(pending_metadata, payload)
                pending_metadata = None
                continue
            if message.get("text") is None:
                continue
            try:
                data = json.loads(message["text"])
            except json.JSONDecodeError:
                await session.emit_error("INVALID_MESSAGE", "Text frame is not valid JSON")
                continue
            if data.get("type") == "audio_frame":
                if pending_metadata is not None:
                    await session.emit_error(
                        "INVALID_FRAME", "Audio metadata must be followed by binary audio"
                    )
                try:
                    pending_metadata = AudioFrameMetadata.model_validate(data)
                except ValidationError:
                    await session.emit_error("INVALID_FRAME", "Invalid audio frame metadata")
                continue
            if pending_metadata is not None:
                await session.emit_error(
                    "INVALID_FRAME", "Audio metadata was not followed by binary audio"
                )
                pending_metadata = None
            try:
                control = ControlMessage.model_validate(data)
            except ValidationError:
                await session.emit_error("INVALID_MESSAGE", "Invalid control message")
                continue
            await session.submit_control(control)
            if control.type == "stop":
                return

    async def send_loop() -> None:
        while True:
            event = await session.next_event()
            await websocket.send_json(event.model_dump(mode="json"))
            if event.type == "session_closed":
                return

    try:
        async with asyncio.TaskGroup() as task_group:
            task_group.create_task(receive_loop())
            task_group.create_task(send_loop())
    except WebSocketDisconnect:
        pass
    finally:
        await manager.remove(session, reason="disconnect")
