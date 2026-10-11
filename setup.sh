#!/usr/bin/env bash
# One-time setup. Needs the internet ONCE, to fetch the two open models.
# After this, `trailguide listen` works with the wifi off.
set -euo pipefail
cd "$(dirname "$0")"

command -v arecord >/dev/null || echo "note: arecord missing (apt install alsa-utils) - you can still use 'id <file>'"
command -v ollama  >/dev/null || { echo "install Ollama first: https://ollama.com/download"; exit 1; }

# 1. Python env + the BirdNET model (the model ships inside the birdnetlib wheel).
if command -v uv >/dev/null; then
  uv venv --python 3.11 .venv 2>/dev/null || true
  uv pip install --python .venv/bin/python -r requirements.txt
else
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

# 2. Gemma 3 1B weights (~770 MB) as a plain GGUF, imported into Ollama.
mkdir -p models
GGUF=models/gemma-3-1b-it-Q4_K_M.gguf
[ -f "$GGUF" ] || curl -L --fail --retry 3 -o "$GGUF" \
  "https://huggingface.co/ggml-org/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q4_K_M.gguf"

ollama serve >/dev/null 2>&1 & sleep 3   # no-op if already running
ollama create trailgemma -f Modelfile

echo
echo "ready. point it at a bird:"
echo "  .venv/bin/python trailguide.py listen --seconds 12"
echo "  .venv/bin/python trailguide.py id my-recording.m4a --offline"
