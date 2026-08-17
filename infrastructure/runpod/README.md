# RunPod Deployment Notes

RunPod is the intended ephemeral GPU target for VocalFlux demonstrations and
benchmark runs.

## Lifecycle

```text
Provision GPU
    ↓
Pull published image
    ↓
Expose TCP/WebSocket port 8000
    ↓
Wait for /ready
    ↓
Run demo or benchmark
    ↓
Stop service and terminate pod
```

Use the GPU Compose override as the local validation reference:

```bash
docker compose \
  -f docker-compose.yml \
  -f infrastructure/docker/docker-compose.gpu.yml \
  config
```

The deployment must provide these environment values:

```text
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
WHISPER_MODEL=small
```

Do not bake credentials into the image. Configure registry and RunPod secrets
through the deployment platform. Terminate the GPU instance after each demo or
benchmark session.
