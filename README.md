# TrailGuide

Point it at a bird. Keep your phone in your pocket.

TrailGuide listens to a bird, works out what it is with **BirdNET** (open model,
runs on the CPU), and has **Gemma 3 1B** (open weights, served locally by Ollama)
write you a short field note: what to look for, where to look, what it is doing.

Everything runs on your machine. **No API key, no account, and no internet** — it
keeps working in a valley with no bars, and the audio never leaves the device. A
`--offline` flag hard-blocks every non-loopback socket so you can watch it refuse
to phone home.

## Why it exists

Birding is the moment your hands should be free. The screen is the shortest part
of the experience: press one key outdoors, pocket the phone, and the note is
waiting in a markdown log when you get back to the car.

## Quickstart

```bash
./setup.sh                                        # once: python deps + both open models
.venv/bin/python trailguide.py listen --seconds 12
.venv/bin/python trailguide.py id recording.m4a --lat 52.52 --lon 13.40
.venv/bin/python trailguide.py id recording.m4a --offline   # prove it needs no network
.venv/bin/python trailguide.py notes --last                 # what it heard, off-trail
```

```
TrailGuide  06:41  [offline guard: on]
  Heard: European Robin (99%)
         also Eurasian Blue Tit (60%)

  Rusty-orange face and breast, thin dark legs. It sings from an exposed perch
  in the low understory, often before the sun is fully up; the song is a clear
  rippling warble with a short pause between phrases.

  logged -> ~/.trailguide/fieldnotes/2026-10-11.md
```

## How it works

```
mic ──► 48 kHz mono WAV ──► BirdNET (TFLite, 6,522 species, CPU) ──► top species
                                                                        │
                             Ollama ──► Gemma 3 1B ──► 70-word field note ┘
                                                                        │
                                          screen (one card) + markdown log
```

| Piece | What it is | Where it runs |
| --- | --- | --- |
| Identification | BirdNET GLOBAL 6K v2.4 (TFLite) | local CPU, ~1-4 s/clip |
| Field note | Gemma 3 1B Q4_K_M | local, Ollama, ~3 tok/s on 4 old CPU cores |
| Audio I/O | arecord + librosa/soundfile | local |
| Cloud | nothing | — |

`--no-narrate` skips Gemma for a fast identification-only run. If Ollama is not
running, TrailGuide still identifies the bird and tells you how to start Gemma.

## Tests

```bash
.venv/bin/python tests/test_trailguide.py
```

## Licenses

Code: MIT. Models are separate: BirdNET weights are **CC BY-NC-SA 4.0**
(non-commercial); Gemma 3 is under the **Gemma Terms of Use**. See `LICENSE`.
