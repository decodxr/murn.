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

    orbital_url: str | None = None
    agent_max_steps: int = 8

    @property
    def session_db(self) -> Path:
        return self.data_dir.expanduser() / self.session_db_name


settings = Settings()
