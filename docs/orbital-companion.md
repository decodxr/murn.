# murn. + Orbital Companion

murn. 0.10 introduces a two-way local integration with the custom Orbital/Chromium build.

## What is integrated

### murn. -> Orbital

- The murn. desktop topbar has an **ORBITAL** button.
- `Ctrl+Shift+O` opens Orbital from the murn. desktop app.
- The agent has `browser_launch`, so requests such as `abre o orbital` can start the browser.
- Existing CDP tools remain available for tabs, navigation, page snapshots, click, typing, keys, scrolling and history.

### Orbital -> murn.

The unpacked Manifest V3 extension under `orbital-extension/` adds:

- a native Chromium Side Panel containing a compact murn. chat;
- current-tab title/URL context;
- optional current-page context attached to a prompt;
- **Analyze page**;
- **Selection** analysis;
- right-click **Ask murn. about selected text**;
- right-click **Analyze this page with murn.**;
- right-click **Open murn. desktop**;
- extension action button opens the murn. Side Panel;
- omnibox keyword `murn.`;
- a custom Orbital new-tab page with murn-style glass UI;
- `murn. <question>` in the custom new-tab command box opens the Side Panel and sends the question;
- open murn. desktop from the Orbital UI.

The side panel shares the same FastAPI backend and chat/session store as the desktop app. Page content inserted as context is explicitly labeled as untrusted data.

## Install/update

```fish
cd ~/Projects/murn
git pull
source .venv/bin/activate.fish
python -m pip install -e '.[voice]'
systemctl --user restart murn.service
systemctl --user restart murn-desktop-backend.service
bash scripts/install_orbital_integration.sh
```

The installer expects the current custom build at:

```text
/home/enzom/Orbital/chromium/src/out/Orbital/chrome
```

Override it when necessary:

```fish
set -x MURN_ORBITAL_BIN /path/to/chrome
bash scripts/install_orbital_integration.sh
```

It creates:

```text
~/.local/bin/orbital-murn
~/.local/share/applications/orbital.desktop
~/.local/share/icons/hicolor/scalable/apps/orbital.svg
~/.local/share/orbital-murn-profile/
```

The launcher starts the murn. loopback backend, loads the companion extension and enables CDP only on loopback port 9222.

## Start

Use the KDE application menu entry **Orbital**, or:

```fish
orbital-murn
```

The extension is loaded automatically; no manual `chrome://extensions` step is required when the launcher accepts `--load-extension` normally.

Verify:

```fish
curl -s http://127.0.0.1:7332/health | jq '{version, browser, orbital_launcher, ollama_keep_alive}'
curl -s http://127.0.0.1:7332/v1/integration/status | jq
```

## Omnibox

Chromium's extension omnibox model activates a registered keyword through the address bar keyword flow. Type `murn.` and activate the keyword (normally Space or Tab), then type the prompt and press Enter.

The custom Orbital new-tab command field is more direct: `murn. explica isso` opens the murn. panel and sends the prompt.

## Performance changes in 0.10

- Simple chat no longer sends every tool schema to the local model.
- Web/browser/memory/image tools are routed only when the request needs them.
- Tool-specific system instructions are injected only for that request.
- The base system prompt is much smaller.
- Only the most recent 24 messages / roughly 18k characters of chat history are sent to the model; durable context remains in long-term memory.
- Ollama HTTP connections are reused.
- `llama3.1:8b` stays warm for 30 minutes by default.
- The backend begins loading the model in the background on startup.
- Health probes run concurrently.
- Desktop token rendering and scrolling are batched per animation frame.
- Expensive nested WebKitGTK backdrop filters and full-window glass animations were reduced while keeping the main Liquid Glass surfaces.

Optional `.env` tuning:

```env
MURN_OLLAMA_KEEP_ALIVE=30m
MURN_OLLAMA_NUM_CTX=4096
MURN_OLLAMA_NUM_PREDICT=512
MURN_ORBITAL_LAUNCHER=/home/enzom/.local/bin/orbital-murn
```

## Security boundary

CDP is bound to `127.0.0.1:9222`; do not expose it to the LAN. The Orbital extension talks to the murn. desktop backend on `127.0.0.1:7332`. Cross-origin API access is limited to `chrome-extension://` origins instead of arbitrary websites.

murn. treats page content as untrusted data. Browser interactions can be automated, but important external side effects (payment, publishing, deletion, security changes, important submissions) still require user authorization unless the user has explicitly authorized that exact action.

## Native Chromium chrome redesign

The companion extension redesigns the new-tab experience and adds a native Side Panel, but it cannot replace Chromium's own tab strip, toolbar, menus, downloads UI or Settings pages. Those live in the local Orbital Chromium source tree.

To fully reskin the browser chrome to match murn., the relevant Orbital source/patch files must be available in a repository or otherwise supplied for editing. Once available, the next phase is a native Views/WebUI theme covering tabs, toolbar, omnibox, menus, settings, downloads and internal pages.
