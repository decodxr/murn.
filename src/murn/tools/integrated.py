from __future__ import annotations

from typing import Any

from murn.app_control import open_orbital
from murn.tools.registry import ToolRegistry


class IntegratedToolRegistry(ToolRegistry):
    """Tool registry with local app integration actions."""

    def definitions(self) -> list[dict[str, Any]]:
        tools = super().definitions()
        if self.browser.configured:
            tools.insert(
                2,
                {
                    "type": "function",
                    "function": {
                        "name": "browser_launch",
                        "description": (
                            "Open/start the local Orbital browser app with the murn. integration enabled. "
                            "Use when the user asks to open, start or launch Orbital."
                        ),
                        "parameters": {"type": "object", "properties": {}},
                    },
                },
            )
        return tools

    async def execute(self, name: str, arguments: Any) -> dict[str, Any]:
        if name == "browser_launch":
            return await open_orbital()
        return await super().execute(name, arguments)
