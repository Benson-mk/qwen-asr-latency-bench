from __future__ import annotations

import asyncio
import base64

import httpx
import numpy as np
import sherpa_onnx

from ..audio import SAMPLE_RATE, VAD_WINDOW, ensure_vad_model, pcm16_to_wav
from ..config import Settings
from ..session import Session
from ..transcript import merge

MIN_SILENCE_S = 0.4
MAX_SPEECH_S = 8.0
SEGMENT_PAD_S = 0.25


class LocalSegmenter:
    """Cuts the incoming stream at short silences, emitting padded segments.

    Qwen3-ASR Flash is a file-in / text-out endpoint with no notion of a
    stream, so simulated streaming needs an endpointer on this side. Its
    hangover (`MIN_SILENCE_S`) is unavoidable latency the caller pays before
    the request is even sent, and is part of what this benchmark measures.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = ensure_vad_model()
        config.silero_vad.min_silence_duration = MIN_SILENCE_S
        config.silero_vad.max_speech_duration = MAX_SPEECH_S
        config.sample_rate = sample_rate
        self._vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=120)
        self._rate = sample_rate
        self._buffer = bytearray()
        self._consumed = 0
        self._emitted_end = 0

    def _padded(self, start: int, length: int) -> bytes:
        pad = int(SEGMENT_PAD_S * self._rate)
        begin = max(0, start - pad) * 2
        end = min(len(self._buffer), (start + length + pad) * 2)
        self._emitted_end = start + length
        return bytes(self._buffer[begin:end])

    def _drain(self):
        while not self._vad.empty():
            segment = self._vad.front
            yield self._padded(segment.start, len(segment.samples))
            self._vad.pop()

    def feed(self, chunk: bytes):
        self._buffer.extend(chunk)
        samples = np.frombuffer(self._buffer, np.int16)
        while self._consumed + VAD_WINDOW <= len(samples):
            window = samples[self._consumed : self._consumed + VAD_WINDOW]
            self._vad.accept_waveform(window.astype(np.float32) / 32768.0)
            self._consumed += VAD_WINDOW
        yield from self._drain()

    def finish(self) -> bytes:
        # Only what the VAD calls speech. The unemitted tail is the benchmark's
        # own trailing silence, and shipping it would bill a second request
        # whose round trip is not latency any speaker ever waits through.
        self._vad.flush()
        return b"".join(self._drain())


async def transcribe_segment(
    client: httpx.AsyncClient, settings: Settings, wav: bytes
) -> str:
    # The audio must be a data URI. Handed a bare base64 string the upstream
    # service treats it as a URL and shells out to wget, returning a 500.
    data_uri = f"data:audio/wav;base64,{base64.b64encode(wav).decode()}"
    response = await client.post(
        f"{settings.http_base}/chat/completions",
        headers=settings.auth_header,
        json={
            "model": settings.flash_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_audio", "input_audio": {"data": data_uri}}
                    ],
                }
            ],
            "stream": False,
        },
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"] or ""


def make_client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=300, trust_env=False, proxy=settings.proxy)


async def run(
    session: Session,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Simulated streaming: local VAD cuts sentences, each goes out as HTTP.

    A caller-supplied `client` keeps the pooled TLS connection alive across
    trials; passing None reproduces the cost of opening a fresh connection per
    segment, which is how a naive integration behaves.
    """
    owned = client is None
    client = client or make_client(settings)
    segmenter = LocalSegmenter()
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def transcriber() -> None:
        # Requests run off the audio path: a microphone does not stop
        # capturing while a segment is in flight, so neither may the pacer.
        transcript = ""
        while True:
            pcm = await queue.get()
            if pcm is None:
                return
            try:
                text = await transcribe_segment(client, settings, pcm16_to_wav(pcm))
            except httpx.HTTPError as exc:
                session.record_error(f"{type(exc).__name__}: {exc}")
                return
            transcript = merge(transcript, text.strip())
            session.record(transcript)

    def submit(pcm: bytes) -> None:
        if len(pcm) >= int(0.3 * SAMPLE_RATE * 2):
            queue.put_nowait(pcm)

    worker = asyncio.create_task(transcriber())
    try:
        async for chunk in session.chunks():
            for segment in segmenter.feed(chunk):
                submit(segment)
        submit(segmenter.finish())
        queue.put_nowait(None)
        await asyncio.wait_for(worker, timeout=120)
    except asyncio.TimeoutError:
        worker.cancel()
        session.record_error("transcription worker timed out")
    finally:
        if not worker.done():
            worker.cancel()
        if owned:
            await client.aclose()
