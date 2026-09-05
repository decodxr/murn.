from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MURN_",
        extra="ignore",
    )

    name: str = "murn."

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1:8b"
    embedding_model: str = "embeddinggemma"
    vision_model: str = "qwen2.5vl:3b"
    vision_max_mb: int = 20

    # Editable personality / behavior prompt. It is read on every message,
    # so changes take effect immediately without restarting the backend.
    system_prompt_path: Path = Path("prompts/system.md")

    # Public internet research. web_open deliberately blocks localhost/private LAN
    # targets; this gives the model research access without raw access to local services.
    web_enabled: bool = True
    web_max_results: int = 6
    web_open_max_chars: int = 12000
    web_timeout_seconds: float = 15.0

    # Orbital/Chromium control through Chrome DevTools Protocol. Keep this endpoint
    # bound to loopback only; it can control the logged-in browser session.
    browser_enabled: bool = True
    orbital_url: str = "http://127.0.0.1:9222"
    browser_timeout_seconds: float = 12.0
    browser_snapshot_max_chars: int = 12000
    browser_snapshot_max_elements: int = 120

    obsidian_vault: Path = Path("~/Documents/Obsidian").expanduser()
    obsidian_memory_dir: str = "murn"

    comfyui_url: str = "http://127.0.0.1:8188"
    comfy_workflow_path: Path = Path("workflows/txt2img_api.json")
    comfy_positive_node: str = ""
    comfy_negative_node: str = ""
    comfy_seed_node: str = ""
    comfy_latent_node: str = ""

    data_dir: Path = Path(".murn")
    session_db_name: str = "sessions.db"
    semantic_db_name: str = "memory_embeddings.db"

    whisper_cli: Path = Path("~/AI/whisper.cpp/build/bin/whisper-cli")
    whisper_model: Path = Path("~/AI/whisper.cpp/models/ggml-base.bin")
    whisper_language: str = "auto"
    whisper_no_gpu: bool = False
    ffmpeg_bin: str = "ffmpeg"
    piper_model: Path = Path("~/.local/share/murn/voices/pt_BR-faber-medium.onnx")
    audio_max_mb: int = 25

    agent_max_steps: int = 12

    @property
    def session_db(self) -> Path:
        return self.data_dir.expanduser() / self.session_db_name

    @property
    def semantic_db(self) -> Path:
        return self.data_dir.expanduser() / self.semantic_db_name

    @property
    def audio_dir(self) -> Path:
        return self.data_dir.expanduser() / "audio"

    @property
    def vision_dir(self) -> Path:
        return self.data_dir.expanduser() / "vision"


settings = Settings()
