from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote

import httpx
import websockets


class OrbitalProvider:
    """Control Orbital/Chromium through the Chrome DevTools Protocol."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:9222",
        enabled: bool = True,
        timeout_seconds: float = 12.0,
        snapshot_max_chars: int = 12000,
        snapshot_max_elements: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.enabled = enabled
        self.timeout_seconds = max(3.0, float(timeout_seconds))
        self.snapshot_max_chars = max(1000, min(int(snapshot_max_chars), 50000))
        self.snapshot_max_elements = max(20, min(int(snapshot_max_elements), 300))
        self._target_id: str | None = None
        self._command_id = 0

    @property
    def configured(self) -> bool:
        return self.enabled and bool(self.base_url)

    async def health(self) -> bool:
        if not self.configured:
            return False
        try:
            async with httpx.AsyncClient(timeout=2.5) as client:
                response = await client.get(f"{self.base_url}/json/version")
                return response.is_success
        except httpx.HTTPError:
            return False

    async def status(self) -> dict[str, Any]:
        if not self.configured:
            return {"connected": False, "enabled": False, "url": self.base_url}
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(f"{self.base_url}/json/version")
                response.raise_for_status()
                version = response.json()
            return {
                "connected": True,
                "enabled": True,
                "url": self.base_url,
                "browser": version.get("Browser", ""),
                "protocol_version": version.get("Protocol-Version", ""),
            }
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "connected": False,
                "enabled": True,
                "url": self.base_url,
                "error": str(exc),
                "hint": (
                    "Start Orbital/Chromium with --remote-debugging-address=127.0.0.1 "
                    "--remote-debugging-port=9222"
                ),
            }

    async def tabs(self) -> dict[str, Any]:
        targets = await self._list_targets()
        pages = [item for item in targets if item.get("type") == "page"]
        if pages and not self._target_id:
            self._target_id = str(pages[0].get("id") or "") or None
        return {
            "tabs": [
                {
                    "id": item.get("id"),
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "active": item.get("id") == self._target_id,
                }
                for item in pages
            ]
        }

    async def focus_tab(self, target_id: str) -> dict[str, Any]:
        targets = await self._list_targets()
        page = next(
            (
                item
                for item in targets
                if item.get("type") == "page" and str(item.get("id")) == target_id
            ),
            None,
        )
        if page is None:
            raise ValueError(f"Browser tab {target_id!r} was not found.")
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(f"{self.base_url}/json/activate/{quote(target_id, safe='')}")
            response.raise_for_status()
        self._target_id = target_id
        return {
            "ok": True,
            "tab": target_id,
            "title": page.get("title", ""),
            "url": page.get("url", ""),
        }

    async def navigate(self, url: str) -> dict[str, Any]:
        url = url.strip()
        if not url:
            raise ValueError("URL is empty.")
        if "://" not in url:
            url = f"https://{url}"
        result = await self._cdp("Page.navigate", {"url": url})
        await asyncio.sleep(0.8)
        info = await self._page_info()
        return {"ok": True, "requested_url": url, **result, **info}

    async def snapshot(self) -> dict[str, Any]:
        max_chars = self.snapshot_max_chars
        max_elements = self.snapshot_max_elements
        expression = f"""
(() => {{
  const MAX_TEXT = {max_chars};
  const MAX_ELEMENTS = {max_elements};
  const visible = (el) => {{
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' &&
           Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
  }};
  const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();

  document.querySelectorAll('[data-murn-id]').forEach((el) => el.removeAttribute('data-murn-id'));
  const selector = [
    'a[href]', 'button', 'input', 'textarea', 'select', 'summary',
    '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="menuitem"]',
    '[contenteditable="true"]', '[tabindex]:not([tabindex="-1"])'
  ].join(',');

  const elements = [];
  let id = 1;
  for (const el of document.querySelectorAll(selector)) {{
    if (elements.length >= MAX_ELEMENTS || !visible(el)) continue;
    el.setAttribute('data-murn-id', String(id));
    const rect = el.getBoundingClientRect();
    elements.push({{
      id,
      tag: el.tagName.toLowerCase(),
      role: clean(el.getAttribute('role')),
      text: clean(el.innerText || el.textContent).slice(0, 220),
      aria_label: clean(el.getAttribute('aria-label')).slice(0, 180),
      placeholder: clean(el.getAttribute('placeholder')).slice(0, 180),
      name: clean(el.getAttribute('name')).slice(0, 120),
      type: clean(el.getAttribute('type')).slice(0, 80),
      href: clean(el.href).slice(0, 500),
      value: (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')
        ? clean(el.value).slice(0, 220) : '',
      disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height)
    }});
    id += 1;
  }}

  const text = clean(document.body ? document.body.innerText : '').slice(0, MAX_TEXT);
  return {{
    title: document.title,
    url: location.href,
    text,
    elements,
    viewport: {{ width: innerWidth, height: innerHeight, scrollY: Math.round(scrollY) }}
  }};
}})()
"""
        value = await self._evaluate(expression)
        if not isinstance(value, dict):
            raise RuntimeError("Browser snapshot returned an invalid result.")
        return value

    async def click(self, element_id: int) -> dict[str, Any]:
        expression = f"""
(() => {{
  const el = document.querySelector('[data-murn-id="{int(element_id)}"]');
  if (!el) return {{ok:false, error:'element not found; take a new browser_snapshot'}};
  if (el.disabled || el.getAttribute('aria-disabled') === 'true')
    return {{ok:false, error:'element is disabled'}};
  el.scrollIntoView({{block:'center', inline:'center', behavior:'instant'}});
  el.focus({{preventScroll:true}});
  el.click();
  return {{
    ok:true,
    tag:el.tagName.toLowerCase(),
    text:String(el.innerText || el.textContent || '').replace(/\\s+/g,' ').trim().slice(0,220),
    href:el.href || ''
  }};
}})()
"""
        result = await self._evaluate(expression)
        await asyncio.sleep(0.45)
        return result if isinstance(result, dict) else {"ok": bool(result)}

    async def type_text(self, element_id: int, text: str, clear: bool = True) -> dict[str, Any]:
        prep = f"""
(() => {{
  const el = document.querySelector('[data-murn-id="{int(element_id)}"]');
  if (!el) return {{ok:false, error:'element not found; take a new browser_snapshot'}};
  if (el.disabled || el.getAttribute('aria-disabled') === 'true')
    return {{ok:false, error:'element is disabled'}};
  el.scrollIntoView({{block:'center', inline:'center', behavior:'instant'}});
  el.focus({{preventScroll:true}});
  if ({str(bool(clear)).lower()}) {{
    if (el.isContentEditable) {{
      el.textContent = '';
    }} else if ('value' in el) {{
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
      if (descriptor && descriptor.set) descriptor.set.call(el, '');
      else el.value = '';
    }}
    el.dispatchEvent(new Event('input', {{bubbles:true, composed:true}}));
    el.dispatchEvent(new Event('change', {{bubbles:true, composed:true}}));
  }}
  return {{ok:true, tag:el.tagName.toLowerCase()}};
}})()
"""
        prepared = await self._evaluate(prep)
        if isinstance(prepared, dict) and not prepared.get("ok"):
            return prepared
        await self._cdp("Input.insertText", {"text": text})
        return {"ok": True, "element_id": int(element_id), "inserted_chars": len(text)}

    async def press(self, key: str) -> dict[str, Any]:
        key = key.strip()
        if not key:
            raise ValueError("Key is empty.")
        mapping: dict[str, tuple[str, str, int]] = {
            "enter": ("Enter", "Enter", 13),
            "tab": ("Tab", "Tab", 9),
            "escape": ("Escape", "Escape", 27),
            "esc": ("Escape", "Escape", 27),
            "backspace": ("Backspace", "Backspace", 8),
            "delete": ("Delete", "Delete", 46),
            "arrowup": ("ArrowUp", "ArrowUp", 38),
            "arrowdown": ("ArrowDown", "ArrowDown", 40),
            "arrowleft": ("ArrowLeft", "ArrowLeft", 37),
            "arrowright": ("ArrowRight", "ArrowRight", 39),
            "home": ("Home", "Home", 36),
            "end": ("End", "End", 35),
            "pagedown": ("PageDown", "PageDown", 34),
            "pageup": ("PageUp", "PageUp", 33),
            "space": (" ", "Space", 32),
        }
        normalized = key.lower().replace(" ", "")
        resolved = mapping.get(normalized)
        if resolved is None:
            if len(key) == 1:
                await self._cdp("Input.insertText", {"text": key})
                return {"ok": True, "key": key}
            raise ValueError(f"Unsupported key: {key}")

        actual_key, code, vk = resolved
        await self._cdp(
            "Input.dispatchKeyEvent",
            {
                "type": "keyDown",
                "key": actual_key,
                "code": code,
                "windowsVirtualKeyCode": vk,
                "nativeVirtualKeyCode": vk,
            },
        )
        await self._cdp(
            "Input.dispatchKeyEvent",
            {
                "type": "keyUp",
                "key": actual_key,
                "code": code,
                "windowsVirtualKeyCode": vk,
                "nativeVirtualKeyCode": vk,
            },
        )
        await asyncio.sleep(0.25)
        return {"ok": True, "key": actual_key}

    async def scroll(self, y: int = 700, x: int = 0) -> dict[str, Any]:
        value = await self._evaluate(
            f"window.scrollBy({{left:{int(x)}, top:{int(y)}, behavior:'instant'}}); "
            "({scrollX:Math.round(scrollX), scrollY:Math.round(scrollY)})"
        )
        return {"ok": True, **(value if isinstance(value, dict) else {})}

    async def back(self) -> dict[str, Any]:
        return await self._history_move(-1)

    async def forward(self) -> dict[str, Any]:
        return await self._history_move(1)

    async def _history_move(self, delta: int) -> dict[str, Any]:
        history = await self._cdp("Page.getNavigationHistory")
        entries = history.get("entries") or []
        index = int(history.get("currentIndex", 0)) + delta
        if index < 0 or index >= len(entries):
            return {"ok": False, "error": "no history entry in that direction"}
        entry = entries[index]
        await self._cdp("Page.navigateToHistoryEntry", {"entryId": entry["id"]})
        await asyncio.sleep(0.6)
        return {"ok": True, "url": entry.get("url", ""), "title": entry.get("title", "")}

    async def _page_info(self) -> dict[str, str]:
        value = await self._evaluate("({title:document.title,url:location.href})")
        if not isinstance(value, dict):
            return {}
        return {"title": str(value.get("title", "")), "url": str(value.get("url", ""))}

    async def _list_targets(self) -> list[dict[str, Any]]:
        if not self.configured:
            raise RuntimeError("Browser control is disabled.")
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.base_url}/json/list")
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                "Orbital CDP is not reachable. Start Orbital with "
                "--remote-debugging-address=127.0.0.1 --remote-debugging-port=9222"
            ) from exc
        if not isinstance(data, list):
            raise RuntimeError("Orbital CDP returned an invalid target list.")
        return data

    async def _target(self, target_id: str | None = None) -> dict[str, Any]:
        targets = await self._list_targets()
        pages = [
            item
            for item in targets
            if item.get("type") == "page" and item.get("webSocketDebuggerUrl")
        ]
        if not pages:
            raise RuntimeError("Orbital has no controllable page tabs.")

        wanted = target_id or self._target_id
        target = next((item for item in pages if str(item.get("id")) == wanted), None)
        if target is None:
            target = pages[0]
        self._target_id = str(target.get("id") or "") or None
        return target

    async def _cdp(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        target = await self._target(target_id)
        ws_url = str(target["webSocketDebuggerUrl"])
        self._command_id += 1
        command_id = self._command_id
        payload = {"id": command_id, "method": method, "params": params or {}}

        try:
            async with websockets.connect(
                ws_url,
                open_timeout=self.timeout_seconds,
                close_timeout=2,
                max_size=8 * 1024 * 1024,
            ) as websocket:
                await websocket.send(json.dumps(payload))
                while True:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=self.timeout_seconds)
                    message = json.loads(raw)
                    if message.get("id") != command_id:
                        continue
                    if "error" in message:
                        error = message["error"]
                        raise RuntimeError(error.get("message") or str(error))
                    result = message.get("result") or {}
                    return result if isinstance(result, dict) else {"value": result}
        except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as exc:
            raise RuntimeError(f"Orbital CDP command {method} failed: {exc}") from exc

    async def _evaluate(self, expression: str) -> Any:
        result = await self._cdp(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
        )
        exception = result.get("exceptionDetails")
        if exception:
            raise RuntimeError(str(exception.get("text") or exception))
        remote = result.get("result") or {}
        if remote.get("subtype") == "error":
            raise RuntimeError(str(remote.get("description") or "browser JavaScript error"))
        return remote.get("value")
