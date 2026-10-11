#!/usr/bin/env python3
"""Understory - point it at a bird, keep your phone in your pocket.

    identify : BirdNET (open model, TFLite, runs on the CPU - no GPU needed)
    narrate  : Gemma 3 1B (open weights, served locally by Ollama)

No cloud, no API key, no signal required. Nothing you record leaves the
machine, and it all keeps working in a valley with no bars.

    ./understory.py listen --seconds 12 --lat 52.52 --lon 13.40
    ./understory.py id robin.mp3 --lat 52.52 --lon 13.40
    ./understory.py id mote.wav --offline      # prove it never touches the network
    ./understory.py notes                       # the log it left behind
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
import wave
from contextlib import contextmanager
from pathlib import Path

SAMPLE_RATE = 48000
HOME = Path(os.environ.get("UNDERSTORY_HOME", Path.home() / ".understory"))
NOTES = HOME / "fieldnotes"
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("UNDERSTORY_MODEL", "understory-gemma")

# Scoped on purpose. A 1B model on a CPU is fluent but shallow: asked for plumage
# it invents colours, asked for a song it invents calls. Asked only where the bird
# lives and what it is doing it stays honest. Markings belong in a field guide.
PROMPT = """A birder has just heard {heard} and is looking up at it right now, in a wood or a garden.
Write two short sentences, plain text, no lists, no title, no opener:
1) where this bird usually is and what habitat it favours,
2) what it is likely to be doing at this moment.
Use only what you are confident is true of this species. Do not describe its colour,
its markings or its song - the birder can see and hear it, and markings belong in a field guide."""


@contextmanager
def quiet_stderr():
    """Hide TFLite/XNNPACK C-level chatter; restored even if the block throws."""
    saved = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(saved, 2)
        os.close(devnull)
        os.close(saved)


@contextmanager
def offline_guard():
    """Refuse any network connection except loopback. Makes 'offline' checkable."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def allowed(addr):
        host = addr[0] if isinstance(addr, tuple) else ""
        return host in ("127.0.0.1", "::1", "localhost")

    def guard(sock, addr):
        if not allowed(addr):
            raise OSError(f"Understory is offline: blocked connection to {addr!r}")
        return real_connect(sock, addr)

    def guard_ex(sock, addr):
        if not allowed(addr):
            raise OSError(f"Understory is offline: blocked connection to {addr!r}")
        return real_connect_ex(sock, addr)

    socket.socket.connect, socket.socket.connect_ex = guard, guard_ex
    try:
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex = real_connect, real_connect_ex


def record_wav(seconds: int, out: Path) -> None:
    """Grab the microphone with ALSA's arecord. Works with no internet."""
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["arecord", "-q", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1",
             "-d", str(seconds), str(out)],
            check=True,
        )
    except FileNotFoundError:
        raise SystemExit("arecord not found - install alsa-utils, or use `id <file>` "
                         "with a recording from your phone.")


def identify(path: Path, lat=None, lon=None, min_conf=0.25):
    """Run BirdNET locally and collapse the per-window hits into one row per species."""
    from birdnetlib import Recording
    from birdnetlib.analyzer import Analyzer

    # birdnetlib is chatty on stdout; TFLite logs to stderr. A field tool should be quiet.
    with contextlib.redirect_stdout(io.StringIO()), quiet_stderr():
        analyzer = Analyzer()
        rec = Recording(analyzer, str(path), lat=lat, lon=lon, min_conf=min_conf)
        rec.analyze()
    return collapse(rec.detections)


def collapse(detections):
    """BirdNET reports one hit per 3s window; keep the best hit per species."""
    best = {}
    for d in detections:
        key = d["common_name"]
        row = best.setdefault(
            key,
            {"common_name": key, "scientific_name": d["scientific_name"],
             "confidence": 0.0, "hits": 0, "at": d["start_time"]},
        )
        row["hits"] += 1
        if d["confidence"] > row["confidence"]:
            row["confidence"] = d["confidence"]
            row["at"] = d["start_time"]
    return sorted(best.values(), key=lambda r: -r["confidence"])


def narrate(species: list[dict], model: str | None = None, timeout=300) -> str:
    """Ask the local Gemma for a field note. Pure loopback - no cloud call."""
    heard = ", ".join(f"{s['common_name']} ({s['confidence']:.0%})" for s in species[:3])
    body = json.dumps({
        "model": model or MODEL,
        "prompt": PROMPT.format(heard=heard),
        "stream": False,
        "keep_alive": "30m",  # a walk is longer than Ollama's default 5m unload
        "options": {"num_predict": 130, "temperature": 0.2},
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = json.load(resp).get("response", "").strip()
    # small models love an opener; drop it so the card starts on the bird
    return re.sub(r"^(certainly|sure|of course|absolutely)\b[!,.:]*\s*", "", text,
                  flags=re.I).strip()


def format_card(species: list[dict], note: str | None, offline: bool) -> str:
    stamp = dt.datetime.now().strftime("%H:%M")
    tag = "  [offline guard: on]" if offline else ""
    lines = [f"Understory  {stamp}{tag}"]
    if not species:
        lines.append("  Nothing bird-shaped in that clip. Try again quieter, or closer.")
        return "\n".join(lines)
    lines.append(f"  Heard: {species[0]['common_name']} ({species[0]['confidence']:.0%})")
    for s in species[1:3]:
        lines.append(f"         also {s['common_name']} ({s['confidence']:.0%})")
    if note:
        lines.append("")
        lines.append("  " + note.replace("\n", "\n  "))
        lines.append("")
        lines.append("  (AI field note - a hint to look, not a tick on a list.)")
    return "\n".join(lines)


def save_note(species: list[dict], note: str | None, source: str) -> Path:
    """Append to a dated markdown log so the reading happens off-trail, not on it."""
    NOTES.mkdir(parents=True, exist_ok=True)
    day = dt.date.today().isoformat()
    path = NOTES / f"{day}.md"
    if not path.exists():
        path.write_text(f"# Field notes, {day}\n")
    heard = ", ".join(f"{s['common_name']} ({s['confidence']:.0%})" for s in species) or "nothing"
    with path.open("a") as f:
        f.write(f"\n## {dt.datetime.now():%H:%M} - {heard}\n")
        f.write(f"source: {source}\n")
        if note:
            f.write(f"\n{note}\n")
    return path


def cmd_id(args) -> int:
    src = Path(args.audio).expanduser()
    if not src.exists():
        print(f"no such file: {src}", file=sys.stderr)
        return 2
    ctx = offline_guard() if args.offline else _null()
    with ctx:
        species = identify(src, lat=args.lat, lon=args.lon, min_conf=args.min_conf)
        note = None
        if species and not args.no_narrate:
            try:
                note = narrate(species, model=args.model)
            except (urllib.error.URLError, OSError) as e:
                print(f"(no field note: Gemma is not answering on {OLLAMA} - {e})",
                      file=sys.stderr)
                print("(start it with: ollama serve   [model: "
                      f"ollama create {MODEL} -f Modelfile])", file=sys.stderr)
    print(format_card(species, note, args.offline))
    if species:
        print(f"\n  logged -> {save_note(species, note, str(src))}")
    return 0


def cmd_listen(args) -> int:
    out = HOME / "clips" / f"{dt.datetime.now():%Y%m%d-%H%M%S}.wav"
    print(f"listening {args.seconds}s ... (quiet, slow, phone in pocket)")
    record_wav(args.seconds, out)
    with wave.open(str(out)) as w:
        print(f"captured {w.getnframes() / w.getframerate():.1f}s -> {out}")
    return cmd_id(argparse.Namespace(**{**vars(args), "audio": str(out)}))


def cmd_notes(args) -> int:
    files = sorted(NOTES.glob("*.md"), reverse=True) if NOTES.exists() else []
    if not files:
        print("no field notes yet. try: ./understory.py listen --seconds 12")
        return 0
    print(files[0].read_text() if args.last else "\n".join(str(f) for f in files))
    return 0


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def build_parser():
    p = argparse.ArgumentParser(prog="understory", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--lat", type=float, help="latitude, narrows the species list to what lives here")
        sp.add_argument("--lon", type=float, help="longitude")
        sp.add_argument("--min-conf", type=float, default=0.25, help="confidence floor (default 0.25)")
        sp.add_argument("--no-narrate", action="store_true", help="skip Gemma, identification only")
        sp.add_argument("--offline", action="store_true", help="hard-block non-loopback network")
        sp.add_argument("--model", default=None,
                        help=f"another local Gemma (default {MODEL}); "
                             "e.g. --model understory-gemma-4b for better notes, slower")
        return sp

    idp = common(sub.add_parser("id", help="identify an existing recording"))
    idp.add_argument("audio")
    idp.set_defaults(func=cmd_id)

    lp = common(sub.add_parser("listen", help="record from the mic, then identify"))
    lp.add_argument("--seconds", type=int, default=12)
    lp.set_defaults(func=cmd_listen)

    np = sub.add_parser("notes", help="show the field-note log")
    np.add_argument("--last", action="store_true", help="newest day only")
    np.set_defaults(func=cmd_notes)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
