from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

from .audio import SAMPLE_RATE, Clip

CHUNK_MS = 100


@dataclass(frozen=True)
class Event:
    at: float
    text: str
    kind: str


@dataclass
class Trial:
    """One sentence played to one backend, and everything that came back.

    The clock origin is `speech_end`: the instant the last sample of real
    speech was handed to the backend. Every reported latency is relative to
    that, because that is the moment a human stops talking and starts waiting.
    """

    clip_index: int
    audio_s: float
    events: list[Event] = field(default_factory=list)
    speech_end: float | None = None
    error: str | None = None

    def _offset(self, at: float) -> float:
        assert self.speech_end is not None
        return (at - self.speech_end) * 1000.0

    @property
    def transcript_events(self) -> list[Event]:
        return [e for e in self.events if e.kind != "error" and e.text]

    @property
    def first_ms(self) -> float | None:
        events = self.transcript_events
        return self._offset(events[0].at) if events else None

    @property
    def settle_ms(self) -> float | None:
        events = self.transcript_events
        return self._offset(events[-1].at) if events else None

    @property
    def text(self) -> str:
        events = self.transcript_events
        return events[-1].text if events else ""

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.transcript_events)


class Session:
    """Feeds one clip to a backend at wall-clock pace and times the replies.

    Audio is never sent faster than real time; a backend handed a 3-second
    sentence in one burst would look artificially fast, because no microphone
    can do that. After the speech runs out the session keeps feeding silence,
    which is what lets each backend's own endpointer fire on its own schedule,
    and stops only once the transcript has gone quiet for `quiet_s`.
    """

    def __init__(
        self,
        clip: Clip,
        quiet_s: float = 2.5,
        max_wait_s: float = 30.0,
        min_trail_s: float = 0.5,
    ) -> None:
        self.clip = clip
        self.trial = Trial(clip_index=clip.index, audio_s=clip.duration_s)
        self._quiet_s = quiet_s
        self._max_wait_s = max_wait_s
        self._min_trail_s = min_trail_s
        self._last_event_at: float | None = None

    def record(self, text: str, kind: str = "partial") -> None:
        text = (text or "").strip()
        if not text:
            return
        # An update that repeats the current transcript verbatim has not
        # changed what the speaker sees, so it must not extend settle time.
        if self.trial.events and self.trial.events[-1].text == text:
            return
        now = time.perf_counter()
        self._last_event_at = now
        self.trial.events.append(Event(now, text, kind))

    def record_error(self, message: str) -> None:
        now = time.perf_counter()
        self.trial.events.append(Event(now, message, "error"))
        self.trial.error = message

    def _done_waiting(self) -> bool:
        assert self.trial.speech_end is not None
        now = time.perf_counter()
        if now - self.trial.speech_end < self._min_trail_s:
            return False
        if now - self.trial.speech_end >= self._max_wait_s:
            return True
        if self._last_event_at is None:
            return False
        return now - self._last_event_at >= self._quiet_s

    async def chunks(self) -> AsyncIterator[bytes]:
        chunk_bytes = SAMPLE_RATE * 2 * CHUNK_MS // 1000
        silence = b"\x00" * chunk_bytes
        pcm = self.clip.pcm
        start = time.perf_counter()
        sent = 0

        async def pace() -> None:
            nonlocal sent
            sent += 1
            target = start + sent * CHUNK_MS / 1000.0
            await asyncio.sleep(max(0.0, target - time.perf_counter()))

        for offset in range(0, len(pcm), chunk_bytes):
            yield pcm[offset : offset + chunk_bytes]
            await pace()

        self.trial.speech_end = time.perf_counter()

        while not self._done_waiting():
            yield silence
            await pace()
