# murn.

**murn.** is a local-first personal AI agent with memory, tools, saved conversations, streaming, image generation, local voice, a desktop interface, and a voice-only phone companion.

Current stack:

- **Ollama** — local language model (`llama3.1:8b` by default)
- **EmbeddingGemma via Ollama** — semantic memory embeddings
- **Obsidian** — durable Markdown memory
- **SQLite** — saved desktop conversations and semantic-memory index
- **ComfyUI** — local image generation
- **whisper.cpp** — local speech-to-text
- **Piper** — local text-to-speech
- **FastAPI** — local API + UI server
- **Orbital** — optional browser bridge scaffold

## v0.5 UI

murn. now ships the black / white / violet interface directly from the backend — no Node build step and no cloud frontend.

```text
Desktop UI   http://127.0.0.1:7331/
Phone UI     http://127.0.0.1:7331/mobile
API docs     http://127.0.0.1:7331/docs
```

### Desktop

The desktop interface includes:

- saved conversations in a left sidebar
- returning to any previous conversation
- search + local pinning
- streaming responses
- visible tool cards
- ComfyUI image results inside chat
- microphone input + Piper playback
- live backend/model/voice status

### Phone companion

The phone interface is intentionally voice-only. It sends audio to the PC, lets the PC run whisper.cpp → murn. → Piper, and plays the returned voice on the phone.

Phone interactions use:

```text
POST /v1/voice/remote
```

and are **ephemeral**: they are not inserted into the saved desktop conversation database.

The mobile UI has the exact runtime states:

```text
STANDBY
LISTENING
TRANSCRIBING
THINKING
SPEAKING
```

It supports hold-to-talk and hands-free auto listening with local voice activity detection.

Full desktop + phone + LAN + HTTPS setup: [`docs/ui.md`](docs/ui.md).

## Architecture

```text
                         murn. PC

 desktop UI  ───────┐
                    |
                    v
                FastAPI
              /    |     \
         sessions agent   voice
          SQLite   |      /   \
                  tools whisper Piper
                 /   \
            Obsidian ComfyUI

 phone UI ──LAN/HTTPS──> /v1/voice/remote
                             |
                             └── ephemeral / not saved
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

Install with voice support:

```bash
python -m pip install -e '.[voice]'
cp .env.example .env
```

Pull the default Ollama models:

```bash
ollama pull llama3.1:8b
ollama pull embeddinggemma
```

Configure your Obsidian vault, ComfyUI workflow, whisper.cpp model, and Piper voice in `.env`.

Start murn.:

```bash
uvicorn murn.main:app --reload --host 127.0.0.1 --port 7331
```

Then open:

```text
http://127.0.0.1:7331
```

## Health

```bash
curl http://127.0.0.1:7331/health
```

The response includes status for Ollama, embeddings, ComfyUI, STT, TTS, and the UI.

## Chat and sessions

Normal chat:

```bash
curl -X POST http://127.0.0.1:7331/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Olá murn."}'
```

The response includes a `session_id`. Reuse it to continue the same persistent conversation.

List sessions:

```bash
curl http://127.0.0.1:7331/v1/sessions
```

Streaming chat:

```bash
curl -N -X POST http://127.0.0.1:7331/v1/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"Explique o que você consegue fazer."}'
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
  --data-urlencode 'q=qual navegador eu estou desenvolvendo?'
```

Obsidian stays the source of truth. The local vector cache lives in `.murn/memory_embeddings.db` and can be rebuilt.

## Image generation

After exporting and configuring a ComfyUI API workflow:

```bash
curl -X POST http://127.0.0.1:7331/v1/images/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"a quiet rainy street at night"}'
```

The agent can also call image generation as a tool from chat, and the desktop UI displays the generated image inline.

## Local voice

Voice API:

```text
POST /v1/audio/transcribe
POST /v1/audio/speech
GET  /v1/audio/files/{filename}
POST /v1/voice/chat
POST /v1/voice/remote
```

Full Arch Linux setup and model downloads: [`docs/voice.md`](docs/voice.md).

Standalone continuous microphone client:

```fish
murn-voice
```

Voice path:

```text
audio -> ffmpeg -> whisper.cpp -> murn. -> Piper -> WAV
```

## Current safety model

murn. does **not** give the language model arbitrary shell access. Capabilities are exposed through explicit providers/tools so filesystem, terminal, Orbital, vision, and other integrations can each receive their own permissions and limits.

The phone companion is intended for a trusted local network. The development server does not yet provide public-internet authentication, so do not expose it directly to the internet.

## Roadmap

- streaming TTS while the model is still answering
- interrupt / barge-in while murn. is speaking
- Orbital native AI bridge
- vision model support
- optional Tauri desktop wrapper around the current UI
- controlled filesystem and terminal tools
