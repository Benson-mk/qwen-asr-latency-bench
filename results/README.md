# Recorded runs

One snapshot each, both recorded back to back on 2026-08-17 from Hong Kong so
they are comparable with each other — and with nothing else.

| file | route | realtime | flash-cold | flash-warm |
|---|---|---|---:|---:|
| `direct.json` | direct | 1968 ms | 12635 ms | 15345 ms |
| `proxy.json` | via local proxy | 1531 ms | 5731 ms | 8373 ms |

Median settle after speech end. Each file carries a `run` block naming its
route, models, audio and clip count, because the same code on the same audio
produces very different numbers by route.

## Read these as one sample, not as the answer

The ranking — realtime fastest, by several times — has held on every run so
far. The absolute numbers have not, and they move a lot:

| flash-cold median, direct route | when |
|---|---|
| 6247 ms | earlier run |
| 12635 ms | run recorded here |

Same code, same audio, same route, ~2x apart. Uplink throughput to the
DashScope endpoint swings hour to hour, and flash is exposed to it because it
uploads a whole sentence after speech ends. Anything you conclude about
absolute latency needs your own run, ideally several.

## Known artifact: truncated replies score as fast

A trial ends when the transcript stops changing. A backend that returns a
partial answer and then goes quiet is indistinguishable, to this harness, from
one that finished — and it scores *better* for having said less.

`proxy.json` has a clear instance: realtime clip 2 settled at **−542 ms** with
`少少。` where the sentence was `少少，三十七點八。`. A negative settle means
the transcript was final before the speaker stopped, which cannot be a real
response latency; it is the signature of an early stop.

So a fast settle is only meaningful next to the text it produced. Both files
keep the transcript on every trial for exactly this reason. Scoring accuracy
against a reference transcript would catch these automatically, and is the
obvious next thing this harness lacks.
