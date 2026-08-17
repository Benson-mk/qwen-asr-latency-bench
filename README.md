# qwen-asr-latency-bench

How long does Qwen3-ASR make you wait after you stop talking?

This measures one interval, the only one a speaker actually feels:

```
        ... speech ...│ silence ────────────────────────
                      │
              speech end          transcript stops changing
                      └──────── settle ────────┘
```

Two DashScope backends, same sentences, same clock:

- **`qwen3-asr-flash`** — a file-in / text-out HTTP endpoint. Streaming has to be
  simulated: a local VAD waits for a pause, cuts a sentence, and uploads it.
- **`qwen3-asr-flash-realtime`** — a WebSocket that transcribes while you speak
  and endpoints upstream (`server_vad`).

## Results

8 Cantonese sentences (1.5–6.3 s), 16 kHz mono, replayed at 1× wall-clock pace,
measured from Hong Kong. Median settle after speech end, per recorded run in
[`results/`](results/README.md):

| backend | [direct](results/direct.json) | [via proxy](results/proxy.json) |
|---|---:|---:|
| `realtime` | **713 ms** | **1531 ms** |
| `flash-cold` | 4295 ms | 5731 ms |
| `flash-warm` | 3839 ms | 8373 ms |

These two runs are **two hours apart**, so read each column on its own. The gap
between backends within a column is the finding; the difference between the
columns is mostly the hour, not the route.

**Realtime wins by several times in every run.** That ordering is the durable
result. The absolute numbers are not: repeated runs of the identical command
have put flash-cold anywhere between 3.2 s and 12.6 s, because upload
throughput to the endpoint swings hour to hour.

Flash is exposed to that swing and realtime mostly is not, which is the
mechanism behind the gap. Flash uploads a whole sentence *after* speech ends,
so every byte of transfer lands inside the measured window; realtime dribbles
small frames while the speaker is still talking, overlapping transfer with
speech. Same bytes, but only one of the two makes you wait for them.

Take the ranking; measure your own absolutes. See
[results/README.md](results/README.md) for how far these move, and for a known
artifact where a truncated reply scores as a fast one.

**Realtime answers ~6× sooner, and starts answering before you finish.**
Its first token lands at a *negative* offset — a median of 0.8 s before speech
end, and 5.0 s before it on the longest sentence — because it transcribes
mid-utterance. Flash cannot beat its own endpointer: nothing is sent until the
VAD is convinced the sentence is over.

Two numbers are reported because one would mislead:

- **first token** — when text first appears. Negative means it appeared while
  the speaker was still talking. Not comparable across the two designs.
- **settle** — when the transcript stops changing. This is the honest
  cross-backend comparison, and the headline above.

**Realtime buys that speed with accuracy, and the harness does not charge it
for that.** In the direct run it ended clip 1 at `今次。` where flash heard
`今朝仲嘔吐咗兩次。`, and returned `好冇明顯。` against flash's
`冇明顯反彈同。`. It also produced `shot` for `sharp`.

A backend that stops early looks *faster* here, because settle only asks when
the text stopped changing, never whether it was right. Read every latency next
to the transcript beside it — both result files keep the text for exactly this
reason. Scoring against a reference transcript is the obvious missing piece.

### Where flash's latency goes

| component | ms |
|---|---|
| local VAD hangover (0.4 s silence + 0.25 s padding) | ~650, fixed |
| HTTP round trip (upload, inference, response) | 1400–12000, your network |

The VAD hangover is fixed; the round trip is whatever your uplink gives you.
Realtime pays the same upload but overlaps it with speech instead of waiting
for the sentence to end.

### Connection reuse

`flash-cold` opens a fresh TLS connection per segment; `flash-warm` reuses one
pooled client. In the table above they tie — but that is a property of the
*schedule*, not of the technique. Requests here are ~8 s apart, by which point
the upstream has closed the idle connection and the handshake is paid again:

| gap between requests | median HTTP RTT |
|---|---|
| 0.3 s | 1390 ms |
| 8.0 s | 2944 ms |

So pooling is worth ~1.5 s per request **in continuous dictation**, and nothing
at all in a slow back-and-forth conversation. Reproduce with
`python bench.py --backends flash-cold flash-warm --pause 0.3`.

## Run it

```bash
git clone https://github.com/Benson-mk/qwen-asr-latency-bench
cd qwen-asr-latency-bench

uv sync                                  # or: python3 -m venv .venv &&
source .venv/bin/activate                #     .venv/bin/pip install -r requirements.txt

cp .env.example .env      # add your DASHSCOPE_API_KEY
python bench.py
```

The silero VAD model downloads automatically on first run.

<details>
<summary><code>ImportError: Library not loaded: @rpath/libonnxruntime.dylib</code></summary>

The native libraries live in a companion package, `sherpa-onnx-core`. The
`sherpa-onnx` **sdist** does not declare that dependency (its wheels do), so a
resolver that builds from the sdist installs an extension module with nothing
to link against. Both `uv sync` and the `requirements.txt` above pin it
explicitly; if you installed some other way, `uv add sherpa-onnx-core` or
`pip install sherpa-onnx-core` fixes it.

</details>

```bash
python bench.py --clips 8                              # all three backends
python bench.py --backends realtime --clips 20         # one backend, more samples
python bench.py --audio path/to/your.wav               # 16 kHz mono PCM16
python bench.py --proxy                                # route via DASHSCOPE_PROXY
python bench.py --proxy http://127.0.0.1:10808         # route via a specific proxy
python tests/test_transcript.py                        # unit tests
```

Connections go **direct by default**. `DASHSCOPE_PROXY` is never applied on its
own — a proxy adds a hop to every measurement, so it takes an explicit
`--proxy` to opt in.

Per-trial timings land in `results.json`.

## Method

Fidelity to a live microphone is what makes the numbers mean anything:

- **Audio is paced at 1×.** Uploading a 3-second sentence in one burst would
  make any backend look fast; no microphone can do that.
- **HTTP requests run off the audio path.** A microphone does not stop
  capturing while a request is in flight, so the pacer never blocks on one.
- **Silence is appended after speech, and each backend endpoints itself.**
  Nothing tells a backend the sentence is over — that latency is the point.
- **A trial ends on quiescence,** once the transcript has been unchanged for
  2.5 s, not on a fixed timer that could truncate a slow reply.
- **Repeated identical transcripts do not extend settle time,** because
  re-sending the same text changes nothing the speaker can see.
- **Clips are cut at natural silences** by the same VAD the flash path uses,
  and trimmed to speech only, so speech end is a timestamp the harness controls.

## Caveats

- **Your network dominates the absolute numbers.** The two tables above differ
  by 2–3× on identical audio and code, purely by route. The ranking held on
  both, but do not quote a millisecond figure measured on someone else's link.
- Sample size is 8 sentences on one network from one location. Rerun it on
  yours — that is what the repo is for.
- Audio is TTS-generated synthetic clinical dialogue. No real patient data.

## Layout

```
bench.py                     CLI
qwenbench/config.py          settings from environment
qwenbench/audio.py           wav loading, VAD sentence cutting
qwenbench/session.py         1x pacing, event timing, settle rule
qwenbench/transcript.py      overlap-aware segment merging
qwenbench/report.py          statistics and tables
qwenbench/backends/flash.py      local VAD + HTTP per segment
qwenbench/backends/realtime.py   streaming WebSocket
```

