# murn. / internet research

murn. v0.7 adds controlled public-web research to the local agent.

## Tools

The language model receives two explicit tools:

- `web_search(query, limit)` — searches the public web through DuckDuckGo HTML search and returns title, snippet and URL.
- `web_open(url, max_chars)` — downloads a public page and extracts readable text for deeper research.

The model does **not** receive arbitrary network or shell access.

## Security boundary

`web_open` only accepts `http://` and `https://` public hosts. Before each request and redirect it resolves the hostname and rejects:

- localhost
- loopback addresses
- RFC/private LAN addresses
- link-local addresses
- reserved/multicast/unspecified addresses
- `.local` / `.localhost` hosts
- URLs containing credentials

This prevents the web research tool from being used as a straightforward SSRF path into Ollama, ComfyUI, the router, LAN devices or other local services.

Page contents are untrusted data. The system prompt tells murn. not to obey instructions embedded in web pages.

## Configuration

Defaults:

```env
MURN_WEB_ENABLED=true
MURN_WEB_MAX_RESULTS=6
MURN_WEB_OPEN_MAX_CHARS=12000
MURN_WEB_TIMEOUT_SECONDS=15
```

Set `MURN_WEB_ENABLED=false` to remove both tools from the model.

## Install/update

The page extractor uses BeautifulSoup:

```fish
cd ~/Projects/murn
source .venv/bin/activate.fish
python -m pip install -e '.[voice]'
```

Restart the running backends after updating Python code:

```fish
systemctl --user restart murn.service
systemctl --user restart murn-desktop-backend.service
```

## Quick test

Test the provider directly:

```fish
python - <<'PY'
import asyncio
from murn.providers.web import WebProvider

async def main():
    result = await WebProvider().search("Arch Linux latest kernel", 3)
    for item in result["results"]:
        print(item["title"])
        print(item["url"])
        print()

asyncio.run(main())
PY
```

Then ask murn. naturally, for example:

```text
pesquisa qual é a versão mais recente do KDE Plasma e me diz o que mudou
```

or:

```text
procura a documentação atual do Tauri sobre WebKitGTK no Linux e confirma isso pra mim
```

When freshness matters or the user explicitly requests research, the system prompt tells murn. to search instead of relying only on model knowledge.
