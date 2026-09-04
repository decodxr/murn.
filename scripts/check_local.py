import asyncio

from murn.config import settings
from murn.providers.comfyui import ComfyUIProvider
from murn.providers.ollama import OllamaProvider
from murn.providers.speech import PiperTTSProvider, WhisperCppProvider


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
    stt = WhisperCppProvider(
        settings.whisper_cli,
        settings.whisper_model,
        settings.audio_dir,
        settings.ffmpeg_bin,
        settings.whisper_language,
        settings.whisper_no_gpu,
    )
    tts = PiperTTSProvider(settings.piper_model, settings.audio_dir)

    print(f"Ollama:  {'OK' if await ollama.health() else 'OFFLINE'}  {settings.ollama_url}")
    print(f"Model:   {settings.ollama_model}")
    print(f"ComfyUI: {'OK' if await comfy.health() else 'OFFLINE'}  {settings.comfyui_url}")
    print(f"Workflow configured: {'YES' if comfy.configured else 'NO'}")
    print(f"STT / whisper.cpp: {'OK' if await stt.health() else 'NOT CONFIGURED'}")
    print(f"Whisper model: {settings.whisper_model}")
    print(f"TTS / Piper: {'OK' if await tts.health() else 'NOT CONFIGURED'}")
    print(f"Piper model: {settings.piper_model}")
    print(f"Obsidian vault: {settings.obsidian_vault}")


if __name__ == "__main__":
    asyncio.run(main())
