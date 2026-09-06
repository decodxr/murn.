import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from murn.providers.ollama import OllamaProvider
from murn.tool_router import select_tool_definitions, tool_guidance
from murn.tools.registry import ToolRegistry


SYSTEM_PROMPT_FALLBACK = """Você é murn., uma IA pessoal local.
Fale em português brasileiro natural, direto e com personalidade.
Não soe como chatbot corporativo. Não comece com confirmações genéricas, não repita o pedido e não
termine com frases de atendimento. Seja útil, preciso e honesto sobre ações e ferramentas.
"""

# Recent conversation remains in the model context. Durable facts belong in the
# long-term Obsidian memory instead of making every request slower forever.
HISTORY_MAX_MESSAGES = 24
HISTORY_MAX_CHARS = 18000


class Agent:
    def __init__(
        self,
        llm: OllamaProvider,
        tools: ToolRegistry,
        max_steps: int = 8,
        system_prompt_path: Path | None = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.system_prompt_path = system_prompt_path or Path("prompts/system.md")

    def system_prompt(self) -> str:
        """Load the editable base prompt fresh for every request."""
        path = self.system_prompt_path.expanduser()
        try:
            prompt = path.read_text(encoding="utf-8").strip()
        except OSError:
            return SYSTEM_PROMPT_FALLBACK
        return prompt or SYSTEM_PROMPT_FALLBACK

    @staticmethod
    def _recent_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
        if not history:
            return []

        selected: list[dict[str, str]] = []
        used_chars = 0
        for item in reversed(history[-HISTORY_MAX_MESSAGES:]):
            content = str(item.get("content") or "")
            size = len(content)
            if selected and used_chars + size > HISTORY_MAX_CHARS:
                break
            selected.append(item)
            used_chars += size
            if used_chars >= HISTORY_MAX_CHARS:
                break
        selected.reverse()
        return selected

    def _messages(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
        tool_definitions: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt()},
        ]
        guidance = tool_guidance(tool_definitions or [])
        if guidance:
            messages.append({"role": "system", "content": guidance})
        messages.extend(self._recent_history(history))
        messages.append({"role": "user", "content": message})
        return messages

    @staticmethod
    def _tool_result_for_model(name: str, result: dict[str, Any]) -> dict[str, Any]:
        if name != "generate_image" or not isinstance(result, dict):
            return result

        safe = dict(result)
        safe_images: list[dict[str, Any]] = []
        for image in result.get("images") or []:
            if not isinstance(image, dict):
                continue
            safe_images.append(
                {
                    key: value
                    for key, value in image.items()
                    if key in {"filename", "subfolder", "type"}
                }
            )
        safe["images"] = safe_images
        safe["display"] = "Rendered inline by the murn. client. Do not output a URL."
        return safe

    def _tool_definitions(self, message: str) -> list[dict[str, Any]]:
        return select_tool_definitions(message, self.tools.definitions())

    async def _execute_tool(self, name: str, arguments: Any) -> dict[str, Any]:
        if name == "generate_image":
            await self.llm.unload()
        return await self.tools.execute(name, arguments)

    async def run(self, message: str, history: list[dict[str, str]] | None = None) -> str:
        tool_definitions = self._tool_definitions(message)
        messages = self._messages(message, history, tool_definitions)

        for _ in range(self.max_steps):
            assistant = await self.llm.chat(messages, tool_definitions)
            tool_calls = assistant.get("tool_calls") or []

            if not tool_calls:
                return assistant.get("content", "")

            messages.append(assistant)
            for call in tool_calls:
                function = call.get("function", {})
                name = function.get("name", "")
                arguments = function.get("arguments", {})
                try:
                    result = await self._execute_tool(name, arguments)
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}

                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(
                            self._tool_result_for_model(name, result),
                            ensure_ascii=False,
                        ),
                    }
                )

        return "Atingi o limite de etapas de ferramentas antes de concluir este pedido."

    async def stream(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        tool_definitions = self._tool_definitions(message)
        messages = self._messages(message, history, tool_definitions)
        visible_parts: list[str] = []

        for _ in range(self.max_steps):
            content_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            seen_tool_calls: set[str] = set()

            async for chunk in self.llm.stream_chat(messages, tool_definitions):
                assistant_chunk = chunk.get("message") or {}
                content = assistant_chunk.get("content") or ""
                if content:
                    content_parts.append(content)
                    visible_parts.append(content)
                    yield {"type": "token", "content": content}

                for call in assistant_chunk.get("tool_calls") or []:
                    key = json.dumps(call, sort_keys=True, ensure_ascii=False)
                    if key not in seen_tool_calls:
                        seen_tool_calls.add(key)
                        tool_calls.append(call)

            assistant: dict[str, Any] = {
                "role": "assistant",
                "content": "".join(content_parts),
            }
            if tool_calls:
                assistant["tool_calls"] = tool_calls

            if not tool_calls:
                yield {"type": "done", "content": "".join(visible_parts)}
                return

            messages.append(assistant)
            for call in tool_calls:
                function = call.get("function", {})
                name = function.get("name", "")
                arguments = function.get("arguments", {})
                yield {"type": "tool_start", "name": name, "arguments": arguments}

                try:
                    result = await self._execute_tool(name, arguments)
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}

                yield {"type": "tool_result", "name": name, "result": result}
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(
                            self._tool_result_for_model(name, result),
                            ensure_ascii=False,
                        ),
                    }
                )

        limit_message = "Atingi o limite de etapas de ferramentas antes de concluir este pedido."
        visible_parts.append(limit_message)
        yield {"type": "token", "content": limit_message}
        yield {"type": "done", "content": "".join(visible_parts)}
