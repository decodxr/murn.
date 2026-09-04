# murn. desktop app

The desktop app is a native Tauri window that opens the **same desktop UI already served by murn.** No redesign, no second frontend, and no duplicated chat code.

The phone stays browser-based at `/mobile`.

## Architecture

```text
murn. desktop app (Tauri)
        |
        | opens the existing desktop UI
        v
127.0.0.1:7331/
        |
        +-- FastAPI / Ollama / memory / ComfyUI / voice
        |
        +-- /mobile  -> phone companion over LAN
```

The backend is installed as a `systemd --user` service. Opening the native app asks systemd to start the backend if needed, waits for port `7331`, then opens the existing UI inside the native window.

This has an important side effect: the backend can remain available to the phone even when the desktop window itself is closed.

## Arch Linux dependencies

Install the native Tauri/WebKit build dependencies:

```fish
sudo pacman -S --needed base-devel rust webkit2gtk-4.1 openssl librsvg
```

No Node.js frontend build is required. The desktop shell is Rust/Tauri only.

## Install

First update the repository and Python environment:

```fish
cd ~/Projects/murn
git pull
source .venv/bin/activate.fish
python -m pip install -e '.[voice]'
```

If you currently have `uvicorn` running manually in a terminal, stop it with `Ctrl+C`. The installer needs port `7331` free so the user service can own it.

Then run:

```fish
cd ~/Projects/murn
bash scripts/install_desktop_app.sh
```

The first Rust build can take a while because Cargo downloads and compiles the Tauri/WebKit dependencies.

The installer creates:

```text
~/.local/bin/murn-desktop
~/.local/share/applications/murn.desktop
~/.local/share/icons/hicolor/scalable/apps/murn.svg
~/.config/systemd/user/murn.service
~/.config/murn/desktop-url
```

It also enables and starts:

```text
murn.service
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

The native window loads the exact same UI that was previously opened at:

```text
http://127.0.0.1:7331/
```

or HTTPS if the local mkcert certificate is already installed.

## HTTPS detection

The installer automatically looks for:

```text
~/.local/share/murn/certs/murn.pem
~/.local/share/murn/certs/murn-key.pem
```

If both exist, the backend service is started with HTTPS and the desktop app opens:

```text
https://127.0.0.1:7331
```

If they do not exist, it uses HTTP locally.

The phone browser needs HTTPS for microphone access over Wi-Fi. The existing phone UI remains:

```text
https://YOUR_PC_LAN_IP:7331/mobile
```

For the current machine, find the LAN address with:

```fish
ip -4 addr
```

## Service commands

Status:

```fish
systemctl --user status murn.service
```

Restart after changing `.env` or backend configuration:

```fish
systemctl --user restart murn.service
```

Stop:

```fish
systemctl --user stop murn.service
```

Start:

```fish
systemctl --user start murn.service
```

Logs:

```fish
journalctl --user -u murn.service -f
```

The desktop app also calls `systemctl --user start murn.service` when launched, so normally you do not need to start it by hand.

## Rebuild after desktop-shell changes

The existing HTML/CSS/JS UI still comes from the Python package, so ordinary UI/backend updates only need `git pull` + service restart.

If files under `desktop-app/` change, rebuild/reinstall the native shell:

```fish
cd ~/Projects/murn
git pull
bash scripts/install_desktop_app.sh
```

## Desktop UI remains unchanged

The Tauri shell does not contain a second copy of the chat interface. It navigates directly to the FastAPI-served desktop UI, so saved conversations, streaming, generated images, memory tool cards, microphone controls, and future UI changes stay identical between the local web version and the desktop app.

The phone is intentionally still a separate browser companion and remains voice-only.
