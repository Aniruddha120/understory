*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 1: Touch Grass](https://dev.to/challenges/hacktoberfest-week1-2026-10-05)*

## What I Built

**Understory** is a bird guide for the places where your phone gives up.

You point a microphone at a singing bird. It tells you what you are listening to using a model that runs *on the machine*, then writes a short field note: where the bird lives, and what it is probably doing right now. Then it gets out of the way.

The whole interaction is one press and one card. The note is appended to a plain markdown file, so the reading happens back at the car, not while the bird is still in front of you. **The screen is the shortest part of the walk.**

It is built for someone with an old laptop, no data signal, and no intention of uploading every recording of their local patch to somebody's cloud.

```
Understory  15:13  [offline guard: on]
  Heard: European Robin (99%)
         also Eurasian Blue Tit (60%)

  It is likely foraging for insects in a woodland area. It is probably
  searching for a mate or nesting material.

  (AI field note — a hint to look, not a tick on a list.)

  logged -> ~/.understory/fieldnotes/2026-10-11.md
```

## Demo

No deployed link, on purpose: there is nothing to deploy. A tool whose whole point is that it needs no server is best shown the way you would actually use it, so the demo below is a real run with the offline guard switched on.

![Understory identifying a European Robin offline, then proving the offline guard by passing its test suite](https://raw.githubusercontent.com/Aniruddha120/understory/main/demo.gif)

```console
$ understory.py id robin.mp3 --lat 52.52 --lon 13.40 --offline
Understory  15:13  [offline guard: on]
  Heard: European Robin (99%)
         also Eurasian Blue Tit (60%)

  It is likely foraging for insects in a woodland area. It is probably
  searching for a mate or nesting material.

  (AI field note — a hint to look, not a tick on a list.)

  logged -> ~/.understory/fieldnotes/2026-10-11.md

$ understory.py id greattit.ogg --lat 52.52 --lon 13.40 --no-narrate --offline
Understory  15:10  [offline guard: on]
  Heard: Great Tit (100%)

  logged -> ~/.understory/fieldnotes/2026-10-11.md

$ understory.py id quiet-room.wav --no-narrate --offline
Understory  15:11  [offline guard: on]
  Nothing bird-shaped in that clip. Try again quieter, or closer.
```

Identification alone is **~6 seconds** on a 4-core CPU. The written note adds 30–45 seconds, which is exactly why the phone goes in the pocket: you watch the bird while it writes, and read the card when you are done.

## Code

{% embed https://github.com/Aniruddha120/understory %}

MIT licensed. 285 lines of Python, 61 lines of tests, no framework, no cloud SDK. `./setup.sh` fetches both open models once; after that it runs with the wifi off.

## How I Built It

Two open models, chained, both local:

| Job | Model | Where it runs |
| --- | --- | --- |
| Identification | BirdNET GLOBAL 6K v2.4 (6,522 species) | TensorFlow Lite, CPU, 1–4 s/clip |
| Field note | Gemma 3 1B (Q4_K_M) | Ollama, CPU, ~3 tok/s |

The pipeline is deliberately boring, because the interesting part is what it *doesn't* do:

```
mic ──► 48 kHz mono WAV ──► BirdNET ──► top species ──► Gemma 3 ──► card + markdown log
                                                             │
                                                  no network, ever
```

BirdNET reports one hit per 3-second window, so `collapse()` keeps the best hit per species and counts the rest. A bird that sings four times across a minute is more convincing than one that appears once.

**The offline guard is the part I care about.** "It works offline" is a claim; I wanted it to be a *test*. `--offline` swaps out `socket.connect` and `socket.connect_ex` for the duration of the run and refuses anything that is not loopback:

```python
@contextmanager
def offline_guard():
    real_connect = socket.socket.connect

    def guard(sock, addr):
        if addr[0] not in ("127.0.0.1", "::1", "localhost"):
            raise OSError(f"Understory is offline: blocked connection to {addr!r}")
        return real_connect(sock, addr)

    socket.socket.connect = guard
    try:
        yield
    finally:
        socket.socket.connect = real_connect
```

Loopback stays open because Gemma is served on `127.0.0.1`. Everything else — a telemetry ping, a model download, an accidental analytics import — dies with a visible error instead of quietly succeeding. The test suite asserts both halves: a real loopback connection succeeds, and a connection to `1.1.1.1:443` raises.

Two things bit me on the way, and both are arguments for open tooling in miniature:

1. **Ollama refused to pull Gemma.** My installed version was too old and the registry answered `412 … requires a newer version of Ollama`. The "upgrade" was a 1.4 GB download. The lazy fix was to skip the registry: fetch the GGUF from Hugging Face and `ollama create` it from a Modelfile. Ollama autodetected the `gemma3-instruct` template and it just worked. The model is a file. Nothing got to tell me no.
2. **`tflite-runtime` blew up under NumPy 2.** `AttributeError: _ARRAY_API not found`, because the runtime is compiled against NumPy 1.x. Pinning `numpy<2` fixed it — two lines in `requirements.txt` and one confused afternoon.

## Why Does Open Innovation Matter?

Four things here were only possible because every piece is open.

**It runs where the birds are.** No signal is the premise, not a limitation. A cloud API is not slow in a valley — it is absent. BirdNET on the CPU turns a dead zone into a working tool. This is the whole reason the app is shaped the way it is: the screen disappears because nothing about the interaction needs a network round-trip.

**Nothing leaves the machine.** Bird recordings are location data. What you recorded, and where, reveals your patch, your routine, and the hours your house is empty. With a local model I am not promising to delete your audio later; it was never sent. That is a structurally different guarantee from a privacy policy, and it is the one a birder would actually want.

**It costs nothing to run, forever.** No tokens, no quota, no per-request billing. I can leave it listening for an hour, or run it every morning for a year, and the cost is identical: the electricity. Metered APIs quietly teach you not to use your own tool — you start rationing the thing that was supposed to be fun. This one costs the same when you use it badly as when you use it well.

**Every layer is swappable.** BirdNET is one `.tflite` file. Gemma is one `.gguf` file. That is not a slogan; it is the reason the section below exists. When the small model got the field notes wrong, I did not file a ticket and wait for a release note. I changed the prompt, re-ran it, and then changed the model — in the same afternoon.

```bash
# same app, a different local Gemma, no code change:
understory.py listen --seconds 12 --model understory-gemma-4b
```

## Where the Open Model Was Wrong

I asked Gemma 3 1B to describe a Great Tit's markings. It wrote:

> "a small, dark greyish-brown plumage with a distinctive white stripe across the chest … a short, repetitive 'cheep-cheep' song."

That is wrong on both counts. A Great Tit has a black head, white cheeks, and a yellow breast split by a black stripe, and its song is a ringing two-note phrase, not a cheep. A 1-billion-parameter model on a laptop CPU is a fluent writer and a poor ornithologist. I had asked it for *recalled facts*, which is the one thing it cannot do reliably.

The fix was not a bigger model. It was to stop asking.

I checked that claim rather than trusting it. I swapped the 1B for **Gemma 3 4B** — one GGUF file, one command, no code change — and the prose really did get better:

> "European Robins typically favour woodland edges and gardens with dense shrubbery. The bird is likely searching for invertebrates amongst the foliage."

That is a *better sentence*, and it is still only habitat and activity, so the scoping holds as the model grows. But it took **four minutes and twenty seconds** to write one note on this CPU, against about forty seconds for the 1B. A four-minute wait at the trailhead is not a field tool. The bigger model fixed the prose and broke the walk, which is the whole lesson: on a laptop in a hedgerow, a bigger model is a slower model before it is a smarter one. Money spent on parameters buys words, not time.

The prompt now asks only for where the bird lives and what it is probably doing — and explicitly forbids colour, markings, and song, because **the birder can see and hear the bird, and markings belong in a field guide.** I also added a confidence gate: below 50% the tool shows the hit but writes *no* note, so a coin-flip never gets dressed up in confident prose.

The notes got shorter, blander, and true. That is the right trade for a tool you are holding up at a bird: a bland true hint tells you where to look, and a confident false one sends you looking for a bird that is not there.

## My Agent Session

Built with OpenCode. The session is saved here:

{% agent_session 749 %}

It includes the smaller fights too: the offline guard's first version crashing because `socket.socket.connect` is assigned on the class and therefore called with `self`; the NumPy ABI crash; and the moment a semantic search of the challenge feed showed me that "offline bird identifier" was already the most crowded idea of the week — which is why the project is called Understory and not Trail-something.

## Prize Categories

**Best Use of Gemma** — Gemma 3 is the half of this project that turns a species label into something a person can act on, and it runs entirely offline through Ollama on CPU. The failure above is part of why I am entering it here: the interesting engineering with a small open model is not calling it, it is deciding what you can honestly ask it — and then refusing to ask it anything else.

## Thanks

Sample recordings used while testing, credited under their Creative Commons licences:

- European Robin, [XC509375](https://www.xeno-canto.org/509375) — Marie-Lan Taÿ Pamart, CC BY-SA 4.0
- Common Blackbird, [XC1059970](https://xeno-canto.org/1059970) — Diana Tudor, CC BY 4.0
- Great Tit — Vladimir Yu. Arkhipov, CC BY-SA 3.0

BirdNET weights are CC BY-NC-SA 4.0 (non-commercial); Gemma 3 is used under the Gemma Terms of Use. The code is MIT.
