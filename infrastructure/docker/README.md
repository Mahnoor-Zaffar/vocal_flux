# Docker Workflows

## Local CPU Development

From the repository root:

```bash
cp .env.example .env
docker compose up --build
```

The frontend is available at `http://localhost:3000`. The backend exposes:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8000/metrics
```

The local image uses Python 3.13, `uv.lock`, the `small` Whisper model, CPU
inference, and `int8` compute. Model startup may take several minutes on the
first run while weights are downloaded into the `model-cache` volume.

## GPU Demo

The GPU override uses the NVIDIA CUDA runtime image, installs the optional
Silero VAD dependency, reserves one GPU, and switches to CUDA/float16:

```bash
docker compose \
  -f docker-compose.yml \
  -f infrastructure/docker/docker-compose.gpu.yml \
  up --build
```

The host must have a working NVIDIA Container Toolkit installation. GPU
deployment should be used for demos and benchmarks, not ordinary local
development.

## Image Rules

- Dependencies are installed from committed lockfiles.
- Model readiness is separate from process health.
- Containers log to stdout/stderr.
- The local Compose setup does not mount developer-specific paths beyond the
  source tree and model cache.
