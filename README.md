# murn.

**murn.** is a local-first personal AI agent with memory, tools, saved conversations, streaming, image generation, image understanding, local voice, a native desktop app, and a voice-only phone companion.

Current stack:

- **Ollama** — local language model (`llama3.1:8b` by default)
- **Qwen2.5-VL via Ollama** — local image understanding (`qwen2.5vl:3b` by default)
- **EmbeddingGemma via Ollama** — semantic memory embeddings
- **Obsidian** — durable Markdown memory
- **SQLite** — saved desktop conversations and semantic-memory index
- **ComfyUI** — local image generation
- **whisper.cpp** — local speech-to-text
- **Piper** — local text-to-speech
- **FastAPI** — local API + UI server
- **Tauri** — native Linux desktop shell around the exact same murn. UI
- **Orbital** — optional browser bridge scaffold

## UI

murn. ships the black / white / violet interface directly from the backend.

```text
Desktop web   http://127.0.0.1:7331/
Phone UI      http://127.0.0.1:7331/mobile
API docs      http://127.0.0.1:7331/docs
```

### Native desktop app

The PC version can be installed as a native Tauri application. It does **not** duplicate or redesign the frontend: the native window opens the exact same desktop UI served by FastAPI.

The installer also creates `systemd --user` backend services, so opening `murn.` from the KDE launcher starts the local backend automatically when needed. The phone companion remains a normal browser page at `/mobile`.

Full Arch Linux installation guide: [`docs/desktop-app.md`](docs/desktop-app.md).

### Desktop interface

The desktop interface includes:

- saved conversations in a left sidebar
- returning to any previous conversation
- search + local pinning
- streaming responses
- visible tool cards
- ComfyUI image results inside chat
- local image analysis from attachments / drag-and-drop / clipboard paste
- saved vision images rendered again when reopening a conversation
- microphone input + Piper playback
- live backend/model/voice/vision status

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

Full desktop-web + phone + LAN + HTTPS setup: [`docs/ui.md`](docs/ui.md).

## Architecture

```text
                         murn. PC

 Tauri app ────────┐
 desktop web ──────┤
                   v
                FastAPI
          /      / | \       \
    sessions vision agent    voice
     SQLite   Ollama  |      /   \
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
ollama pull qwen2.5vl:3b
```

Configure your Obsidian vault, ComfyUI workflow, whisper.cpp model, Piper voice, and optional vision model override in `.env`.

Start murn. manually for development:

```bash
uvicorn murn.main:app --reload --host 127.0.0.1 --port 7331
```

Then open:

```text
http://127.0.0.1:7331
```

For the native desktop application instead, see [`docs/desktop-app.md`](docs/desktop-app.md).

## Health

```bash
curl http://127.0.0.1:7331/health
```

The response includes status for Ollama, vision, embeddings, ComfyUI, STT, TTS, and the UI.

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

## Local image understanding

Install the default vision model:

```fish
ollama pull qwen2.5vl:3b
```

In the desktop app you can then:

- click the attachment icon
- drag a PNG/JPEG/WebP image onto the composer
- paste a screenshot directly from the clipboard

Ask questions such as:

```text
analisa esse erro
leia o texto desse print
explique esse gráfico
o que aparece nessa foto?
```

Vision requests use:

```text
POST /v1/vision/chat
GET  /v1/vision/files/{filename}
```

The normal text LLM is unloaded before vision so both models do not compete for VRAM. The vision model uses `keep_alive=0` and is released immediately after each analysis.

Full guide: [`docs/vision.md`](docs/vision.md).

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

Full guide: [`docs/images.md`](docs/images.md).

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
- multi-image vision requests
- controlled filesystem and terminal tools
