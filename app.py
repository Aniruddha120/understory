#!/usr/bin/env python3
"""Understory - browser demo.

Same chain as the CLI: BirdNET identifies, Gemma 3 1B writes the field note.
The note streams in token by token, so you watch it being written while the
bird is still in front of you (and so the request never sits idle long enough
for a proxy to time it out).

Honesty note: this page runs on a server, so a clip you upload here does travel
over the network. The CLI is the real product - it keeps the audio on your
machine. What this demo shows is that the same offline code path runs with no
cloud API behind it.
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from pathlib import Path

from flask import Flask, Response, request, send_file

from understory import (CONFIDENT, MODEL, OLLAMA, PROMPT, clean_note, identify,
                        offline_guard, save_note)

app = Flask(__name__)
SAMPLE_DIR = Path(__file__).parent / "samples"
MAX_BYTES = 25 * 1024 * 1024  # a field recording, not a dataset


@app.get("/")
def index():
    return PAGE


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/samples/<name>")
def sample(name):
    """Bundled clips (CC-licensed, credited in the post) for a one-click demo."""
    path = (SAMPLE_DIR / name).resolve()
    if path.parent != SAMPLE_DIR.resolve() or not path.exists():
        return "no such sample", 404
    return send_file(path)


def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj) + "\n\n"


def _stream_note(species: list[dict]):
    """Ask the local Gemma and yield the note one token at a time."""
    heard = ", ".join(f"{s['common_name']} ({s['confidence']:.0%})" for s in species[:3])
    body = json.dumps({
        "model": MODEL,
        "prompt": PROMPT.format(heard=heard),
        "stream": True,
        "keep_alive": "30m",
        "options": {"num_predict": 130, "temperature": 0.2},
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        for line in resp:
            if not line.strip():
                continue
            chunk = json.loads(line)
            if chunk.get("response"):
                yield chunk["response"]
            if chunk.get("done"):
                break


@app.post("/identify")
def identify_route():
    up = request.files.get("audio")
    if up is None:
        return {"error": "no audio uploaded"}, 400
    data = up.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return {"error": "clip too large (25 MB max)"}, 413

    suffix = Path(up.filename or "clip.wav").suffix or ".wav"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(data)
    tmp.close()

    try:
        lat = float(request.form["lat"]) if request.form.get("lat") else None
        lon = float(request.form["lon"]) if request.form.get("lon") else None
    except ValueError:
        lat = lon = None

    # ponytail: one global guard is fine at demo scale; per-request would need
    # care because offline_guard() patches socket globally.
    guard = offline_guard() if os.environ.get("UNDERSTORY_OFFLINE", "1") == "1" else _null()

    def generate():
        try:
            with guard:
                species = identify(Path(tmp.name), lat=lat, lon=lon)
                yield _sse({"species": species})
                if not species:
                    yield _sse({"done": True})
                    return
                if species[0]["confidence"] < CONFIDENT:
                    # same gate as the CLI: never narrate a coin-flip
                    yield _sse({"skipped": True, "confidence": species[0]["confidence"]})
                    yield _sse({"done": True})
                    return
                parts = []
                for token in _stream_note(species):
                    parts.append(token)
                    yield _sse({"token": token})
                note = clean_note("".join(parts))
                yield _sse({"final": note})  # the tidy card, once the raw stream is done
            try:
                save_note(species, note or None, "web demo")
            except (OSError, UnboundLocalError):
                pass
            yield _sse({"done": True})
        except Exception as exc:  # keep the stream legible instead of dying mid-note
            yield _sse({"error": f"{type(exc).__name__}: {exc}"})
            yield _sse({"done": True})
        finally:
            os.unlink(tmp.name)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Understory - identify a bird with no signal</title>
<style>
  :root { --bg:#0b1610; --fg:#d6ecda; --dim:#7a9e80; --green:#7ed68c; --amber:#e8c478; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:16px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace; }
  main { max-width:760px; margin:0 auto; padding:40px 20px 80px; }
  h1 { font-size:1.4rem; margin:0 0 4px; }
  .sub { color:var(--dim); margin:0 0 28px; }
  .row { display:flex; gap:10px; flex-wrap:wrap; margin:14px 0 26px; }
  button,label.btn { background:#12291c; color:var(--green); border:1px solid #1e4630;
         border-radius:8px; padding:9px 14px; font:inherit; cursor:pointer; }
  button:hover,label.btn:hover { background:#173522; }
  button:disabled { opacity:.5; cursor:default; }
  input[type=file] { display:none; }
  #out { background:#08120c; border:1px solid #16301f; border-radius:10px;
         padding:18px; min-height:150px; white-space:pre-wrap; }
  .heard { color:var(--green); }
  .dim { color:var(--dim); }
  #status { color:var(--dim); margin:10px 0 0; min-height:1.4em; }
  .spin::after { content:""; animation:d 1.2s steps(4,end) infinite; }
  @keyframes d { 0%{content:""} 25%{content:"."} 50%{content:".."} 75%{content:"..."} }
  footer { color:var(--dim); font-size:.82rem; margin-top:34px; border-top:1px solid #16301f; padding-top:16px; }
  a { color:var(--green); }
</style></head><body><main>
<h1>Understory <span class="dim">- point it at a bird, keep your phone in your pocket</span></h1>
<p class="sub">BirdNET listens, Gemma&nbsp;3&nbsp;1B writes the note. Both run open-weight on the
server's CPU, no cloud API.</p>

<div class="row">
  <button data-sample="robin.mp3">European Robin sample</button>
  <button data-sample="greattit.ogg">Great Tit sample</button>
  <label class="btn">Upload a recording<input type="file" id="file" accept="audio/*"></label>
</div>

<div id="out"><span class="dim">Pick a sample or upload a clip. The note is written live, one word at a time.</span></div>
<p id="status"></p>

<footer>
This demo runs the <em>same</em> code as the CLI, on a server, so an uploaded clip does travel
over the network. The real thing is the <a href="https://github.com/Aniruddha120/understory">CLI</a>:
it keeps your audio on your own machine with no signal at all.
Notes are a hint to look, not a tick on a list. Sample audio credited under CC in the repo.
</footer>
</main>
<script>
const out = document.getElementById('out');
const status = document.getElementById('status');

async function run(formData) {
  out.textContent = '';
  status.className = 'spin';
  status.textContent = 'BirdNET is identifying, then Gemma writes';
  let wrote = false;
  const res = await fetch('/identify', { method:'POST', body: formData });
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream:true });
    let i;
    while ((i = buf.indexOf('\\n\\n')) >= 0) {
      const frame = buf.slice(0, i); buf = buf.slice(i + 2);
      if (!frame.startsWith('data: ')) continue;
      handle(JSON.parse(frame.slice(6)));
    }
  }
  status.className = '';
  status.textContent = 'logged to the field-note file.';

  function handle(m) {
    if (m.species) {
      status.textContent = 'Gemma is writing the note';
      if (!m.species.length) { out.textContent = 'Nothing bird-shaped in that clip.'; return; }
      let t = 'Heard: ' + m.species[0].common_name +
              ' (' + Math.round(m.species[0].confidence * 100) + '%)';
      m.species.slice(1,3).forEach(s => t += '\\nalso ' + s.common_name +
              ' (' + Math.round(s.confidence * 100) + '%)');
      out.textContent = t + '\\n\\n';
    }
    if (m.skipped) out.textContent += '\\n\\n(only ' + Math.round(m.confidence*100) +
        '% - too uncertain to write about, so it stays a guess.)';
    if (m.token) { wrote = true; out.textContent += m.token; }
    if (m.error) { out.textContent += '\\n\\n[' + m.error + ']'; }
    if (m.done && wrote) out.textContent +=
        '\\n\\n(AI field note - a hint to look, not a tick on a list.)';
  }
}

document.querySelectorAll('button[data-sample]').forEach(b => {
  b.onclick = async () => {
    const blob = await (await fetch('/samples/' + b.dataset.sample)).blob();
    const fd = new FormData();
    fd.append('audio', blob, b.dataset.sample);
    run(fd);
  };
});

document.getElementById('file').onchange = (e) => {
  const fd = new FormData();
  fd.append('audio', e.target.files[0], e.target.files[0].name);
  run(fd);
};
</script></body></html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), threaded=True)
