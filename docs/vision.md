# murn. local vision

murn. v0.6 adds local image understanding to the desktop app.

The default vision model is:

```text
qwen2.5vl:3b
```

It runs through the same local Ollama server as the normal text model. The smaller 3B vision model is the default because it is a much better fit for an 8 GB GPU while still handling screenshots, text, interfaces, diagrams, photos and documents.

## Install the vision model

```fish
ollama pull qwen2.5vl:3b
```

Check that Ollama sees it:

```fish
ollama list
```

`/health` should then report:

```json
{
  "vision_model": "qwen2.5vl:3b",
  "vision": true
}
```

## Desktop usage

The existing attachment icon in the murn. desktop composer now accepts images.

Supported input methods:

- click the attachment button and choose an image
- drag an image onto the composer
- paste an image/screenshot from the clipboard

Supported file formats:

```text
PNG
JPEG
WebP
```

The default upload limit is 20 MB.

After attaching an image, type a question such as:

```text
o que tem nessa imagem?
```

```text
analisa esse erro e me diga o que aconteceu
```

```text
leia o texto deste print
```

```text
explique esse gráfico
```

If the text field is empty, murn. uses:

```text
Analise esta imagem detalhadamente.
```

## Saved conversations

Images sent to vision are copied into:

```text
.murn/vision/
```

The conversation database stores a private local image marker plus the question. When the conversation is reopened, the desktop UI renders the saved image inline again.

The image files are served only through murn.'s local API:

```text
GET /v1/vision/files/{filename}
```

## Vision endpoint

```text
POST /v1/vision/chat
```

Multipart fields:

```text
file        required image
message     optional question/prompt
session_id  optional existing desktop session
```

Example:

```fish
curl -X POST http://127.0.0.1:7332/v1/vision/chat \
  -F 'file=@/tmp/screenshot.png' \
  -F 'message=analise esse print'
```

## GPU / VRAM behavior

The normal text model and the vision model share the same GPU.

Before a vision request, murn. asks Ollama to unload the normal `llama3.1:8b` model. The vision request then loads `qwen2.5vl:3b`, performs the analysis and uses `keep_alive=0`, so the vision model is released immediately after the answer.

The normal text model automatically loads again the next time ordinary chat needs it.

This is intentional for GPUs with limited VRAM and also keeps ComfyUI image generation from competing with multiple Ollama models at once.

## Change the vision model

In `.env`:

```env
MURN_VISION_MODEL=qwen2.5vl:3b
MURN_VISION_MAX_MB=20
```

Then restart both murn. backends:

```fish
systemctl --user restart murn.service
systemctl --user restart murn-desktop-backend.service
```

Any Ollama model configured here must support image input.
