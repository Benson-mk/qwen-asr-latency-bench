from __future__ import annotations

import io
import os
import wave
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000
VAD_WINDOW = 512
VAD_MODEL_PATH = os.environ.get("VAD_MODEL", "models/silero_vad.onnx")
VAD_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
)


class AudioFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Clip:
    index: int
    samples: np.ndarray

    @property
    def duration_s(self) -> float:
        return len(self.samples) / SAMPLE_RATE

    @property
    def pcm(self) -> bytes:
        return self.samples.tobytes()

    def to_wav(self) -> bytes:
        return pcm16_to_wav(self.pcm, SAMPLE_RATE)


def ensure_vad_model(path: str = VAD_MODEL_PATH) -> str:
    if os.path.exists(path):
        return path
    import httpx

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    print(f"downloading silero VAD -> {path}")
    with httpx.Client(follow_redirects=True, timeout=600) as client:
        response = client.get(VAD_MODEL_URL)
        response.raise_for_status()
        partial = path + ".part"
        with open(partial, "wb") as handle:
            handle.write(response.content)
    os.replace(partial, path)
    return path


def pcm16_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(pcm)
    return buffer.getvalue()


def read_wav(path: str) -> np.ndarray:
    with wave.open(path) as reader:
        if (reader.getframerate(), reader.getnchannels(), reader.getsampwidth()) != (
            SAMPLE_RATE,
            1,
            2,
        ):
            raise AudioFormatError(
                f"{path}: need 16 kHz mono PCM16, got "
                f"{reader.getframerate()} Hz / {reader.getnchannels()} ch / "
                f"{reader.getsampwidth() * 8} bit"
            )
        return np.frombuffer(reader.readframes(reader.getnframes()), dtype=np.int16)


def cut_sentences(
    samples: np.ndarray,
    count: int,
    min_s: float = 1.5,
    max_s: float = 8.0,
    min_silence_s: float = 0.4,
) -> list[Clip]:
    """Slice natural sentences out of a recording at silence boundaries.

    Each clip is trimmed to speech only, with no leading or trailing silence:
    the benchmark appends its own silence so that speech end is a timestamp the
    harness controls exactly, rather than an artifact of where the cut landed.
    """
    import sherpa_onnx

    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = ensure_vad_model()
    config.silero_vad.min_silence_duration = min_silence_s
    config.silero_vad.max_speech_duration = max_s
    config.sample_rate = SAMPLE_RATE
    detector = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=180)

    floats = samples.astype(np.float32) / 32768.0
    clips: list[Clip] = []
    for offset in range(0, len(floats) - VAD_WINDOW, VAD_WINDOW):
        detector.accept_waveform(floats[offset : offset + VAD_WINDOW])
        while not detector.empty():
            segment = detector.front
            length = len(segment.samples)
            if min_s * SAMPLE_RATE <= length <= max_s * SAMPLE_RATE:
                clips.append(
                    Clip(len(clips) + 1, samples[segment.start : segment.start + length])
                )
            detector.pop()
        if len(clips) >= count:
            break
    return clips[:count]
