# murn.

**murn.** is a local-first personal AI agent with adaptive intelligence, persistent conversations, Obsidian memory, web research, Orbital browser control, safe coding-workspace inspection, image generation, image understanding, local voice, a native desktop app, mini voice mode, mobile companion, and live debug tracing.

Current stack:

- **Ollama** — local language model (`llama3.1:8b` by default)
- **Qwen2.5-VL via Ollama** — local image understanding (`qwen2.5vl:3b` by default)
- **EmbeddingGemma via Ollama** — semantic memory embeddings
- **Obsidian** — durable Markdown memory
- **SQLite** — saved conversations, semantic-memory index, and shared debug events
- **ComfyUI** — local image generation
- **whisper.cpp** — local speech-to-text
- **Piper** — local text-to-speech
- **FastAPI** — local API + UI server
- **Tauri** — native Linux desktop shell with full + mini modes
- **Orbital** — controllable Chromium browser through CDP + murn. extension integration

## Intelligence

murn. treats the underlying LLM as one component of the system rather than the entire product.

Requests are classified locally without another model call:

```text
coding    -> low-temperature engineering/debug profile
language  -> writing/translation/linguistic profile
factual   -> conservative factual profile
general   -> normal murn. personality + reliability rules
```

Tool routing also considers recent conversation context, so short follow-ups remain attached to the action already in progress. Explicit actions can trigger one internal tool-use retry when the LLM tries to answer around an available tool instead of actually using it.

## UI

```text
Desktop/LAN backend   :7331
Native desktop backend 127.0.0.1:7332
Phone companion       /mobile
Mini voice UI         /mini
API docs               /docs
```

### Native desktop app

The PC version can be installed as a native Tauri application. The installer creates `systemd --user` services so opening `murn.` from KDE starts the required local backend automatically.

The desktop interface includes:

- saved conversations + search + local pinning
- delete-chat without touching long-term memory
- streaming responses
- generated images inline
- image analysis by attachment / drag-and-drop / clipboard paste
- microphone input + Piper playback
- Orbital launch/integration controls
- live global debug console
- liquid-glass UI with reduced repaint overhead
- **MINI** voice mode (`Ctrl+Shift+M`)

### Mini desktop voice mode

`MINI` shrinks the actual native KDE window to a compact voice core. It includes:

- animated orb/waveform reacting to microphone input
- the same waveform reacting to murn.'s Piper output
- hold-to-talk
- hands-free VAD / auto listen
- native always-on-top toggle
- expand back to the full desktop UI
- conversation continuity between full and mini modes

### Phone companion

The phone has two modes:

```text
ASSISTANT  -> voice + text + visible conversation + generated images
VOICE MODE -> focused voice HUD with hold-to-talk / auto listen
```

Voice runtime states:

```text
STANDBY
LISTENING
TRANSCRIBING
THINKING
SPEAKING
```

The orb reacts to both the user's microphone signal and murn.'s spoken response.

## Tools

murn. exposes capabilities as explicit tools rather than arbitrary shell access.

Current families include:

```text
memory_search / memory_write
calculate
workspace_roots / workspace_list / workspace_read / workspace_search
workspace_git_status / workspace_git_diff
web_search / web_open
browser_launch / browser_* Orbital tools
generate_image
```

The coding workspace is **read-only**. It is restricted to configured roots, blocks path/symlink escapes, skips common binary/build/vendor data, disables external Git diff helpers, and puts a time/file budget on broad searches.

Default configuration:

```env
MURN_WORKSPACE_ENABLED=true
MURN_WORKSPACE_ROOTS=~/Projects;~/Orbital
MURN_WORKSPACE_MAX_FILE_CHARS=40000
```

Only add roots that you are comfortable allowing the local agent to inspect.

## Architecture

```text
                              murn. PC

 full Tauri UI ─────┐
 mini voice UI ─────┤
 desktop web ───────┤
 phone /mobile ─────┤
 Orbital extension ─┤
                    v
                 FastAPI
        /       /    |      \        \
 sessions   vision  agent   voice    debug
 SQLite     Ollama    |    whisper   SQLite
                      |      Piper
                     tools
      /        /       |        \          \
 Obsidian   ComfyUI    web    Orbital    workspace
 memory               HTTP      CDP      read-only
```

## Quick start

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

Configure Obsidian, ComfyUI, whisper.cpp, Piper, Orbital, and allowed workspace roots in `.env`.

For development:

```bash
uvicorn murn.main:app --reload --host 127.0.0.1 --port 7331
```

For the native desktop application, run the desktop installer documented in [`docs/desktop-app.md`](docs/desktop-app.md).

## Health

```bash
curl http://127.0.0.1:7331/health
```

The response includes Ollama, vision, embeddings, ComfyUI, browser, workspace, adaptive-intelligence, STT/TTS, debug and UI state.

## Chat and sessions

Normal chat:

```bash
curl -X POST http://127.0.0.1:7331/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Olá murn."}'
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

The desktop UI supports attachment, drag-and-drop and clipboard screenshots. Vision requests use:

```text
POST /v1/vision/chat
GET  /v1/vision/files/{filename}
```

The normal text LLM is unloaded before vision so both models do not compete for VRAM.

Full guide: [`docs/vision.md`](docs/vision.md).

## Semantic Obsidian memory

Reindex:

```bash
curl -X POST http://127.0.0.1:7331/v1/memory/reindex
```

Search:

```bash
curl --get http://127.0.0.1:7331/v1/memory/search \
  --data-urlencode 'q=qual navegador eu estou desenvolvendo?'
```

Obsidian stays the source of truth. The vector cache lives in `.murn/memory_embeddings.db` and can be rebuilt.

## Image generation

After configuring a ComfyUI API workflow:

```bash
curl -X POST http://127.0.0.1:7331/v1/images/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"a quiet rainy street at night"}'
```

The agent can call `generate_image` from chat and the clients render results inline. For tool-driven generation, resident chat/embedding models are released before ComfyUI competes for GPU memory.

Full guide: [`docs/images.md`](docs/images.md).

## Local voice

```text
POST /v1/audio/transcribe
POST /v1/audio/speech
GET  /v1/audio/files/{filename}
POST /v1/voice/chat
POST /v1/voice/remote
```

Voice path:

```text
audio -> ffmpeg -> whisper.cpp -> murn. -> Piper -> WAV
```

Full guide: [`docs/voice.md`](docs/voice.md).

## Debug mode

Debug traces are shared between the desktop and phone backend processes through `.murn/debug_events.db`.

The console exposes operational reasoning rather than hidden chain-of-thought: request source, selected profile, tool routing, context size, tool arguments/results, first-token latency, total time, VRAM events and errors.

## Current safety model

murn. does **not** give the LLM arbitrary shell access. Capabilities are explicit providers/tools with their own bounds.

- web page content is untrusted
- Orbital CDP stays loopback-only
- consequential browser actions require confirmation when not already explicitly authorized
- workspace inspection is read-only and allowlisted
- debug logs are local
- the LAN backend is intended for a trusted local network and should not be exposed directly to the public internet

## v0.14 notes

See [`docs/v0.14-overhaul.md`](docs/v0.14-overhaul.md) for the adaptive-intelligence, tool-recovery, workspace and mini-mode changes.

## Roadmap

- streaming TTS while the model is still answering
- interrupt / barge-in while murn. is speaking
- optional specialist local model routing for coding/general reasoning
- controlled file-edit tools with explicit review/approval
- multi-image vision requests
