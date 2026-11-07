from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOVELISTA_", env_file=".env", extra="ignore")

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.6:35b-a3b"
    data_dir: Path = Path(__file__).resolve().parent.parent / "data" / "novels"
    db_url: str = ""

    def resolved_db_url(self) -> str:
        if self.db_url:
            return self.db_url
        db_path = Path(__file__).resolve().parent.parent / "data" / "novelista.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path.as_posix()}"


settings = AppSettings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
