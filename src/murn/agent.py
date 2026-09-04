import json
from collections.abc import AsyncIterator
from typing import Any

from murn.providers.ollama import OllamaProvider
from murn.tools.registry import ToolRegistry


SYSTEM_PROMPT = """You are murn., a local-first personal AI agent.

Be useful, concise, and natural. You can use registered tools when they help.
Search memory when past project context is likely relevant. Write memory only when the user explicitly
asks you to remember something or when information is clearly durable and useful for future work.
When image generation is available and the user asks to create an image, use the image tool.
When a tool returns a useful local URL or output path, include it in the final answer.
Never claim a tool action succeeded unless the tool result says it did.
"""


class Agent:
    def __init__(self, llm: OllamaProvider, tools: ToolRegistry, max_steps: int = 8) -> None:
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps

    @staticmethod
    def _messages(message: str, history: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": message})
        return messages

    async def run(self, message: str, history: list[dict[str, str]] | None = None) -> str:
        messages = self._messages(message, history)

        for _ in range(self.max_steps):
            assistant = await self.llm.chat(messages, self.tools.definitions())
            tool_calls = assistant.get("tool_calls") or []

            if not tool_calls:
                return assistant.get("content", "")

            messages.append(assistant)
            for call in tool_calls:
                function = call.get("function", {})
                name = function.get("name", "")
                arguments = function.get("arguments", {})
                try:
                    result = await self.tools.execute(name, arguments)
                except Exception as exc:  # Tool failures are fed back to the model, not hidden.
                    result = {"ok": False, "error": str(exc)}

                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        return "I hit the tool-step limit before finishing this request."

    async def stream(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        messages = self._messages(message, history)
        visible_parts: list[str] = []

        for _ in range(self.max_steps):
            content_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            seen_tool_calls: set[str] = set()

            async for chunk in self.llm.stream_chat(messages, self.tools.definitions()):
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
                    result = await self.tools.execute(name, arguments)
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}

                yield {"type": "tool_result", "name": name, "result": result}
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        limit_message = "I hit the tool-step limit before finishing this request."
        visible_parts.append(limit_message)
        yield {"type": "token", "content": limit_message}
        yield {"type": "done", "content": "".join(visible_parts)}
