# murn. image system

murn. v0.5.1 can manage ComfyUI as a user service and renders generated images directly inside the desktop conversation.

## Architecture

```text
murn. desktop app
      |
      v
127.0.0.1:7332
      |
      +--> generate_image tool
      |        |
      |        v
      |   ComfyUI :8188
      |        |
      |        v
      |   generated image
      |
      +--> /v1/images/view
               |
               v
        inline <img> in chat
```

The browser/Tauri client no longer needs to load a raw `127.0.0.1:8188/view?...` URL. murn. proxies the image through its own `/v1/images/view` route.

## Automatic ComfyUI startup

The desktop installer looks for ComfyUI at:

```text
~/AI/ComfyUI
```

You can override that location before installation:

```fish
set -x MURN_COMFYUI_DIR /another/path/ComfyUI
bash scripts/install_desktop_app.sh
```

The installer detects Python in this order:

```text
~/AI/ComfyUI/.venv/bin/python
~/AI/ComfyUI/venv/bin/python
python3
python
```

When detected it installs:

```text
~/.config/systemd/user/murn-comfyui.service
~/.local/lib/murn/start-comfyui
```

`murn.service` and `murn-desktop-backend.service` both request `murn-comfyui.service`, so starting murn. also starts the image backend.

If ComfyUI is already running manually on port `8188`, the managed service waits instead of fighting for the port. When that manual instance exits, the managed instance takes over.

## Install/update

```fish
cd ~/Projects/murn
git pull
source .venv/bin/activate.fish
python -m pip install -e '.[voice]'
bash scripts/install_desktop_app.sh
```

## Check status

```fish
systemctl --user status murn-comfyui.service
```

Live logs:

```fish
journalctl --user -u murn-comfyui.service -f
```

Check ComfyUI itself:

```fish
curl http://127.0.0.1:8188/queue
```

Check murn.'s image status:

```fish
curl http://127.0.0.1:7332/health
```

The health response should contain:

```json
"comfyui": true
```

## Inline generated images

The `generate_image` tool result contains a same-origin murn. URL like:

```text
/v1/images/view?filename=...&subfolder=...&type=output
```

The desktop UI already turns the tool result into an `<img>` element in the assistant message. The language model does not receive the transport URL, so it should not replace the image with a raw localhost link in its answer.
