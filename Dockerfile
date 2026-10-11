# Render demo image: the same BirdNET + Gemma chain as the CLI, behind Flask.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OLLAMA_MODELS=/models/ollama \
    UNDERSTORY_HOME=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsndfile1 ca-certificates curl zstd \
    && rm -rf /var/lib/apt/lists/*

# Ollama, local-only. The release bundle is ~2 GB and almost all of it is CUDA
# libs a Render box has no GPU for; the CPU-only files are ~60 MB. Dropping the
# GPU dirs keeps the image small and Ollama falls back to CPU (verified).
ARG OLLAMA_VERSION=v0.40.3
RUN curl -fsSL -o /tmp/ollama.tar.zst \
        "https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/ollama-linux-amd64.tar.zst" \
    && tar --zstd -xf /tmp/ollama.tar.zst -C /usr/local \
    && rm -rf /usr/local/lib/ollama/cuda_v12 /usr/local/lib/ollama/cuda_v13 \
              /usr/local/lib/ollama/vulkan /tmp/ollama.tar.zst

WORKDIR /app
COPY requirements.txt requirements-web.txt ./
RUN pip install -r requirements-web.txt

# Bake the open Gemma GGUF in at build time: the running service never downloads.
ARG GEMMA_URL=https://huggingface.co/ggml-org/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q4_K_M.gguf
RUN mkdir -p /models /data \
    && curl -L --fail --retry 3 -o /models/gemma.gguf "$GEMMA_URL"

COPY Modelfile.docker ./
RUN ollama serve & sleep 10 && ollama create understory-gemma -f /app/Modelfile.docker

COPY understory.py app.py ./
COPY samples ./samples

EXPOSE 10000
CMD ["sh", "-c", "ollama serve & exec gunicorn -k gthread -w 1 --threads 8 --timeout 900 -b 0.0.0.0:${PORT:-10000} app:app"]
