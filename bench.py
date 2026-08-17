"""Measure how long each Qwen3-ASR backend takes to answer after you stop talking.

    python bench.py
    python bench.py --backends flash-cold flash-warm realtime --clips 8

Every backend hears the same sentences, paced at 1x wall-clock speed, and is
scored on the same interval: last sample of speech -> transcript stops changing.
"""

from __future__ import annotations

import argparse
import asyncio

from qwenbench import report
from qwenbench.audio import Clip, cut_sentences, read_wav
from qwenbench.backends import flash, realtime
from qwenbench.config import MissingCredentials, Settings
from qwenbench.session import Session, Trial

DEFAULT_AUDIO = "audio/consultation_yue_16k.wav"
BACKENDS = ("flash-cold", "flash-warm", "realtime")


async def run_backend(
    name: str, clips: list[Clip], settings: Settings, pause_s: float
) -> list[Trial]:
    trials: list[Trial] = []
    shared = flash.make_client(settings) if name == "flash-warm" else None
    try:
        for clip in clips:
            session = Session(clip)
            if name == "realtime":
                await realtime.run(session, settings)
            else:
                await flash.run(session, settings, client=shared)
            trials.append(session.trial)
            await asyncio.sleep(pause_s)
    finally:
        if shared is not None:
            await shared.aclose()
    return trials


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backends", nargs="+", default=list(BACKENDS), choices=BACKENDS)
    parser.add_argument("--audio", default=DEFAULT_AUDIO)
    parser.add_argument("--clips", type=int, default=8)
    # Pooled connections only pay off while they are still open upstream, so
    # the gap between trials decides whether flash-warm differs from
    # flash-cold at all. See "Connection reuse" in the README.
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--out", default="results.json")
    parser.add_argument(
        "--proxy",
        nargs="?",
        const="",
        default=None,
        metavar="URL",
        help="route through a proxy; bare --proxy uses DASHSCOPE_PROXY from the "
        "environment. Off by default so timings measure the network you are on.",
    )
    args = parser.parse_args()

    proxy = args.proxy
    if proxy == "":
        proxy = Settings.env_proxy()
        if proxy is None:
            raise SystemExit("--proxy given with no URL and DASHSCOPE_PROXY is not set")

    try:
        settings = Settings.from_env(proxy=proxy)
    except MissingCredentials as exc:
        raise SystemExit(str(exc))

    clips = cut_sentences(read_wav(args.audio), args.clips)
    if not clips:
        raise SystemExit(f"no usable sentences found in {args.audio}")

    print(f"{settings.describe()}")
    print(
        f"{len(clips)} sentences from {args.audio}: "
        + ", ".join(f"{c.duration_s:.1f}s" for c in clips)
    )

    results: dict[str, list[Trial]] = {}
    for name in args.backends:
        results[name] = await run_backend(name, clips, settings, args.pause)
        report.summarize(name, results[name])

    report.compare(results)
    report.to_json(results, args.out)


if __name__ == "__main__":
    asyncio.run(main())
