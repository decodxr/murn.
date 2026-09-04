# murn.

**murn.** is a local-first AI agent with memory, tools, web/browser integration, and image generation.

This repository is the core backend for murn. The first version uses:

- **Ollama** for local text models (default: `llama3.1:8b`)
- **ComfyUI** for local image generation
- **Obsidian** as persistent Markdown memory
- **FastAPI** as the local agent API
- **Orbital** as an optional browser provider (adapter scaffold included)

## Architecture

```text
client / future UI
      |
      v
 FastAPI API
      |
      v
  murn agent
   /   |    \
Ollama Obsidian ComfyUI
  |       |      |
Llama   memory  images
      \
       Orbital (optional browser)
```

## Quick start

### 1. Install Ollama

Linux:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
ollama run llama3.1:8b
```

Ollama exposes its local API on `http://127.0.0.1:11434`.

For a lighter model, especially if ComfyUI is using the GPU at the same time:

```bash
ollama pull llama3.2:3b
```

Then set `MURN_OLLAMA_MODEL=llama3.2:3b` in `.env`.

### 2. Install ComfyUI

One easy option is `comfy-cli`:

```bash
python -m pip install comfy-cli
comfy install
```

Or install manually:

```bash
git clone https://github.com/Comfy-Org/ComfyUI.git ~/AI/ComfyUI
cd ~/AI/ComfyUI
python -m venv .venv
source .venv/bin/activate
pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
pip install -r requirements.txt
python main.py --listen 127.0.0.1 --port 8188
```

Place your image models in the folders expected by your ComfyUI workflow.

To let murn. generate images, build a working txt2img workflow in ComfyUI and export it in **API format**. Save the exported file as:

```text
workflows/txt2img_api.json
```

Then configure the node IDs in `.env`. See `workflows/README.md`.

### 3. Set up murn.

```bash
git clone https://github.com/decodxr/murn..git
cd murn.
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Edit `.env` and set your Obsidian vault path:

```env
MURN_OBSIDIAN_VAULT=/home/you/Documents/Obsidian/MyVault
```

Start the backend:

```bash
uvicorn murn.main:app --reload --host 127.0.0.1 --port 7331
```

Open:

```text
http://127.0.0.1:7331/docs
```

### 4. Test it

Health:

```bash
curl http://127.0.0.1:7331/health
```

Chat:

```bash
curl -X POST http://127.0.0.1:7331/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Remember that the murn. browser integration is called Orbital."}'
```

Search memory:

```bash
curl 'http://127.0.0.1:7331/v1/memory/search?q=Orbital'
```

Generate an image after configuring a ComfyUI API workflow:

```bash
curl -X POST http://127.0.0.1:7331/v1/images/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"a quiet rainy street at night, documentary photography"}'
```

## Current scope

The initial core intentionally does **not** give the model arbitrary shell access. Tools are registered explicitly. That keeps the agent understandable and gives us a safe place to add filesystem, Orbital, code execution, vision, and other capabilities later.

## Next pieces

- semantic memory / embeddings over the Obsidian vault
- conversation sessions
- streaming responses
- Orbital native AI bridge
- vision model support
- local speech input/output
- desktop UI
