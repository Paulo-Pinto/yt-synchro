"""Configuration management for yt-synchro."""

import tomllib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


CONFIG_DIR = Path.home() / ".config" / "yt-synchro"
CONFIG_FILE = CONFIG_DIR / "config.toml"
STATE_FILE = CONFIG_DIR / "state.json"
LOG_FILE = CONFIG_DIR / "yt-synchro.log"

DEFAULTS = {
    "playlist_url": "",
    "output_dir": str(Path.home() / "Downloads" / "yt-synchro"),
    "max_storage_gb": 50.0,
    "max_videos": 20,
    "parallel": 3,
    "quality": "1080p",
    "daemon_interval_minutes": 60,
    "video_max_age_days": 14,
}


@dataclass
class Config:
    playlist_url: str = ""
    output_dir: str = str(Path.home() / "Downloads" / "yt-synchro")
    max_storage_gb: float = 50.0
    max_videos: int = 20
    parallel: int = 3
    quality: str = "1080p"
    daemon_interval_minutes: int = 60
    video_max_age_days: int = 14

    @classmethod
    def from_toml(cls, path: Path) -> "Config":
        if not path.exists():
            return cls()
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for key, value in asdict(self).items():
                if value:
                    f.write(f'{key} = {toml_repr(value)}\n')


def toml_repr(value) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def load_config(overrides: Optional[dict] = None) -> Config:
    config = Config.from_toml(CONFIG_FILE)
    if overrides:
        for key, value in overrides.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)
    return config


def ensure_config() -> Config:
    if not CONFIG_FILE.exists():
        config = Config()
        config.save(CONFIG_FILE)
        return config
    return load_config()
