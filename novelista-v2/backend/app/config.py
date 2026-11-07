from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOVELISTA_", env_file=".env", extra="ignore")

    data_dir: Path = Path(__file__).resolve().parents[2] / "data"

    @property
    def novels_dir(self) -> Path:
        return self.data_dir / "novels"


settings = AppSettings()
settings.novels_dir.mkdir(parents=True, exist_ok=True)
