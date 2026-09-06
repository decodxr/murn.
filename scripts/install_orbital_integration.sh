#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORBITAL_BIN="${MURN_ORBITAL_BIN:-$HOME/Orbital/chromium/src/out/Orbital/chrome}"
PROFILE_DIR="${MURN_ORBITAL_PROFILE:-$HOME/.local/share/orbital-murn-profile}"
CDP_PORT="${MURN_ORBITAL_CDP_PORT:-9222}"
EXTENSION_DIR="$ROOT/orbital-extension"
EXTENSION_ICON="$EXTENSION_DIR/orbital.svg"
EXTENSION_ICONS="$EXTENSION_DIR/icons"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/orbital-murn"
APP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$APP_DIR/orbital.desktop"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
ICON_FILE="$ICON_DIR/orbital.svg"
ENV_FILE="$ROOT/.env"

say() { printf '\n\033[1;35m[murn. + orbital]\033[0m %s\n' "$*"; }
warn() { printf '\n\033[1;33m[warning]\033[0m %s\n' "$*"; }
fail() { printf '\n\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

set_env_key() {
  local key="$1"
  local value="$2"
  [[ -f "$ENV_FILE" ]] || return 0
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

[[ -x "$ORBITAL_BIN" ]] || fail "Orbital binary not found: $ORBITAL_BIN"
[[ -f "$EXTENSION_DIR/manifest.json" ]] || fail "extension not found: $EXTENSION_DIR"
command -v rsvg-convert >/dev/null 2>&1 || fail "rsvg-convert is required: sudo pacman -S --needed librsvg"

mkdir -p "$PROFILE_DIR" "$EXTENSION_ICONS" "$BIN_DIR" "$APP_DIR" "$ICON_DIR"

say "Generating Orbital / murn. extension icons..."
for size in 16 32 48 128; do
  rsvg-convert -w "$size" -h "$size" "$EXTENSION_ICON" -o "$EXTENSION_ICONS/$size.png"
done
install -m 0644 "$EXTENSION_ICON" "$ICON_FILE"

say "Installing integrated Orbital launcher..."
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
set -euo pipefail

ORBITAL_BIN="$ORBITAL_BIN"
PROFILE_DIR="$PROFILE_DIR"
EXTENSION_DIR="$EXTENSION_DIR"
CDP_PORT="$CDP_PORT"

# The side panel talks to the desktop loopback API even when the standalone
# murn. window is closed.
systemctl --user start murn-desktop-backend.service >/dev/null 2>&1 || true
systemctl --user start murn.service >/dev/null 2>&1 || true

mkdir -p "\$PROFILE_DIR"

exec "\$ORBITAL_BIN" \
  --user-data-dir="\$PROFILE_DIR" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port="\$CDP_PORT" \
  --load-extension="\$EXTENSION_DIR" \
  --no-first-run \
  "\$@"
EOF
chmod 0755 "$LAUNCHER"

say "Configuring murn. -> Orbital bridge..."
if [[ -f "$ENV_FILE" ]]; then
  set_env_key MURN_BROWSER_ENABLED true
  set_env_key MURN_ORBITAL_URL "http://127.0.0.1:$CDP_PORT"
  set_env_key MURN_ORBITAL_LAUNCHER "$LAUNCHER"
else
  warn "$ENV_FILE does not exist; built-in defaults will be used."
fi

say "Installing KDE desktop entry..."
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Orbital
Comment=Orbital browser integrated with murn.
Exec=$LAUNCHER %U
Icon=orbital
Terminal=false
Categories=Network;WebBrowser;
StartupNotify=true
StartupWMClass=chromium
MimeType=text/html;text/xml;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;
Actions=Murn;

[Desktop Action Murn]
Name=Open murn.
Exec=$HOME/.local/bin/murn-desktop
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

# Reload settings immediately. Restarting also kicks off the non-blocking model
# warmup so the first chat is less likely to pay a cold-load penalty.
systemctl --user restart murn-desktop-backend.service >/dev/null 2>&1 || true
systemctl --user restart murn.service >/dev/null 2>&1 || true

say "Installed."
printf 'Orbital launcher: %s\n' "$LAUNCHER"
printf 'Orbital app entry: %s\n' "$DESKTOP_FILE"
printf 'Orbital icon: %s\n' "$ICON_FILE"
printf 'Persistent profile: %s\n' "$PROFILE_DIR"
printf 'murn. extension: %s\n' "$EXTENSION_DIR"
printf 'CDP: http://127.0.0.1:%s\n' "$CDP_PORT"
printf '\nOpen it with: orbital-murn\n'
