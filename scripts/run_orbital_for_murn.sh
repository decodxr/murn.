#!/usr/bin/env bash
set -euo pipefail

ORBITAL_BIN="${MURN_ORBITAL_BIN:-$HOME/Orbital/chromium/src/out/Orbital/chrome}"
PROFILE_DIR="${MURN_ORBITAL_PROFILE:-$HOME/.local/share/orbital-murn-profile}"
CDP_PORT="${MURN_ORBITAL_CDP_PORT:-9222}"

if [[ ! -x "$ORBITAL_BIN" ]]; then
  printf '[murn.] Orbital binary not found or not executable:\n  %s\n' "$ORBITAL_BIN" >&2
  printf '[murn.] Build it first or set MURN_ORBITAL_BIN.\n' >&2
  exit 1
fi

mkdir -p "$PROFILE_DIR"

if curl -fsS "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
  printf '[murn.] Orbital CDP is already available on 127.0.0.1:%s\n' "$CDP_PORT"
  exit 0
fi

printf '[murn.] starting Orbital with local CDP control...\n'
printf '[murn.] binary: %s\n' "$ORBITAL_BIN"
printf '[murn.] profile: %s\n' "$PROFILE_DIR"
printf '[murn.] CDP: http://127.0.0.1:%s\n' "$CDP_PORT"

exec "$ORBITAL_BIN" \
  --user-data-dir="$PROFILE_DIR" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port="$CDP_PORT" \
  --no-first-run \
  "$@"
