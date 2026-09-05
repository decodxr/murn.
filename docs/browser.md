# murn. + Orbital browser control

murn. can control the local Orbital/Chromium browser through Chrome DevTools Protocol (CDP).

The CDP endpoint is loopback-only by default:

```text
http://127.0.0.1:9222
```

Do not expose this port to the LAN or public internet. A CDP client can control the logged-in browser session.

## 1. Update/install murn.

```fish
cd ~/Projects/murn
git pull
source .venv/bin/activate.fish
python -m pip install -e '.[voice]'
```

Restart the backends after installing the new dependency:

```fish
systemctl --user restart murn.service
systemctl --user restart murn-desktop-backend.service
```

## 2. Start Orbital with CDP

For the user's current Chromium checkout the built browser is expected at:

```text
/home/enzom/Orbital/chromium/src/out/Orbital/chrome
```

The repo includes a launcher that uses a persistent controlled-browser profile:

```fish
cd ~/Projects/murn
bash scripts/run_orbital_for_murn.sh
```

Equivalent command:

```fish
~/Orbital/chromium/src/out/Orbital/chrome \
  --user-data-dir="$HOME/.local/share/orbital-murn-profile" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --no-first-run
```

The separate profile is deliberate: modern Chromium builds may restrict remote debugging against their default profile, and a separate profile also prevents the controlled instance from colliding with an already-running normal Orbital session. Log into sites once in this profile if you want murn. to operate those authenticated sessions later.

## 3. Verify CDP

```fish
curl http://127.0.0.1:9222/json/version
```

Then verify murn. sees it:

```fish
curl -s http://127.0.0.1:7332/health | jq '{browser, orbital_url}'
```

Expected:

```json
{
  "browser": true,
  "orbital_url": "http://127.0.0.1:9222"
}
```

## Browser tools

murn. exposes:

```text
browser_status
browser_tabs
browser_focus_tab
browser_snapshot
browser_navigate
browser_click
browser_type
browser_press
browser_scroll
browser_back
browser_forward
```

`browser_snapshot` is the core of interaction. It returns visible page text and numbered interactive elements. Example:

```text
[1] input  placeholder="Search"
[2] button text="Search"
[3] a      text="First result"
```

murn. uses those numeric IDs for `browser_click` and `browser_type`. A new snapshot should be taken whenever the page changes because element IDs are ephemeral.

## Typical agent flow

```text
user: open youtube and search for comfyui low vram

browser_status
browser_navigate -> https://youtube.com
browser_snapshot
browser_type -> search field
browser_press -> Enter
browser_snapshot
```

For simple information retrieval, murn. should prefer `web_search`/`web_open`; CDP is for actual browser interaction.

## Safety behavior

Page content is untrusted data and must never override murn.'s system prompt. The system prompt tells murn. to ignore prompt injection from websites.

Navigation, scrolling, searching and ordinary page interaction can be automatic. Before an important external side effect, murn. should stop before the final action and ask for confirmation unless the user already explicitly authorized that exact action. Examples include sending/publishing, buying/paying, deleting, changing security settings, and submitting an important form.

## Configuration

`.env` values:

```env
MURN_BROWSER_ENABLED=true
MURN_ORBITAL_URL=http://127.0.0.1:9222
MURN_BROWSER_TIMEOUT_SECONDS=12
MURN_BROWSER_SNAPSHOT_MAX_CHARS=12000
MURN_BROWSER_SNAPSHOT_MAX_ELEMENTS=120
MURN_AGENT_MAX_STEPS=12
```

The browser endpoint should remain loopback-only.
