"""Download state tracking for yt-synchro."""

import json
import logging
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import STATE_FILE

logger = logging.getLogger(__name__)


@dataclass
class VideoState:
    video_id: str
    title: str
    file_path: str
    downloaded_at: str  # ISO format
    duration: Optional[float] = None  # seconds
    status: str = "downloaded"  # downloaded, failed, removed

    @classmethod
    def create(
        cls,
        video_id: str,
        title: str,
        file_path: str,
        duration: Optional[float] = None,
    ) -> "VideoState":
        return cls(
            video_id=video_id,
            title=title,
            file_path=file_path,
            duration=duration,
            downloaded_at=datetime.now(timezone.utc).isoformat(),
        )


class StateManager:
    def __init__(self, *, state_file: Path = STATE_FILE, output_dir: Path):
        self.state_file = state_file
        self._output_dir = output_dir
        self._videos: dict[str, VideoState] = {}
        self._lock = threading.Lock()
        self._load()

    def _resolve(self, file_path: str) -> Path:
        return Path(file_path).expanduser().resolve()

    def _sandbox(self, file_path: str) -> Path:
        """Return the resolved path if it lives under output_dir, else raise."""
        resolved = self._resolve(file_path)
        output_resolved = self._output_dir.expanduser().resolve()
        if not resolved.is_relative_to(output_resolved):
            raise ValueError(
                f"Path escapes output directory: {file_path!r} "
                f"(output_dir={output_resolved!r})"
            )
        return resolved

    def _load(self) -> None:
        if not self.state_file.exists():
            return
        with open(self.state_file) as f:
            data = json.load(f)
        for v in data.get("videos", []):
            try:
                state = VideoState(**v)
                self._sandbox(state.file_path)
                datetime.fromisoformat(state.downloaded_at)
            except (ValueError, TypeError) as exc:
                logger.warning(f"Dropping invalid state entry: {v!r} ({exc})")
                continue
            self._videos[state.video_id] = state

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"videos": [asdict(v) for v in self._videos.values()]}
        fd, temp_path = tempfile.mkstemp(
            dir=self.state_file.parent, prefix=self.state_file.name + ".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(temp_path, self.state_file)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def is_downloaded(self, video_id: str) -> bool:
        with self._lock:
            return video_id in self._videos and self._videos[video_id].status == "downloaded"

    def add(self, video: VideoState) -> None:
        self._sandbox(video.file_path)
        with self._lock:
            self._videos[video.video_id] = video
            self._save()

    def mark_failed(self, video_id: str) -> None:
        with self._lock:
            if video_id in self._videos:
                self._videos[video_id].status = "failed"
                self._save()

    def remove(self, video_id: str) -> Optional[VideoState]:
        with self._lock:
            video = self._videos.pop(video_id, None)
            if video:
                self._save()
            return video

    def get(self, video_id: str) -> Optional[VideoState]:
        with self._lock:
            return self._videos.get(video_id)

    def get_all(self) -> list[VideoState]:
        with self._lock:
            return list(self._videos.values())

    def get_downloaded(self) -> list[VideoState]:
        with self._lock:
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
        return min(downloaded, key=lambda v: datetime.fromisoformat(v.downloaded_at))

    def remove_video(self, video: VideoState) -> bool:
        """Sandbox, unlink, mark removed, and persist state.

        If the path escapes the output directory, the file is never touched.
        The entry is still marked removed so cleanup does not loop forever.
        """
        try:
            self._sandbox(video.file_path)
        except ValueError as exc:
            logger.warning(f"Skipping deletion of escaped path: {exc}")
            video.status = "removed"
            with self._lock:
                self._videos[video.video_id] = video
                self._save()
            return False
        path = Path(video.file_path)
        if path.exists():
            try:
                path.unlink()
            except OSError as exc:
                logger.warning(f"Failed to delete {path}: {exc}")
                return False
        video.status = "removed"
        with self._lock:
            self._videos[video.video_id] = video
            self._save()
        return True

    def cleanup_old(self, max_age_days: int) -> list[VideoState]:
        removed = []
        now = datetime.now(timezone.utc)
        for v in self.get_downloaded():
            downloaded_at = datetime.fromisoformat(v.downloaded_at)
            age_days = (now - downloaded_at).days
            if age_days > max_age_days:
                if self.remove_video(v):
                    removed.append(v)
        return removed
