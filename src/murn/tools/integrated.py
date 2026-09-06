from __future__ import annotations

import asyncio
import json
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

    @staticmethod
    def _arguments(arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, str):
            return json.loads(arguments)
        return arguments or {}

    async def execute(self, name: str, arguments: Any) -> dict[str, Any]:
        if name == "browser_launch":
            return await open_orbital()

        if name.startswith("workspace_"):
            args = self._arguments(arguments)
            if name == "workspace_roots":
                return self.workspace.roots_info()
            if name == "workspace_list":
                return await asyncio.to_thread(
                    self.workspace.list,
                    args.get("path"),
                    int(args.get("depth", 2)),
                    int(args.get("limit", 220)),
                )
            if name == "workspace_read":
                return await asyncio.to_thread(
                    self.workspace.read,
                    str(args["path"]),
                    int(args.get("start_line", 1)),
                    args.get("end_line"),
                )
            if name == "workspace_search":
                return await asyncio.to_thread(
                    self.workspace.search,
                    str(args["query"]),
                    args.get("path"),
                    int(args.get("limit", 40)),
                )
            if name == "workspace_git_status":
                return await asyncio.to_thread(self.workspace.git_status, args.get("path"))
            if name == "workspace_git_diff":
                return await asyncio.to_thread(
                    self.workspace.git_diff,
                    args.get("path"),
                    bool(args.get("staged", False)),
                )

        if name == "generate_image":
            # Semantic memory may have left embeddinggemma resident in Ollama.
            # Release it before ComfyUI competes for an 8 GB GPU. ToolRegistry
            # also unloads the chat LLM immediately before generation.
            await self.semantic_memory.embeddings.unload()

        return await super().execute(name, arguments)
