import json
from typing import Any

from murn.providers.ollama import OllamaProvider
from murn.tools.registry import ToolRegistry


SYSTEM_PROMPT = """You are murn., a local-first personal AI agent.

Be useful, concise, and natural. You can use registered tools when they help.
Search memory when past project context is likely relevant. Write memory only when the user explicitly
asks you to remember something or when information is clearly durable and useful for future work.
When image generation is available and the user asks to create an image, use the image tool.
Never claim a tool action succeeded unless the tool result says it did.
"""


class Agent:
    def __init__(self, llm: OllamaProvider, tools: ToolRegistry, max_steps: int = 8) -> None:
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps

    async def run(self, message: str, history: list[dict[str, str]] | None = None) -> str:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": message})

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
