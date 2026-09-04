#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${MURN_VENV:-$ROOT/.venv}"
UVICORN="$VENV/bin/uvicorn"
CARGO_MANIFEST="$ROOT/desktop-app/src-tauri/Cargo.toml"
BINARY_SOURCE="$ROOT/desktop-app/src-tauri/target/release/murn-desktop"
APP_LIB_DIR="$HOME/.local/lib/murn"
BINARY_DEST="$APP_LIB_DIR/murn-desktop-bin"
COMFY_LAUNCHER="$APP_LIB_DIR/start-comfyui"
LAUNCHER_DIR="$HOME/.local/bin"
LAUNCHER_DEST="$LAUNCHER_DIR/murn-desktop"
SAFE_LAUNCHER_DEST="$LAUNCHER_DIR/murn-desktop-safe"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/murn"
LOG_FILE="$STATE_DIR/desktop.log"
SERVICE_DIR="$HOME/.config/systemd/user"
MOBILE_SERVICE_FILE="$SERVICE_DIR/murn.service"
DESKTOP_SERVICE_FILE="$SERVICE_DIR/murn-desktop-backend.service"
COMFY_SERVICE_FILE="$SERVICE_DIR/murn-comfyui.service"
CONFIG_DIR="$HOME/.config/murn"
URL_FILE="$CONFIG_DIR/desktop-url"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
DESKTOP_DIR="$HOME/.local/share/applications"
FISH_CONF_DIR="$HOME/.config/fish/conf.d"
FISH_PATH_FILE="$FISH_CONF_DIR/murn-path.fish"
CERT="$HOME/.local/share/murn/certs/murn.pem"
KEY="$HOME/.local/share/murn/certs/murn-key.pem"
TAURI_ICON_DIR="$ROOT/desktop-app/src-tauri/icons"
TAURI_ICON="$TAURI_ICON_DIR/icon.png"
SOURCE_ICON="$ROOT/desktop-app/murn.svg"
COMFY_DIR="${MURN_COMFYUI_DIR:-$HOME/AI/ComfyUI}"
COMFY_VRAM_ARGS="${MURN_COMFYUI_ARGS:---lowvram --reserve-vram 0.5}"
DESKTOP_PORT=7332
MOBILE_PORT=7331
COMFY_PORT=8188
DESKTOP_URL="http://127.0.0.1:${DESKTOP_PORT}"

say() { printf '\n\033[1;35m[murn.]\033[0m %s\n' "$*"; }
warn() { printf '\n\033[1;33m[murn.] warning:\033[0m %s\n' "$*"; }
fail() { printf '\n\033[1;31m[murn.] error:\033[0m %s\n' "$*" >&2; exit 1; }

[[ -x "$UVICORN" ]] || fail "uvicorn was not found at $UVICORN. Create/activate the murn. venv and install the project first."
command -v cargo >/dev/null 2>&1 || fail "cargo was not found. Install Rust first: sudo pacman -S --needed rust"
command -v systemctl >/dev/null 2>&1 || fail "systemctl was not found."
command -v rsvg-convert >/dev/null 2>&1 || fail "rsvg-convert was not found. Install it with: sudo pacman -S --needed librsvg"
command -v curl >/dev/null 2>&1 || fail "curl was not found. Install it with: sudo pacman -S --needed curl"

systemctl --user stop murn.service >/dev/null 2>&1 || true
systemctl --user stop murn-desktop-backend.service >/dev/null 2>&1 || true
systemctl --user stop murn-comfyui.service >/dev/null 2>&1 || true

if command -v ss >/dev/null 2>&1; then
  if ss -ltn | grep -qE "[:.]${MOBILE_PORT}[[:space:]]"; then
    fail "port ${MOBILE_PORT} is already in use. Stop the manually started uvicorn (Ctrl+C) and run this installer again."
  fi
  if ss -ltn | grep -qE "[:.]${DESKTOP_PORT}[[:space:]]"; then
    fail "port ${DESKTOP_PORT} is already in use. Stop the process using it and run this installer again."
  fi
fi

MOBILE_SSL_ARGS=""
MOBILE_SCHEME="http"
if [[ -f "$CERT" && -f "$KEY" ]]; then
  MOBILE_SSL_ARGS=" --ssl-certfile $CERT --ssl-keyfile $KEY"
  MOBILE_SCHEME="https"
  say "HTTPS certificate found; phone/LAN backend will use HTTPS on port ${MOBILE_PORT}."
else
  say "No local HTTPS certificate found; phone/LAN backend will use HTTP. Browser microphone access over Wi-Fi requires HTTPS."
fi

COMFY_AVAILABLE=0
COMFY_PYTHON=""
if [[ -f "$COMFY_DIR/main.py" ]]; then
  if [[ -x "$COMFY_DIR/.venv/bin/python" ]]; then
    COMFY_PYTHON="$COMFY_DIR/.venv/bin/python"
  elif [[ -x "$COMFY_DIR/venv/bin/python" ]]; then
    COMFY_PYTHON="$COMFY_DIR/venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    COMFY_PYTHON="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    COMFY_PYTHON="$(command -v python)"
  fi

  if [[ -n "$COMFY_PYTHON" ]]; then
    COMFY_AVAILABLE=1
    say "ComfyUI found at $COMFY_DIR. It will start automatically with murn."
    say "ComfyUI VRAM profile: $COMFY_VRAM_ARGS"
  else
    warn "ComfyUI was found, but no Python interpreter was detected. Auto-start will not be installed."
  fi
else
  warn "ComfyUI was not found at $COMFY_DIR. Set MURN_COMFYUI_DIR before running this installer if it lives elsewhere."
fi

say "Desktop app will use loopback-only HTTP on 127.0.0.1:${DESKTOP_PORT}."
say "Applying Linux/NVIDIA-safe WebKit launcher defaults without changing the UI."

say "Preparing native app icon..."
mkdir -p "$TAURI_ICON_DIR"
rsvg-convert -w 512 -h 512 "$SOURCE_ICON" -o "$TAURI_ICON"
[[ -s "$TAURI_ICON" ]] || fail "failed to generate $TAURI_ICON"

say "Building native Tauri shell..."
cargo build --release --manifest-path "$CARGO_MANIFEST"

mkdir -p "$APP_LIB_DIR" "$LAUNCHER_DIR" "$STATE_DIR" "$SERVICE_DIR" "$CONFIG_DIR" "$ICON_DIR" "$DESKTOP_DIR" "$FISH_CONF_DIR"
install -m 0755 "$BINARY_SOURCE" "$BINARY_DEST"
install -m 0644 "$SOURCE_ICON" "$ICON_DIR/murn.svg"
printf '%s\n' "$DESKTOP_URL" > "$URL_FILE"

cat > "$LAUNCHER_DEST" <<EOF
#!/usr/bin/env bash
set -u
STATE_DIR="\${XDG_STATE_HOME:-\$HOME/.local/state}/murn"
mkdir -p "\$STATE_DIR"
LOG_FILE="\$STATE_DIR/desktop.log"
export __NV_DISABLE_EXPLICIT_SYNC="\${__NV_DISABLE_EXPLICIT_SYNC:-1}"
export WEBKIT_DISABLE_DMABUF_RENDERER="\${WEBKIT_DISABLE_DMABUF_RENDERER:-1}"
printf '\n===== murn. desktop start %s =====\n' "\$(date --iso-8601=seconds 2>/dev/null || date)" >> "\$LOG_FILE"
exec "$BINARY_DEST" >> "\$LOG_FILE" 2>&1
EOF
chmod 0755 "$LAUNCHER_DEST"

cat > "$SAFE_LAUNCHER_DEST" <<EOF
#!/usr/bin/env bash
export MURN_WEBKIT_SAFE_MODE=1
exec "$LAUNCHER_DEST" "\$@"
EOF
chmod 0755 "$SAFE_LAUNCHER_DEST"

cat > "$FISH_PATH_FILE" <<'EOF'
# murn. desktop command
if type -q fish_add_path
    fish_add_path --path "$HOME/.local/bin"
end
EOF

if [[ "$COMFY_AVAILABLE" -eq 1 ]]; then
  cat > "$COMFY_LAUNCHER" <<EOF
#!/usr/bin/env bash
set -euo pipefail
COMFY_DIR="$COMFY_DIR"
COMFY_PYTHON="$COMFY_PYTHON"
COMFY_URL="http://127.0.0.1:$COMFY_PORT"
COMFY_VRAM_ARGS="$COMFY_VRAM_ARGS"

# If the user already started ComfyUI manually, keep the service alive without
# fighting for the same port. As soon as that manual process exits, systemd's
# managed instance takes over automatically.
if curl -fsS "\$COMFY_URL/queue" >/dev/null 2>&1; then
  echo "murn.: existing ComfyUI detected on $COMFY_PORT; waiting to take over"
  while curl -fsS "\$COMFY_URL/queue" >/dev/null 2>&1; do
    sleep 5
  done
  sleep 1
fi

cd "\$COMFY_DIR"
read -r -a COMFY_ARGV <<< "\$COMFY_VRAM_ARGS"
exec "\$COMFY_PYTHON" main.py --listen 127.0.0.1 --port $COMFY_PORT "\${COMFY_ARGV[@]}"
EOF
  chmod 0755 "$COMFY_LAUNCHER"

  cat > "$COMFY_SERVICE_FILE" <<EOF
[Unit]
Description=murn. managed ComfyUI image backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$COMFY_LAUNCHER
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1
Environment=PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

[Install]
WantedBy=default.target
EOF
else
  rm -f "$COMFY_SERVICE_FILE" "$COMFY_LAUNCHER"
fi

COMFY_UNIT_DEPS=""
if [[ "$COMFY_AVAILABLE" -eq 1 ]]; then
  COMFY_UNIT_DEPS=$'Wants=murn-comfyui.service\nAfter=murn-comfyui.service'
fi

cat > "$MOBILE_SERVICE_FILE" <<EOF
[Unit]
Description=murn. LAN/mobile AI backend
After=network-online.target
Wants=network-online.target
$COMFY_UNIT_DEPS

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$UVICORN murn.main:app --host 0.0.0.0 --port $MOBILE_PORT$MOBILE_SSL_ARGS
Restart=on-failure
RestartSec=2
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

cat > "$DESKTOP_SERVICE_FILE" <<EOF
[Unit]
Description=murn. desktop loopback backend
After=network-online.target
$COMFY_UNIT_DEPS

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$UVICORN murn.main:app --host 127.0.0.1 --port $DESKTOP_PORT
Restart=on-failure
RestartSec=1
Environment=PYTHONUNBUFFERED=1
EOF

cat > "$DESKTOP_DIR/murn.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=murn.
Comment=Local-first AI assistant
Exec=$LAUNCHER_DEST
Icon=murn
Terminal=false
Categories=Utility;Development;
StartupNotify=true
StartupWMClass=murn-desktop
EOF

systemctl --user daemon-reload
systemctl --user enable --now murn.service
systemctl --user start murn-desktop-backend.service

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

LAN_IP=""
if command -v ip >/dev/null 2>&1; then
  LAN_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')"
fi

say "Installed."
printf 'Desktop launcher: %s\n' "$LAUNCHER_DEST"
printf 'Native binary: %s\n' "$BINARY_DEST"
printf 'Desktop log: %s\n' "$LOG_FILE"
printf 'Desktop backend: http://127.0.0.1:%s\n' "$DESKTOP_PORT"
printf 'Phone/LAN backend service: %s\n' "$MOBILE_SERVICE_FILE"
printf 'Desktop backend service: %s\n' "$DESKTOP_SERVICE_FILE"
if [[ "$COMFY_AVAILABLE" -eq 1 ]]; then
  printf 'Image backend service: %s\n' "$COMFY_SERVICE_FILE"
  printf 'ComfyUI: managed automatically on http://127.0.0.1:%s\n' "$COMFY_PORT"
  printf 'ComfyUI VRAM args: %s\n' "$COMFY_VRAM_ARGS"
fi
printf '\nOpen your application launcher and search for: murn.\n'
printf 'For this current fish shell, run once: fish_add_path ~/.local/bin\n'
printf 'Then start it with: murn-desktop\n'
printf 'Emergency WebKit mode: murn-desktop-safe\n'
if [[ -n "$LAN_IP" ]]; then
  printf '\nPhone UI remains available at: %s://%s:%s/mobile\n' "$MOBILE_SCHEME" "$LAN_IP" "$MOBILE_PORT"
else
  printf '\nPhone UI remains available at /mobile on this PC LAN address.\n'
fi