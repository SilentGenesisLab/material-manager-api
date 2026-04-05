import json
from pathlib import Path

from pydantic_settings import BaseSettings

# Persistent config inside repo: config/manager-config.json (gitignored)
PERSISTENT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "manager-config.json"


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
    """Persist FILE_URL to config/manager-config.json."""
    PERSISTENT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if PERSISTENT_CONFIG_PATH.exists():
        try:
            data = json.loads(PERSISTENT_CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    data["FILE_URL"] = file_url
    PERSISTENT_CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


settings = _load_settings()
