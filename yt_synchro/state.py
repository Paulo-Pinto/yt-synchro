"""Download state tracking for yt-synchro."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import STATE_FILE


@dataclass
class VideoState:
    video_id: str
    title: str
    file_path: str
    downloaded_at: str  # ISO format
    status: str = "downloaded"  # downloaded, failed, removed

    @classmethod
    def create(cls, video_id: str, title: str, file_path: str) -> "VideoState":
        return cls(
            video_id=video_id,
            title=title,
            file_path=file_path,
            downloaded_at=datetime.now(timezone.utc).isoformat(),
        )


class StateManager:
    def __init__(self, state_file: Path = STATE_FILE):
        self.state_file = state_file
        self._videos: dict[str, VideoState] = {}
        self._load()

    def _load(self) -> None:
        if self.state_file.exists():
            with open(self.state_file) as f:
                data = json.load(f)
            for v in data.get("videos", []):
                state = VideoState(**v)
                self._videos[state.video_id] = state

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(
                {"videos": [asdict(v) for v in self._videos.values()]},
                f,
                indent=2,
            )

    def is_downloaded(self, video_id: str) -> bool:
        return video_id in self._videos and self._videos[video_id].status == "downloaded"

    def add(self, video: VideoState) -> None:
        self._videos[video.video_id] = video
        self._save()

    def mark_failed(self, video_id: str) -> None:
        if video_id in self._videos:
            self._videos[video_id].status = "failed"
            self._save()

    def remove(self, video_id: str) -> Optional[VideoState]:
        video = self._videos.pop(video_id, None)
        if video:
            self._save()
        return video

    def get(self, video_id: str) -> Optional[VideoState]:
        return self._videos.get(video_id)

    def get_all(self) -> list[VideoState]:
        return list(self._videos.values())

    def get_downloaded(self) -> list[VideoState]:
        return [v for v in self._videos.values() if v.status == "downloaded"]

    def get_count(self) -> int:
        total = 0
        for v in self.get_downloaded():
            path = Path(v.file_path)
            if path.exists():
                total += 1
        return total

    def get_total_size(self) -> int:
        total = 0
        for v in self.get_downloaded():
            path = Path(v.file_path)
            if path.exists():
                total += path.stat().st_size
        return total

    def get_oldest(self) -> Optional[VideoState]:
        downloaded = self.get_downloaded()
        if not downloaded:
            return None
        return min(downloaded, key=lambda v: v.downloaded_at)

    def cleanup_old(self, max_age_days: int) -> list[VideoState]:
        removed = []
        now = datetime.now(timezone.utc)
        for v in self.get_downloaded():
            downloaded_at = datetime.fromisoformat(v.downloaded_at)
            age_days = (now - downloaded_at).days
            if age_days > max_age_days:
                path = Path(v.file_path)
                if path.exists():
                    path.unlink()
                v.status = "removed"
                removed.append(v)
        if removed:
            self._save()
        return removed
