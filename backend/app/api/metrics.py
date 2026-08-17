from fastapi import APIRouter, Request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

router = APIRouter()


@router.get("/metrics")
async def metrics(request: Request) -> Response:
    manager = request.app.state.session_manager
    payload = generate_latest()
    _ = manager
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)
