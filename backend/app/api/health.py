from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    lifecycle = request.app.state.model_lifecycle
    return {"status": "ok", "model_state": lifecycle.state.value}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    lifecycle = request.app.state.model_lifecycle
    status_code = 200 if lifecycle.ready else 503
    return JSONResponse(
        status_code=status_code,
        content={"ready": lifecycle.ready, "model_state": lifecycle.state.value},
    )
