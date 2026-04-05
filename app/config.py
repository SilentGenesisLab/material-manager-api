import json
from pathlib import Path

from pydantic_settings import BaseSettings

# Persistent config file outside the repo — survives git pull / redeploy
PERSISTENT_CONFIG_PATH = Path.home() / ".material-manager-config.json"


class Settings(BaseSettings):
    FILE_URL: str = "./storage"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def _load_settings() -> Settings:
    """Load settings: persistent config > .env > default."""
    s = Settings()
    if PERSISTENT_CONFIG_PATH.exists():
        try:
            data = json.loads(PERSISTENT_CONFIG_PATH.read_text(encoding="utf-8"))
            if "FILE_URL" in data:
                s.FILE_URL = data["FILE_URL"]
        except (json.JSONDecodeError, OSError):
            pass
    return s


def save_persistent_config(file_url: str) -> None:
    """Persist FILE_URL to a file outside the repo."""
    data = {}
    if PERSISTENT_CONFIG_PATH.exists():
        try:
            data = json.loads(PERSISTENT_CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    data["FILE_URL"] = file_url
    PERSISTENT_CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


settings = _load_settings()
