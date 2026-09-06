from typing import Sequence

import httpx


class OllamaEmbeddingProvider:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    @staticmethod
    def _matches(configured: str, loaded: str) -> bool:
        return loaded == configured or loaded.startswith(f"{configured}:")

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
        except (httpx.HTTPError, ValueError):
            return False

        names = {str(item.get("name", "")) for item in models}
        return self.model in names or any(name.startswith(f"{self.model}:") for name in names)

    async def loaded(self) -> bool:
        """Check whether this embedding model currently occupies Ollama runtime memory."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/ps")
                response.raise_for_status()
                models = response.json().get("models", [])
        except (httpx.HTTPError, ValueError):
            return False

        return any(
            self._matches(self.model, str(item.get("name") or item.get("model") or ""))
            for item in models
        )

    async def unload(self) -> bool:
        """Release the embedding model if it is resident, avoiding unnecessary loads."""
        if not await self.loaded():
            return True
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}/api/embed",
                    json={
                        "model": self.model,
                        "input": "",
                        "truncate": True,
                        "keep_alive": 0,
                    },
                )
                response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    async def embed(self, inputs: str | Sequence[str]) -> list[list[float]]:
        payload = {
            "model": self.model,
            "input": inputs if isinstance(inputs, str) else list(inputs),
            "truncate": True,
        }

        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{self.base_url}/api/embed", json=payload)
            response.raise_for_status()
            data = response.json()

        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings:
            raise RuntimeError("Ollama returned no embeddings.")
        return embeddings
