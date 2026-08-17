# RunPod Deployment Notes

RunPod is the intended ephemeral GPU target for VocalFlux demonstrations and
benchmark runs.

## Image Publishing

`.github/workflows/publish-gpu-image.yml` publishes the backend CUDA image to
GitHub Container Registry on pushes to `main` that change the backend or GPU
Dockerfile. It also supports manual dispatch.

The resulting image is:

```text
ghcr.io/<owner>/vocalflux-backend-gpu:main
```

The RunPod host must be able to pull the package. Make the GHCR package public
for a portfolio demo or configure a read-only registry token in RunPod. Never
place that token in this repository.

Copy `runpod.env.example` into the pod configuration and replace the owner and
frontend host values.

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

## Pod Configuration

Create an on-demand GPU pod with the following settings:

| Setting | Value |
| --- | --- |
| Container image | `RUNPOD_IMAGE` |
| GPU | `RUNPOD_GPU_TYPE_ID` |
| Container port | `8000` over HTTP/WebSocket |
| Container disk | At least 20 GB |
| Volume | Optional model cache volume |
| Startup command | Image default command |

Expose the provider's public HTTP/WebSocket URL to the browser. Set
`NEXT_PUBLIC_WS_URL` in the frontend to the public WebSocket endpoint ending in
`/ws/v1/transcribe`.

## Readiness Validation

Do not send browser traffic until the model is ready:

```bash
curl --fail "$VOCALFLUX_PUBLIC_URL/health"
until curl -sf "$VOCALFLUX_PUBLIC_URL/ready" | grep -q '"ready":true'; do sleep 5; done
```

The first endpoint confirms process liveness. The second returns HTTP 503 until
the model has loaded; the loop blocks until it returns HTTP 200 with
`{"ready":true,...}` before a session is opened.

## Teardown

After the demonstration or benchmark:

1. Stop accepting new browser sessions.
2. Close the active WebSocket session.
3. Save benchmark JSON output outside the pod.
4. Stop and terminate the RunPod instance.
5. Verify the pod is no longer billing.

Do not bake credentials into the image. Configure registry and RunPod secrets
through the deployment platform. Terminate the GPU instance after each demo or
benchmark session.
