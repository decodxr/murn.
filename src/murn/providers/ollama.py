import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


class OllamaProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        keep_alive: str = "30m",
        num_ctx: int = 4096,
        num_predict: int = 512,
        temperature: float = 0.45,
        top_p: float = 0.9,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.keep_alive = keep_alive
        self.num_ctx = max(1024, int(num_ctx))
        self.num_predict = max(64, int(num_predict))
        self.temperature = max(0.0, min(2.0, float(temperature)))
        self.top_p = max(0.05, min(1.0, float(top_p)))
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(180.0, connect=10.0),
            limits=httpx.Limits(max_connections=12, max_keepalive_connections=6),
        )

    def _payload(
        self,
        messages: list[dict[str, Any]],
        stream: bool,
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        num_predict: int | None = None,
    ) -> dict[str, Any]:
        temp = self.temperature if temperature is None else max(0.0, min(2.0, float(temperature)))
        nucleus = self.top_p if top_p is None else max(0.05, min(1.0, float(top_p)))
        predict = self.num_predict if num_predict is None else max(32, int(num_predict))
        return {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": predict,
                "temperature": temp,
                "top_p": nucleus,
            },
        }

    async def health(self) -> bool:
        try:
            response = await self._client.get(f"{self.base_url}/api/tags", timeout=3)
            return response.is_success
        except httpx.HTTPError:
            return False

    async def warm(self) -> bool:
        """Load the configured model without making startup wait for generation."""
        try:
            response = await self._client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": self.keep_alive,
                },
                timeout=180,
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    async def unload(self) -> bool:
        """Ask Ollama to unload the active model and release its GPU memory."""
        try:
            response = await self._client.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "keep_alive": 0},
                timeout=30,
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        num_predict: int | None = None,
    ) -> dict[str, Any]:
        payload = self._payload(
            messages,
            stream=False,
            temperature=temperature,
            top_p=top_p,
            num_predict=num_predict,
        )
        if tools:
            payload["tools"] = tools

        response = await self._client.post(f"{self.base_url}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        return data["message"]

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        num_predict: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        payload = self._payload(
            messages,
            stream=True,
            temperature=temperature,
            top_p=top_p,
            num_predict=num_predict,
        )
        if tools:
            payload["tools"] = tools

        async with self._client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=None,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                yield json.loads(line)
