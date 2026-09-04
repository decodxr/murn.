# murn.

**murn.** is a local-first AI agent with memory, tools, persistent conversations, streaming, image generation, and local voice.

Current stack:

- **Ollama** — local language model (`llama3.1:8b` by default)
- **EmbeddingGemma via Ollama** — semantic memory embeddings
- **Obsidian** — durable Markdown memory
- **SQLite** — conversation sessions and semantic-memory index
- **ComfyUI** — local image generation
- **whisper.cpp** — local speech-to-text
- **Piper** — local text-to-speech
- **FastAPI** — local API
- **Orbital** — optional browser bridge scaffold

## Architecture

```text
                  murn.
                    |
        +-----------+-----------+
        |           |           |
      Ollama      SQLite       tools
        |         /     \      /   \
      Llama   sessions vectors memory ComfyUI
        ^                   |       |
        |                Obsidian images
        |
   whisper.cpp
        ^
        |
 microphone/audio

 murn. response -> Piper -> WAV
```

## Quick start

Clone and create the local environment:

```bash
git clone https://github.com/decodxr/murn..git ~/Projects/murn
cd ~/Projects/murn
python -m venv .venv
```

fish:

```fish
source .venv/bin/activate.fish
```

Install the core:

```bash
python -m pip install -e .
cp .env.example .env
```

For local TTS support, install the voice extra instead:

```bash
python -m pip install -e '.[voice]'
```

Pull the default Ollama models:

```bash
ollama pull llama3.1:8b
ollama pull embeddinggemma
```

Configure your Obsidian vault, ComfyUI workflow, and optional voice paths in `.env`.

Start murn.:

```bash
uvicorn murn.main:app --reload --host 127.0.0.1 --port 7331
```

API docs:

```text
http://127.0.0.1:7331/docs
```

## Health

```bash
curl http://127.0.0.1:7331/health
```

The response includes status for Ollama, embeddings, ComfyUI, STT, and TTS.

## Chat and sessions

Normal chat:

```bash
curl -X POST http://127.0.0.1:7331/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello murn."}'
```

The response includes a `session_id`. Reuse it in later requests to continue the same persistent conversation.

List sessions:

```bash
curl http://127.0.0.1:7331/v1/sessions
```

Streaming chat:

```bash
curl -N -X POST http://127.0.0.1:7331/v1/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"Explain what you can do."}'
```

Streaming events include `session`, `token`, `tool_start`, `tool_result`, `done`, and `error`.

## Semantic Obsidian memory

Build/update the semantic index:

```bash
curl -X POST http://127.0.0.1:7331/v1/memory/reindex
```

Search by meaning rather than exact wording:

```bash
curl --get http://127.0.0.1:7331/v1/memory/search \
  --data-urlencode 'q=what browser am I developing?'
```

Obsidian stays the source of truth. The local vector cache lives in `.murn/memory_embeddings.db` and can be rebuilt.

## Image generation

After exporting and configuring a ComfyUI API workflow:

```bash
curl -X POST http://127.0.0.1:7331/v1/images/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"a quiet rainy street at night"}'
```

The agent can also call image generation as a tool from `/v1/chat`.

## Local voice

murn. v0.4 adds:

```text
POST /v1/audio/transcribe
POST /v1/audio/speech
GET  /v1/audio/files/{filename}
POST /v1/voice/chat
```

Full Arch Linux setup, model downloads, configuration, and curl tests are in [`docs/voice.md`](docs/voice.md).

The full voice path is:

```text
audio -> ffmpeg -> whisper.cpp -> murn. -> Piper -> WAV
```

## Current safety model

murn. does **not** give the language model arbitrary shell access. Capabilities are exposed through explicit providers/tools so filesystem, terminal, Orbital, vision, and other integrations can each receive their own permissions and limits.

## Roadmap

- real-time microphone/VAD voice mode
- streaming TTS while the model is still answering
- Orbital native AI bridge
- vision model support
- desktop/chat UI
- controlled filesystem and terminal tools
