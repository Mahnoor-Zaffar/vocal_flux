import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
from websockets.asyncio.client import Connection, connect

from tests.benchmarks.reporting import count_errors

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_RATE = 16_000
CHUNK_MS = 40
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_MS // 1_000
READY_TIMEOUT_SECONDS = 300.0
SESSION_DEADLINE_SECONDS = 120.0


class BenchmarkAbort(RuntimeError):
    pass


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


class BenchmarkService:
    def __init__(
        self,
        *,
        model: str,
        device: str,
        compute_type: str,
        beam_size: int,
        language: str | None = None,
        max_concurrent_sessions: int = 64,
    ) -> None:
        self.model = model
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.language = language
        self.max_concurrent_sessions = max_concurrent_sessions
        self.port = _free_port()
        self.process: subprocess.Popen[bytes] | None = None

    @property
    def ws_url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/ws/v1/transcribe"

    def environment(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "WHISPER_MODEL": self.model,
                "WHISPER_DEVICE": self.device,
                "WHISPER_COMPUTE_TYPE": self.compute_type,
                "WHISPER_BEAM_SIZE": str(self.beam_size),
                "MAX_CONCURRENT_SESSIONS": str(self.max_concurrent_sessions),
                "RATE_LIMIT_ATTEMPTS": "100000",
            }
        )
        if self.language:
            env["WHISPER_LANGUAGE"] = self.language
        return env

    async def start(self) -> None:
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--log-level",
                "warning",
            ],
            cwd=BACKEND_ROOT,
            env=self.environment(),
        )
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        url = f"http://127.0.0.1:{self.port}/ready"
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise BenchmarkAbort(
                    f"benchmark service exited early with code {self.process.returncode}"
                )
            if await asyncio.to_thread(_http_ready, url):
                return
            await asyncio.sleep(0.5)
        raise BenchmarkAbort("benchmark service did not become ready in time")

    async def close(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                await asyncio.to_thread(self.process.wait, 10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                await asyncio.to_thread(self.process.wait)


class StreamSession:
    def __init__(self, ws_url: str, *, session_name: str, clip_id: str, audio: np.ndarray) -> None:
        self.ws_url = ws_url
        self.session_name = session_name
        self.clip_id = clip_id
        self.audio = audio
        self.started_ns = 0
        self.finals: list[dict[str, Any]] = []
        self.first_partial_ns: int | None = None
        self.first_final_ns: int | None = None
        self.partial_count = 0
        self.error_codes: list[str] = []
        self.fatal_code: str | None = None
        self.session_closed_ns: int | None = None
        self.dropped_frames = 0
        self.frames_sent = 0
        self.server_session_id: str | None = None
        self._server_ready = asyncio.Event()

    async def run(self) -> dict[str, Any]:
        pcm = np.clip(self.audio, -1.0, 1.0)
        pcm = (pcm * 32_767).astype("<i2")
        payload = pcm.tobytes()
        try:
            async with connect(self.ws_url, compression=None, max_size=2**20) as connection:
                reader = asyncio.create_task(self._read_loop(connection))
                try:
                    await asyncio.wait_for(self._server_ready.wait(), timeout=30.0)
                except TimeoutError:
                    reader.cancel()
                    raise BenchmarkAbort(
                        f"session {self.session_name} never received session_started"
                    ) from None
                self.started_ns = time.monotonic_ns()
                total_chunks = max(1, len(payload) // (CHUNK_SAMPLES * 2))
                await self._feed(connection, payload, total_chunks)
                await connection.send(json.dumps({"type": "stop"}))
                remaining = SESSION_DEADLINE_SECONDS - (time.monotonic_ns() - self.started_ns) / 1e9
                try:
                    await asyncio.wait_for(asyncio.shield(reader), timeout=max(remaining, 1.0))
                except TimeoutError:
                    reader.cancel()
                    raise BenchmarkAbort(
                        f"session {self.session_name} overstayed "
                        f"the {SESSION_DEADLINE_SECONDS}s deadline"
                    ) from None
        except BenchmarkAbort:
            raise
        except Exception as error:
            raise BenchmarkAbort(f"session {self.session_name} failed fatally: {error}") from error
        if self.fatal_code is not None:
            raise BenchmarkAbort(f"session {self.session_name} got fatal error {self.fatal_code}")
        return self.summary()

    async def _feed(self, connection: Connection, payload: bytes, total_chunks: int) -> None:
        chunk_bytes = CHUNK_SAMPLES * 2
        for index in range(total_chunks):
            target_ns = self.started_ns + index * CHUNK_MS * 1_000_000
            now_ns = time.monotonic_ns()
            if target_ns > now_ns:
                await asyncio.sleep((target_ns - now_ns) / 1e9)
            self.frames_sent += 1
            await connection.send(
                json.dumps(
                    {
                        "type": "audio_frame",
                        "session_id": self.server_session_id,
                        "stream_id": self.session_name,
                        "sequence_number": index,
                    }
                )
            )
            await connection.send(payload[index * chunk_bytes : (index + 1) * chunk_bytes])

    async def _read_loop(self, connection: Connection) -> None:
        try:
            async for raw in connection:
                message = json.loads(raw)
                received_ns = time.monotonic_ns()
                kind = message.get("type")
                if kind == "session_started":
                    self.server_session_id = message.get("session_id")
                    self._server_ready.set()
                elif kind == "transcript":
                    if message.get("is_final"):
                        self.finals.append(
                            {
                                "sequence": message.get("sequence"),
                                "latency_ms": message.get("latency_ms", 0.0),
                                "stage_timings_ms": message.get("stage_timings_ms") or {},
                            }
                        )
                        if self.first_final_ns is None:
                            self.first_final_ns = received_ns
                    else:
                        self.partial_count += 1
                        if self.first_partial_ns is None:
                            self.first_partial_ns = received_ns
                elif kind == "error":
                    code = message.get("code", "UNKNOWN")
                    self.error_codes.append(code)
                    if code == "QUEUE_OVERFLOW":
                        self.dropped_frames += 1
                    elif message.get("fatal"):
                        self.fatal_code = code
                elif kind == "session_closed":
                    self.session_closed_ns = received_ns
                    return
        finally:
            if not connection.close_code:
                await connection.close()

    @property
    def first_text_ns(self) -> int | None:
        candidates = [ns for ns in (self.first_partial_ns, self.first_final_ns) if ns]
        return min(candidates) if candidates else None

    def summary(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "server_session_id": self.server_session_id,
            "frames_sent": self.frames_sent,
            "dropped_frames": self.dropped_frames,
            "error_codes": count_errors(self.error_codes),
            "fatal_code": self.fatal_code,
            "finals_count": len(self.finals),
            "partial_count": self.partial_count,
        }
