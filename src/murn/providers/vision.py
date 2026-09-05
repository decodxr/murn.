import base64
from typing import Any

import httpx


VISION_SYSTEM_PROMPT = """Você é o sistema de visão do murn., um assistente local.
Analise a imagem com atenção e responda em português brasileiro por padrão.
Quando houver texto legível, transcreva ou resuma apenas o que realmente conseguir ler.
Não invente detalhes que não estejam visíveis. Se algo estiver incerto, diga que está incerto.
Se a imagem for um print de erro, interface, código, gráfico, documento ou exercício, priorize uma
análise útil e prática do conteúdo visível.
"""


class OllamaVisionProvider:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def health(self) -> bool:
        if not self.model:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
        except (httpx.HTTPError, ValueError):
            return False

        names = {str(item.get("name", "")) for item in models}
        return self.model in names or any(name.startswith(f"{self.model}:") for name in names)

    async def unload(self) -> bool:
        if not self.model:
            return False
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": self.model, "keep_alive": 0},
                )
                response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    async def analyze(
        self,
        image: bytes,
        prompt: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        if not image:
            raise ValueError("Image is empty.")
        if not self.model:
            raise RuntimeError("MURN_VISION_MODEL is not configured.")

        question = prompt.strip() or "Analise esta imagem detalhadamente."
        encoded = base64.b64encode(image).decode("ascii")

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
        ]

        # A little text context helps follow-up questions without trying to make the
        # normal text model understand image bytes. Keep it short so vision stays fast.
        for item in (history or [])[-6:]:
            role = str(item.get("role", ""))
            content = str(item.get("content", ""))
            if role not in {"user", "assistant"} or not content:
                continue
            # Strip murn's saved-image marker from textual context.
            if content.startswith("[[murn-image:"):
                marker_end = content.find("]]" )
                if marker_end >= 0:
                    content = content[marker_end + 2 :].lstrip()
            messages.append({"role": role, "content": content[:4000]})

        messages.append(
            {
                "role": "user",
                "content": question,
                "images": [encoded],
            }
        )

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            # Vision is loaded only for the request. This matters on an 8 GB GPU
            # because ComfyUI and the normal LLM share the same VRAM.
            "keep_alive": 0,
        }

        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        message = data.get("message") or {}
        answer = str(message.get("content") or "").strip()
        if not answer:
            raise RuntimeError("Ollama vision model returned an empty answer.")
        return answer
