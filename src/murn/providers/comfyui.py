import asyncio
import copy
import json
import random
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx


class ComfyUIProvider:
    def __init__(
        self,
        base_url: str,
        workflow_path: Path,
        positive_node: str = "",
        negative_node: str = "",
        seed_node: str = "",
        latent_node: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.workflow_path = workflow_path
        self.positive_node = positive_node
        self.negative_node = negative_node
        self.seed_node = seed_node
        self.latent_node = latent_node

    @property
    def configured(self) -> bool:
        return self.workflow_path.exists() and bool(self.positive_node)

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(f"{self.base_url}/queue")
                return response.is_success
        except httpx.HTTPError:
            return False

    def _workflow(self) -> dict[str, Any]:
        if not self.workflow_path.exists():
            raise RuntimeError(
                f"ComfyUI workflow not found: {self.workflow_path}. "
                "Export a workflow in API format first."
            )
        data = json.loads(self.workflow_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("ComfyUI API workflow must be a JSON object keyed by node ID.")
        return copy.deepcopy(data)

    @staticmethod
    def _node(workflow: dict[str, Any], node_id: str) -> dict[str, Any]:
        if node_id not in workflow:
            raise RuntimeError(f"ComfyUI node {node_id!r} was not found in the workflow.")
        return workflow[node_id]

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int | None = None,
        height: int | None = None,
        seed: int | None = None,
        timeout_seconds: int = 180,
    ) -> dict[str, Any]:
        if not self.positive_node:
            raise RuntimeError("MURN_COMFY_POSITIVE_NODE is not configured.")

        workflow = self._workflow()
        self._node(workflow, self.positive_node)["inputs"]["text"] = prompt

        if self.negative_node:
            self._node(workflow, self.negative_node)["inputs"]["text"] = negative_prompt

        final_seed = seed if seed is not None else random.randint(0, 2**63 - 1)
        if self.seed_node:
            self._node(workflow, self.seed_node)["inputs"]["seed"] = final_seed

        if self.latent_node:
            latent_inputs = self._node(workflow, self.latent_node)["inputs"]
            if width is not None:
                latent_inputs["width"] = width
            if height is not None:
                latent_inputs["height"] = height

        async with httpx.AsyncClient(timeout=30) as client:
            queued = await client.post(f"{self.base_url}/prompt", json={"prompt": workflow})
            queued.raise_for_status()
            prompt_id = queued.json()["prompt_id"]

        outputs = await self._wait_for_outputs(prompt_id, timeout_seconds)
        return {
            "prompt_id": prompt_id,
            "seed": final_seed,
            "images": outputs,
        }

    async def _wait_for_outputs(self, prompt_id: str, timeout_seconds: int) -> list[dict[str, str]]:
        deadline = asyncio.get_running_loop().time() + timeout_seconds

        async with httpx.AsyncClient(timeout=10) as client:
            while asyncio.get_running_loop().time() < deadline:
                response = await client.get(f"{self.base_url}/history/{prompt_id}")
                response.raise_for_status()
                data = response.json()
                entry = data.get(prompt_id, data)
                outputs = entry.get("outputs") if isinstance(entry, dict) else None
                if outputs:
                    images: list[dict[str, str]] = []
                    for node_output in outputs.values():
                        for image in node_output.get("images", []):
                            params = {
                                "filename": image["filename"],
                                "subfolder": image.get("subfolder", ""),
                                "type": image.get("type", "output"),
                            }
                            images.append(
                                {
                                    **params,
                                    "url": f"{self.base_url}/view?{urlencode(params)}",
                                }
                            )
                    if images:
                        return images
                await asyncio.sleep(1)

        raise TimeoutError(f"ComfyUI generation {prompt_id} did not finish in time.")
