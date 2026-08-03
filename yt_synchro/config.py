"""Configuration management for yt-synchro."""

import json
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".config" / "yt-synchro"
CONFIG_FILE = CONFIG_DIR / "config.toml"
STATE_FILE = CONFIG_DIR / "state.json"
LOG_FILE = CONFIG_DIR / "yt-synchro.log"

_VALID_QUALITIES = {"best", "2160p", "1440p", "1080p", "720p", "480p", "360p"}


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
                f.write(f"{key} = {toml_repr(value)}\n")

    def validate(self) -> None:
        """Raise ValueError for configuration values that would break the app."""
        if self.max_storage_gb < 0:
            raise ValueError(f"max_storage_gb must be >= 0, got {self.max_storage_gb}")
        if self.max_videos <= 0:
            raise ValueError(f"max_videos must be > 0, got {self.max_videos}")
        if self.parallel <= 0:
            raise ValueError(f"parallel must be > 0, got {self.parallel}")
        if self.daemon_interval_minutes <= 0:
            raise ValueError(
                f"daemon_interval_minutes must be > 0, got {self.daemon_interval_minutes}"
            )
        if self.video_max_age_days < 0:
            raise ValueError(f"video_max_age_days must be >= 0, got {self.video_max_age_days}")
        if self.quality not in _VALID_QUALITIES:
            raise ValueError(f"quality must be one of {_VALID_QUALITIES}, got {self.quality!r}")


def toml_repr(value) -> str:
    if isinstance(value, str):
        # JSON string escaping is a valid subset of TOML basic-string escaping.
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def load_config(overrides: Optional[dict] = None) -> Config:
    config = Config.from_toml(CONFIG_FILE)
    if overrides:
        for key, value in overrides.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)
    config.validate()
    return config


def ensure_config() -> Config:
    if not CONFIG_FILE.exists():
        config = Config()
        config.save(CONFIG_FILE)
        return config
    return load_config()
