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
    ollama_keep_alive: str = "30m"
    ollama_num_ctx: int = 4096
    ollama_num_predict: int = 512
    ollama_temperature: float = 0.45
    ollama_top_p: float = 0.9
    embedding_model: str = "embeddinggemma"
    vision_model: str = "qwen2.5vl:3b"
    vision_max_mb: int = 20

    # Identity and behavior prompts are read fresh on every request.
    identity_prompt_path: Path = Path("prompts/identity.md")
    system_prompt_path: Path = Path("prompts/system.md")

    # Public internet research.
    web_enabled: bool = True
    web_max_results: int = 6
    web_open_max_chars: int = 12000
    web_timeout_seconds: float = 15.0

    # Orbital/Chromium control through Chrome DevTools Protocol.
    browser_enabled: bool = True
    orbital_url: str = "http://127.0.0.1:9222"
    orbital_launcher: Path = Path("~/.local/bin/orbital-murn").expanduser()
    desktop_launcher: Path = Path("~/.local/bin/murn-desktop").expanduser()
    browser_timeout_seconds: float = 12.0
    browser_snapshot_max_chars: int = 12000
    browser_snapshot_max_elements: int = 120

    # Safe read-only coding workspace inspection. Semicolon-separated roots.
    workspace_enabled: bool = True
    workspace_roots: str = "~/Projects;~/Orbital"
    workspace_max_file_chars: int = 40000

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
