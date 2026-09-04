# murn.

**murn.** is a local-first AI agent with memory, tools, persistent conversations, streaming, browser integration, and image generation.

Current stack:

- **Ollama** for local language models (default: `llama3.1:8b`)
- **EmbeddingGemma via Ollama** for local semantic memory
- **ComfyUI** for local image generation
- **Obsidian** for durable Markdown memory
- **SQLite** for local conversation sessions/history and the semantic-memory index
- **FastAPI** for the local agent API
- **Orbital** as an optional browser provider (adapter scaffold included)

## Architecture

```text
client / future UI
        |
        v
    FastAPI API
        |
        v
      murn.
   /      |       \
Ollama  SQLite    tools
  |      /   \    /   \
Llama sessions vectors Obsidian ComfyUI
         ^             |       |
         |             |     images
   EmbeddingGemma -----+

Orbital -> optional browser bridge
```

## Quick start

### 1. Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
ollama pull embeddinggemma
```

Ollama API:

```text
http://127.0.0.1:11434
```

### 2. ComfyUI on Arch Linux

Do not install Python packages globally with `pip --break-system-packages`. Use a virtual environment.

```bash
git clone https://github.com/Comfy-Org/ComfyUI.git ~/AI/ComfyUI
cd ~/AI/ComfyUI
python -m venv .venv
```

fish:

```fish
source .venv/bin/activate.fish
```

bash/zsh:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
python -m pip install -r requirements.txt
```

Start ComfyUI:

```bash
python main.py --listen 127.0.0.1 --port 8188
```

Export a working txt2img workflow in **API format** and save it as:

```text
workflows/txt2img_api.json
```

Then configure the workflow node IDs in `.env`. See `workflows/README.md`.

### 3. murn.

```bash
git clone https://github.com/decodxr/murn..git ~/Projects/murn
cd ~/Projects/murn
python -m venv .venv
```

fish:

```fish
source .venv/bin/activate.fish
```

Then:

```bash
python -m pip install -e .
cp .env.example .env
```

Configure `.env`, for example:

```env
MURN_OLLAMA_URL=http://127.0.0.1:11434
MURN_OLLAMA_MODEL=llama3.1:8b
MURN_EMBEDDING_MODEL=embeddinggemma

MURN_OBSIDIAN_VAULT=/home/you/Documents/Obsidian/Murn
MURN_OBSIDIAN_MEMORY_DIR=murn

MURN_COMFYUI_URL=http://127.0.0.1:8188
MURN_COMFY_WORKFLOW_PATH=workflows/txt2img_api.json
MURN_COMFY_POSITIVE_NODE=67
MURN_COMFY_NEGATIVE_NODE=71
MURN_COMFY_SEED_NODE=70
MURN_COMFY_LATENT_NODE=68

MURN_DATA_DIR=.murn
MURN_SESSION_DB_NAME=sessions.db
MURN_SEMANTIC_DB_NAME=memory_embeddings.db
```

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

`embeddings` should be `true` after `embeddinggemma` has been pulled into Ollama.

## Persistent chat sessions

A chat request without a `session_id` automatically creates a session:

```bash
curl -X POST http://127.0.0.1:7331/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"My browser project is called Orbital."}'
```

The response contains a `session_id`. Reuse it on later messages:

```bash
curl -X POST http://127.0.0.1:7331/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"PASTE_SESSION_ID_HERE","message":"What is my browser project called?"}'
```

List sessions:

```bash
curl http://127.0.0.1:7331/v1/sessions
```

Read one session:

```bash
curl http://127.0.0.1:7331/v1/sessions/PASTE_SESSION_ID_HERE
```

Session data is stored locally in:

```text
.murn/sessions.db
```

This is separate from Obsidian memory: SQLite stores the conversation history, while Obsidian stores durable long-term memories.

## Streaming chat

`/v1/chat/stream` returns newline-delimited JSON events as the model responds:

```bash
curl -N -X POST http://127.0.0.1:7331/v1/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"Explain what murn. can currently do."}'
```

Event types include:

```text
session
 token
 tool_start
 tool_result
 done
 error
```

The tool events are useful for a future UI to show things like image-generation progress without waiting for the final model response.

## Semantic Obsidian memory

murn. embeds Markdown chunks locally with Ollama and caches the vectors in:

```text
.murn/memory_embeddings.db
```

The source of truth stays in Obsidian. The SQLite vector cache can be deleted and rebuilt at any time.

Build/update the index:

```bash
curl -X POST http://127.0.0.1:7331/v1/memory/reindex
```

Semantic search:

```bash
curl --get http://127.0.0.1:7331/v1/memory/search \
  --data-urlencode 'q=what was I doing with my browser project?'
```

The index automatically checks for changed Markdown files before each semantic search, so new or edited notes are picked up without manually rebuilding every time.

If the embedding backend is unavailable, the agent's `memory_search` tool falls back to the older keyword search instead of losing memory access completely.

murn.-generated memories live under:

```text
<your vault>/murn/memory/
```

## Image generation

```bash
curl -X POST http://127.0.0.1:7331/v1/images/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"a quiet rainy street at night, documentary photography"}'
```

Or ask the agent directly:

```bash
curl -X POST http://127.0.0.1:7331/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Generate an image of an abandoned gas station at night."}'
```

## Current safety model

murn. does not give the language model arbitrary shell access. Capabilities are exposed as explicit tools. Filesystem, terminal, Orbital, voice, and other integrations can therefore be added with their own permissions instead of handing the model unrestricted system access.

## Roadmap

- speech-to-text (local Whisper-compatible backend)
- text-to-speech
- Orbital native AI bridge
- vision model support
- desktop/chat UI
- controlled filesystem and terminal tools
