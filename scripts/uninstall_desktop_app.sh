#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now murn.service >/dev/null 2>&1 || true
rm -f "$HOME/.config/systemd/user/murn.service"
rm -f "$HOME/.local/bin/murn-desktop"
rm -f "$HOME/.local/share/applications/murn.desktop"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/murn.svg"
rm -f "$HOME/.config/murn/desktop-url"
systemctl --user daemon-reload

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi

printf 'murn. desktop app removed.\n'
printf 'The repository, .env, models, memories, sessions, and mobile UI were not deleted.\n'
