from __future__ import annotations

import asyncio
import base64
import json
import ssl

import certifi
import websockets

from ..config import Settings
from ..session import Session

TEXT_EVENT = "conversation.item.input_audio_transcription.text"
COMPLETED_EVENT = "conversation.item.input_audio_transcription.completed"
FAILED_EVENT = "conversation.item.input_audio_transcription.failed"


def connect(settings: Settings):
    return websockets.connect(
        f"{settings.realtime_url}?model={settings.realtime_model}",
        additional_headers=settings.auth_header,
        proxy=settings.proxy,
        ssl=ssl.create_default_context(cafile=certifi.where()),
        # DashScope never answers WebSocket pings; the default keepalive would
        # decide the link is dead mid-sentence and tear it down.
        ping_interval=None,
    )


async def run(session: Session, settings: Settings) -> None:
    """True streaming: audio goes up continuously, text comes back as it lands.

    Endpointing happens upstream (`server_vad`), so unlike the flash path
    nothing on this side delays the request; partial text typically arrives
    while the speaker is still mid-sentence.
    """
    try:
        async with connect(settings) as upstream:
            await upstream.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "input_audio_format": "pcm",
                            "sample_rate": 16000,
                            "turn_detection": {"type": "server_vad"},
                        },
                    }
                )
            )

            finished: list[str] = []

            async def receive() -> None:
                async for raw in upstream:
                    event = json.loads(raw)
                    kind = event.get("type", "")
                    if kind == TEXT_EVENT:
                        live = (event.get("text") or "") + (event.get("stash") or "")
                        session.record(" ".join(finished + [live]))
                    elif kind == COMPLETED_EVENT:
                        finished.append(event.get("transcript") or "")
                        session.record(" ".join(finished))
                    elif kind == FAILED_EVENT:
                        session.record_error(json.dumps(event.get("error", event))[:300])
                        return
                    elif kind == "session.finished":
                        return

            async def send() -> None:
                async for chunk in session.chunks():
                    await upstream.send(
                        json.dumps(
                            {
                                "type": "input_audio_buffer.append",
                                "audio": base64.b64encode(chunk).decode(),
                            }
                        )
                    )
                await upstream.send(json.dumps({"type": "session.finish"}))

            receiver = asyncio.create_task(receive())
            try:
                await send()
                await asyncio.wait_for(receiver, timeout=30)
            except asyncio.TimeoutError:
                receiver.cancel()
            finally:
                if not receiver.done():
                    receiver.cancel()
    except (websockets.WebSocketException, OSError) as exc:
        session.record_error(f"{type(exc).__name__}: {exc}")
