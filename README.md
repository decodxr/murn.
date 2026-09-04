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

> On Arch Linux, do not install Python packages globally with `pip --break-system-packages`. Use a virtual environment. The `python-xyz` text shown by pacman/PEP 668 is only an example placeholder, not a real package name.

Manual install:

```bash
git clone https://github.com/Comfy-Org/ComfyUI.git ~/AI/ComfyUI
cd ~/AI/ComfyUI
python -m venv .venv
```

Activate the venv for your shell:

**fish:**

```fish
source .venv/bin/activate.fish
```

**bash/zsh:**

```bash
source .venv/bin/activate
```

Then install dependencies from inside the venv:

```bash
python -m pip install --upgrade pip
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
python -m pip install -r requirements.txt
```

You can verify that the venv is active with:

```bash
which python
python -m pip --version
```

Both paths should point somewhere inside `~/AI/ComfyUI/.venv/`.

If shell activation ever fails, you can bypass activation entirely and use the venv Python directly:

```bash
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py --listen 127.0.0.1 --port 8188
```

Start ComfyUI normally after activation:

```bash
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
```

Activate it using the correct script for your shell:

```fish
# fish
source .venv/bin/activate.fish
```

```bash
# bash/zsh
source .venv/bin/activate
```

Then:

```bash
python -m pip install -e .
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
