from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


class WebProvider:
    SEARCH_URL = "https://html.duckduckgo.com/html/"

    def __init__(
        self,
        enabled: bool = True,
        max_results: int = 6,
        open_max_chars: int = 12000,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.enabled = enabled
        self.max_results = max(1, min(int(max_results), 10))
        self.open_max_chars = max(1000, min(int(open_max_chars), 50000))
        self.timeout_seconds = max(3.0, float(timeout_seconds))
        self.user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131 Safari/537.36 murn/0.7"
        )

    @staticmethod
    def _unwrap_duckduckgo_url(url: str) -> str:
        if url.startswith("//"):
            url = f"https:{url}"
        parsed = urlparse(url)
        if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            if target:
                return unquote(target)
        return url

    @staticmethod
    def _is_public_ip(value: str) -> bool:
        ip = ipaddress.ip_address(value)
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )

    async def _validate_public_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Only public http/https URLs are allowed.")
        if parsed.username or parsed.password:
            raise ValueError("URLs containing credentials are not allowed.")

        host = (parsed.hostname or "").strip().lower().rstrip(".")
        if not host:
            raise ValueError("URL has no hostname.")
        if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
            raise ValueError("Local/private hosts are blocked.")

        try:
            ipaddress.ip_address(host)
        except ValueError:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            try:
                infos = await asyncio.to_thread(
                    socket.getaddrinfo,
                    host,
                    port,
                    type=socket.SOCK_STREAM,
                )
            except socket.gaierror as exc:
                raise ValueError(f"Could not resolve host: {host}") from exc

            addresses = {item[4][0] for item in infos}
            if not addresses or any(not self._is_public_ip(address) for address in addresses):
                raise ValueError("Local/private network targets are blocked.")
        else:
            if not self._is_public_ip(host):
                raise ValueError("Local/private network targets are blocked.")

        return url

    async def search(self, query: str, limit: int | None = None) -> dict[str, object]:
        if not self.enabled:
            raise RuntimeError("Web access is disabled.")

        query = query.strip()
        if not query:
            raise ValueError("Search query is empty.")

        final_limit = max(1, min(int(limit or self.max_results), 10))
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                self.SEARCH_URL,
                params={"q": query},
                headers=headers,
            )
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        results: list[dict[str, str]] = []

        for block in soup.select(".result"):
            link = block.select_one(".result__a")
            if link is None:
                continue
            href = self._unwrap_duckduckgo_url(str(link.get("href") or "").strip())
            if not href.startswith(("http://", "https://")):
                continue

            snippet_node = block.select_one(".result__snippet")
            snippet = " ".join(snippet_node.stripped_strings) if snippet_node else ""
            title = " ".join(link.stripped_strings)
            results.append(
                {
                    "title": title,
                    "url": href,
                    "snippet": snippet,
                }
            )
            if len(results) >= final_limit:
                break

        # DuckDuckGo occasionally changes wrappers; keep a lightweight fallback.
        if not results:
            for link in soup.select("a.result__a"):
                href = self._unwrap_duckduckgo_url(str(link.get("href") or "").strip())
                if not href.startswith(("http://", "https://")):
                    continue
                results.append(
                    {
                        "title": " ".join(link.stripped_strings),
                        "url": href,
                        "snippet": "",
                    }
                )
                if len(results) >= final_limit:
                    break

        return {
            "query": query,
            "engine": "duckduckgo",
            "searched_at": datetime.now(timezone.utc).isoformat(),
            "results": results,
        }

    async def open(self, url: str, max_chars: int | None = None) -> dict[str, object]:
        if not self.enabled:
            raise RuntimeError("Web access is disabled.")

        current = await self._validate_public_url(url.strip())
        char_limit = max(1000, min(int(max_chars or self.open_max_chars), 50000))
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,text/plain,application/json;q=0.9,*/*;q=0.5",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
        }

        body = b""
        media_type = ""
        final_url = current
        title = ""

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False) as client:
            for _ in range(6):
                async with client.stream("GET", current, headers=headers) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise RuntimeError("Redirect response had no Location header.")
                        current = await self._validate_public_url(urljoin(current, location))
                        continue

                    response.raise_for_status()
                    final_url = str(response.url)
                    media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if media_type and not (
                        media_type.startswith("text/")
                        or media_type in {"application/xhtml+xml", "application/json"}
                    ):
                        raise ValueError(f"Unsupported page content type: {media_type}")

                    chunks: list[bytes] = []
                    total = 0
                    max_bytes = 2_000_000
                    async for chunk in response.aiter_bytes():
                        if total + len(chunk) > max_bytes:
                            remaining = max_bytes - total
                            if remaining > 0:
                                chunks.append(chunk[:remaining])
                            break
                        chunks.append(chunk)
                        total += len(chunk)
                    body = b"".join(chunks)
                    break
            else:
                raise RuntimeError("Too many redirects.")

        text = body.decode("utf-8", errors="replace")
        if media_type in {"text/html", "application/xhtml+xml", ""}:
            soup = BeautifulSoup(text, "html.parser")
            if soup.title:
                title = " ".join(soup.title.stripped_strings)

            for node in soup.select("script, style, noscript, svg, canvas, template"):
                node.decompose()

            container = soup.find("main") or soup.find("article") or soup.body or soup
            raw_lines = [" ".join(part.split()) for part in container.stripped_strings]
            lines: list[str] = []
            previous = None
            for line in raw_lines:
                if not line or line == previous:
                    continue
                lines.append(line)
                previous = line
            content = "\n".join(lines)
        else:
            content = text

        content = re.sub(r"\n{3,}", "\n\n", content).strip()
        truncated = len(content) > char_limit
        if truncated:
            content = content[:char_limit].rstrip() + "\n[…truncated…]"

        return {
            "url": final_url,
            "title": title,
            "content_type": media_type or "text/html",
            "content": content,
            "truncated": truncated,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
