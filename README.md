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

8 Cantonese sentences (1.5–6.3 s), 16 kHz mono, replayed at 1× wall-clock pace.
Measured from Hong Kong through a local proxy (see [Caveats](#caveats)).

| backend | settle after speech end (median) | first token (median) | vs fastest |
|---|---|---|---|
| `realtime` | **677 ms** | −1187 ms | — |
| `flash-cold` | 3154 ms | 3154 ms | 4.7× slower |
| `flash-warm` | 3210 ms | 3210 ms | 4.7× slower |

**Realtime answers ~4.7× sooner, and starts answering before you finish.**
Its first token lands at a *negative* offset — a median of 1.2 s before speech
end, and 5.5 s before it on the longest sentence — because it transcribes
mid-utterance. Flash cannot beat its own endpointer: nothing is sent until the
VAD is convinced the sentence is over.

Two numbers are reported because one would mislead:

- **first token** — when text first appears. Negative means it appeared while
  the speaker was still talking. Not comparable across the two designs.
- **settle** — when the transcript stops changing. This is the honest
  cross-backend comparison, and the headline above.

Realtime trades a little accuracy for the latency: on these clips it produced
`唞` for `賭`, and dropped a word or two that flash caught.

### Where flash's 3.2 s goes

| component | ms |
|---|---|
| local VAD hangover (0.4 s silence + 0.25 s padding) | ~650 |
| HTTP round trip (upload, inference, response) | ~2500 |

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
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

cp .env.example .env      # add your DASHSCOPE_API_KEY
.venv/bin/python bench.py
```

The silero VAD model downloads automatically on first run.

```bash
python bench.py --clips 8                              # all three backends
python bench.py --backends realtime --clips 20         # one backend, more samples
python bench.py --audio path/to/your.wav               # 16 kHz mono PCM16
python tests/test_transcript.py                        # unit tests
```

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

- **Every measurement includes a local proxy** (`DASHSCOPE_PROXY`), which costs
  ~1.9 s on a bare connect. Absolute numbers will be lower on a direct
  China-region connection; the *ratio* between backends is what transfers.
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

## License

MIT
