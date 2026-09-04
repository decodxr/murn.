#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${MURN_VENV:-$ROOT/.venv}"
UVICORN="$VENV/bin/uvicorn"
CARGO_MANIFEST="$ROOT/desktop-app/src-tauri/Cargo.toml"
BINARY_SOURCE="$ROOT/desktop-app/src-tauri/target/release/murn-desktop"
BINARY_DEST="$HOME/.local/bin/murn-desktop"
SERVICE_DIR="$HOME/.config/systemd/user"
MOBILE_SERVICE_FILE="$SERVICE_DIR/murn.service"
DESKTOP_SERVICE_FILE="$SERVICE_DIR/murn-desktop-backend.service"
CONFIG_DIR="$HOME/.config/murn"
URL_FILE="$CONFIG_DIR/desktop-url"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
DESKTOP_DIR="$HOME/.local/share/applications"
CERT="$HOME/.local/share/murn/certs/murn.pem"
KEY="$HOME/.local/share/murn/certs/murn-key.pem"
TAURI_ICON_DIR="$ROOT/desktop-app/src-tauri/icons"
TAURI_ICON="$TAURI_ICON_DIR/icon.png"
SOURCE_ICON="$ROOT/desktop-app/murn.svg"
DESKTOP_PORT=7332
MOBILE_PORT=7331
DESKTOP_URL="http://127.0.0.1:${DESKTOP_PORT}"

say() { printf '\n\033[1;35m[murn.]\033[0m %s\n' "$*"; }
fail() { printf '\n\033[1;31m[murn.] error:\033[0m %s\n' "$*" >&2; exit 1; }

[[ -x "$UVICORN" ]] || fail "uvicorn was not found at $UVICORN. Create/activate the murn. venv and install the project first."
command -v cargo >/dev/null 2>&1 || fail "cargo was not found. Install Rust first: sudo pacman -S --needed rust"
command -v systemctl >/dev/null 2>&1 || fail "systemctl was not found."
command -v rsvg-convert >/dev/null 2>&1 || fail "rsvg-convert was not found. Install it with: sudo pacman -S --needed librsvg"

systemctl --user stop murn.service >/dev/null 2>&1 || true
systemctl --user stop murn-desktop-backend.service >/dev/null 2>&1 || true

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

say "Desktop app will use loopback-only HTTP on 127.0.0.1:${DESKTOP_PORT}."
say "This avoids WebKit TLS/certificate blank-window issues without changing the UI."

say "Preparing native app icon..."
mkdir -p "$TAURI_ICON_DIR"
rsvg-convert -w 512 -h 512 "$SOURCE_ICON" -o "$TAURI_ICON"
[[ -s "$TAURI_ICON" ]] || fail "failed to generate $TAURI_ICON"

say "Building native Tauri shell..."
cargo build --release --manifest-path "$CARGO_MANIFEST"

mkdir -p "$(dirname "$BINARY_DEST")" "$SERVICE_DIR" "$CONFIG_DIR" "$ICON_DIR" "$DESKTOP_DIR"
install -m 0755 "$BINARY_SOURCE" "$BINARY_DEST"
install -m 0644 "$SOURCE_ICON" "$ICON_DIR/murn.svg"
printf '%s\n' "$DESKTOP_URL" > "$URL_FILE"

cat > "$MOBILE_SERVICE_FILE" <<EOF
[Unit]
Description=murn. LAN/mobile AI backend
After=network-online.target
Wants=network-online.target

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
Exec=$BINARY_DEST
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
printf 'Desktop app: %s\n' "$BINARY_DEST"
printf 'Desktop backend: http://127.0.0.1:%s\n' "$DESKTOP_PORT"
printf 'Phone/LAN backend service: %s\n' "$MOBILE_SERVICE_FILE"
printf 'Desktop backend service: %s\n' "$DESKTOP_SERVICE_FILE"
printf '\nOpen your application launcher and search for: murn.\n'
printf 'Or start it now with: murn-desktop\n'
if [[ -n "$LAN_IP" ]]; then
  printf '\nPhone UI remains available at: %s://%s:%s/mobile\n' "$MOBILE_SCHEME" "$LAN_IP" "$MOBILE_PORT"
else
  printf '\nPhone UI remains available at /mobile on this PC LAN address.\n'
fi
