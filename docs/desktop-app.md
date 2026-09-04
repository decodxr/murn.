# murn. desktop app

The desktop app is a native Tauri window that opens the **same desktop UI already served by murn.** No redesign, no second frontend, and no duplicated chat code.

The phone stays browser-based at `/mobile`.

## Architecture

```text
murn. desktop app (Tauri)
        |
        | loopback-only HTTP
        v
127.0.0.1:7332/
        |
        +-- FastAPI / Ollama / memory / ComfyUI / voice

phone browser
        |
        | LAN / HTTPS when mkcert is configured
        v
PC-LAN-IP:7331/mobile
```

There are intentionally two local FastAPI processes:

- `murn-desktop-backend.service` — HTTP on `127.0.0.1:7332`, reachable only from the PC and used by the native Tauri webview.
- `murn.service` — LAN backend on `0.0.0.0:7331`; it uses HTTPS automatically when the mkcert files exist and serves the phone companion.

Both use the same `.env`, SQLite conversations, Obsidian memory, Ollama, ComfyUI, whisper.cpp, and Piper configuration.

Why split them? WebKit inside a Tauri Linux app can reject a locally generated TLS certificate even when Chrome/Android trusts the same CA. That can produce a blank native window. The dedicated loopback HTTP service removes TLS from the desktop rendering path while keeping HTTPS for the phone microphone.

## Arch Linux dependencies

Install the native Tauri/WebKit build dependencies:

```fish
sudo pacman -S --needed base-devel rust webkit2gtk-4.1 openssl librsvg
```

No Node.js frontend build is required. The desktop shell is Rust/Tauri only.

## Install / repair

Update the repository and Python environment:

```fish
cd ~/Projects/murn
git pull
source .venv/bin/activate.fish
python -m pip install -e '.[voice]'
```

If you currently have `uvicorn` running manually in a terminal, stop it with `Ctrl+C`. The installer needs ports `7331` and `7332` free.

Then run:

```fish
cd ~/Projects/murn
bash scripts/install_desktop_app.sh
```

The first Rust build can take a while. Later runs reuse Cargo's build cache.

The installer creates:

```text
~/.local/bin/murn-desktop
~/.local/share/applications/murn.desktop
~/.local/share/icons/hicolor/scalable/apps/murn.svg
~/.config/systemd/user/murn.service
~/.config/systemd/user/murn-desktop-backend.service
~/.config/murn/desktop-url
```

The desktop URL file is intentionally:

```text
http://127.0.0.1:7332
```

## Open the app

Use the KDE application launcher and search for:

```text
murn.
```

or run:

```fish
murn-desktop
```

The native window loads the exact same UI as the browser version, but from the loopback-only desktop backend.

## Phone HTTPS

The installer looks for:

```text
~/.local/share/murn/certs/murn.pem
~/.local/share/murn/certs/murn-key.pem
```

If both exist, `murn.service` serves the LAN endpoint with HTTPS on port `7331`.

The phone UI remains:

```text
https://YOUR_PC_LAN_IP:7331/mobile
```

If those files do not exist, the phone endpoint uses HTTP instead; browser microphone access over Wi-Fi generally requires HTTPS.

Find the PC LAN IP with:

```fish
ip -4 addr
```

## Service commands

Phone/LAN service status:

```fish
systemctl --user status murn.service
```

Desktop loopback service status:

```fish
systemctl --user status murn-desktop-backend.service
```

Restart both after backend/config changes:

```fish
systemctl --user restart murn.service murn-desktop-backend.service
```

Logs:

```fish
journalctl --user -u murn.service -f
```

```fish
journalctl --user -u murn-desktop-backend.service -f
```

The native app asks systemd to start both services when launched.

## Rebuild after desktop-shell changes

The HTML/CSS/JS UI still comes from the Python package, so ordinary UI/backend changes do not duplicate frontend code.

If files under `desktop-app/` or the installer change, rebuild/reinstall with:

```fish
cd ~/Projects/murn
git pull
bash scripts/install_desktop_app.sh
```

## Desktop UI remains unchanged

The Tauri shell does not contain a second copy of the chat interface. It navigates directly to the FastAPI-served desktop UI, so saved conversations, streaming, generated images, memory tool cards, microphone controls, and future UI changes stay identical to the web UI.

The phone remains a separate browser companion and stays voice-only.
