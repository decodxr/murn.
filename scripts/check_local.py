import asyncio

from murn.config import settings
from murn.providers.comfyui import ComfyUIProvider
from murn.providers.ollama import OllamaProvider


async def main() -> None:
    ollama = OllamaProvider(settings.ollama_url, settings.ollama_model)
    comfy = ComfyUIProvider(
        settings.comfyui_url,
        settings.comfy_workflow_path,
        settings.comfy_positive_node,
        settings.comfy_negative_node,
        settings.comfy_seed_node,
        settings.comfy_latent_node,
    )

    print(f"Ollama:  {'OK' if await ollama.health() else 'OFFLINE'}  {settings.ollama_url}")
    print(f"Model:   {settings.ollama_model}")
    print(f"ComfyUI: {'OK' if await comfy.health() else 'OFFLINE'}  {settings.comfyui_url}")
    print(f"Workflow configured: {'YES' if comfy.configured else 'NO'}")
    print(f"Obsidian vault: {settings.obsidian_vault}")


if __name__ == "__main__":
    asyncio.run(main())
