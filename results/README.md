# Recorded runs

| file | route | recorded (UTC) | realtime | flash-cold | flash-warm |
|---|---|---|---:|---:|---:|
| `direct.json` | direct | 2026-08-17 08:53 | 713 ms | 4295 ms | 3839 ms |
| `proxy.json` | via local proxy | 2026-08-17 06:50 | 1531 ms | 5731 ms | 8373 ms |

Median settle after speech end, 8 Cantonese sentences each, from Hong Kong.
Every file carries a `run` block naming its route, models, audio and clip
count, plus the full transcript of each trial.

## Do not compare the two files to each other

They were recorded **two hours apart**, so the difference between them mixes
route with whatever the network was doing at the time. Only the gap *within*
a file — between backends measured minutes apart on identical audio — is a
controlled comparison.

## The absolutes move a lot

Same command, same audio, same direct route:

| flash-cold median | recorded (UTC) | kept |
|---:|---|---|
| 6247 ms | ~06:20 | no, predates these files |
| 12635 ms | 06:44 | superseded `direct.json` |
| 4295 ms | 08:53 | current `direct.json` |

Three runs, a 3× spread. Uplink throughput to the DashScope endpoint swings
hour to hour, and flash is exposed to it because it uploads a whole sentence
once speech ends. Realtime overlaps its upload with speech, so it moves less.

Quote the ranking, not the milliseconds. If you need an absolute figure,
record several runs of your own at the hour you actually care about.

## Known artifact: truncated replies score as fast

A trial ends when the transcript stops changing. A backend that returns a
partial answer and then goes quiet is indistinguishable, to this harness, from
one that finished — and it scores *better* for having said less.

Both files show it. In `direct.json`, realtime ended clip 1 at
`…屙咗六七次，今次。` where flash heard `…今朝仲嘔吐咗兩次。`, and clip 8 at
`好冇明顯。` against `冇明顯反彈同。` — then took the win on latency.
`proxy.json` has the blatant case: realtime clip 2 settled at **−542 ms** with
`少少。` where the sentence was `少少，三十七點八。`. A negative settle means
the transcript was final before the speaker stopped, which cannot be a real
response latency; it is the signature of an early stop.

So a fast settle is only meaningful next to the text that produced it, which
is why every trial keeps its transcript. Scoring accuracy against a reference
would catch these automatically, and is the main thing this harness lacks.
