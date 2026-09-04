import json
from typing import Any

from murn.memory.obsidian import ObsidianMemory
from murn.memory.semantic import SemanticMemory
from murn.providers.comfyui import ComfyUIProvider


class ToolRegistry:
    def __init__(
        self,
        memory: ObsidianMemory,
        semantic_memory: SemanticMemory,
        images: ComfyUIProvider,
    ) -> None:
        self.memory = memory
        self.semantic_memory = semantic_memory
        self.images = images

    def definitions(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": "memory_search",
                    "description": (
                        "Semantically search murn.'s long-term Obsidian memory for relevant context, "
                        "even when the query does not use the same words as the notes."
                    ),
                    "parameters": {
                        "type": "object",
                        "required": ["query"],
                        "properties": {
                            "query": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_write",
                    "description": (
                        "Write useful long-term information to murn.'s Obsidian memory. "
                        "Use for explicit remember requests or durable project context, not every message."
                    ),
                    "parameters": {
                        "type": "object",
                        "required": ["title", "content"],
                        "properties": {
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "tags": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            },
        ]

        if self.images.configured:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "generate_image",
                        "description": "Generate an image locally using the configured ComfyUI workflow.",
                        "parameters": {
                            "type": "object",
                            "required": ["prompt"],
                            "properties": {
                                "prompt": {"type": "string"},
                                "negative_prompt": {"type": "string"},
                                "width": {"type": "integer", "minimum": 64, "maximum": 4096},
                                "height": {"type": "integer", "minimum": 64, "maximum": 4096},
                                "seed": {"type": "integer"},
                            },
                        },
                    },
                }
            )

        return tools

    async def execute(self, name: str, arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        arguments = arguments or {}

        if name == "memory_search":
            query = str(arguments["query"])
            limit = int(arguments.get("limit", 5))
            try:
                results = await self.semantic_memory.search(query, limit)
                return {"mode": "semantic", "results": results}
            except Exception as exc:
                return {
                    "mode": "keyword-fallback",
                    "semantic_error": str(exc),
                    "results": self.memory.search(query, limit),
                }

        if name == "memory_write":
            result = self.memory.write(
                title=str(arguments["title"]),
                content=str(arguments["content"]),
                tags=list(arguments.get("tags") or []),
            )
            return {"saved": True, **result}

        if name == "generate_image":
            return await self.images.generate(
                prompt=str(arguments["prompt"]),
                negative_prompt=str(arguments.get("negative_prompt", "")),
                width=arguments.get("width"),
                height=arguments.get("height"),
                seed=arguments.get("seed"),
            )

        raise KeyError(f"Unknown tool: {name}")
