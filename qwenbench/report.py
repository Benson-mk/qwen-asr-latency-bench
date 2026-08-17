from __future__ import annotations

import json
import statistics
from dataclasses import dataclass

from .session import Trial


@dataclass(frozen=True)
class Stats:
    count: int
    median: float
    mean: float
    minimum: float
    p90: float
    maximum: float

    @classmethod
    def of(cls, values: list[float]) -> "Stats | None":
        if not values:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, int(0.9 * len(ordered)))
        return cls(
            count=len(ordered),
            median=statistics.median(ordered),
            mean=statistics.mean(ordered),
            minimum=ordered[0],
            p90=ordered[index],
            maximum=ordered[-1],
        )

    def line(self, label: str) -> str:
        return (
            f"  {label:<13} n={self.count:<3} median={self.median:7.0f} ms  "
            f"mean={self.mean:7.0f}  min={self.minimum:7.0f}  "
            f"p90={self.p90:7.0f}  max={self.maximum:7.0f}"
        )


def summarize(name: str, trials: list[Trial]) -> None:
    print(f"\n=== {name} ===")
    for trial in trials:
        if trial.error:
            print(f"  #{trial.clip_index} {trial.audio_s:4.1f}s  ERROR {trial.error[:60]}")
            continue
        first = f"{trial.first_ms:7.0f}" if trial.first_ms is not None else "    n/a"
        settle = f"{trial.settle_ms:7.0f}" if trial.settle_ms is not None else "    n/a"
        print(
            f"  #{trial.clip_index} {trial.audio_s:4.1f}s  first={first} ms  "
            f"settle={settle} ms   {trial.text[-38:]}"
        )

    good = [t for t in trials if t.ok]
    # First token and settle answer different questions. Realtime streams
    # mid-utterance so its first token can precede speech end (negative);
    # settle is when the sentence stops changing, and is the comparable one.
    for label, values in (
        ("first token", [t.first_ms for t in good if t.first_ms is not None]),
        ("settle (EOS)", [t.settle_ms for t in good if t.settle_ms is not None]),
    ):
        stats = Stats.of(values)
        print(stats.line(label) if stats else f"  {label}: no data")
    if len(good) < len(trials):
        print(f"  ({len(trials) - len(good)} failed run(s) excluded)")


def compare(results: dict[str, list[Trial]]) -> None:
    settled = {
        name: Stats.of([t.settle_ms for t in trials if t.ok and t.settle_ms is not None])
        for name, trials in results.items()
    }
    usable = {name: stats for name, stats in settled.items() if stats}
    if len(usable) < 2:
        return
    fastest = min(usable, key=lambda n: usable[n].median)
    print("\n=== settle-after-speech-end, median ===")
    for name, stats in sorted(usable.items(), key=lambda kv: kv[1].median):
        ratio = stats.median / usable[fastest].median
        marker = "  <- fastest" if name == fastest else f"  {ratio:.1f}x slower"
        print(f"  {name:<28} {stats.median:7.0f} ms{marker}")


def to_json(
    results: dict[str, list[Trial]], path: str, run: dict[str, object] | None = None
) -> None:
    """Write per-trial timings, stamped with the run that produced them.

    The `run` block is what makes a saved result quotable. Identical audio and
    code produce 2-3x different numbers depending on the network route, so a
    bare table of milliseconds is unreadable a week later.
    """
    summary: dict[str, dict[str, float | None]] = {}
    for name, trials in results.items():
        stats = Stats.of([t.settle_ms for t in trials if t.ok and t.settle_ms is not None])
        summary[name] = {
            "settle_median_ms": None if stats is None else round(stats.median),
            "settle_p90_ms": None if stats is None else round(stats.p90),
        }

    payload = {
        "run": run or {},
        "summary": summary,
        "trials": {
            name: [
                {
                    "clip": t.clip_index,
                    "audio_s": round(t.audio_s, 2),
                    "first_ms": None if t.first_ms is None else round(t.first_ms),
                    "settle_ms": None if t.settle_ms is None else round(t.settle_ms),
                    "text": t.text,
                    "error": t.error,
                }
                for t in trials
            ]
            for name, trials in results.items()
        },
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(f"\nwrote {path}")
