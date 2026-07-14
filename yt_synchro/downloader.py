"""YouTube downloader module for yt-synchro."""

import sys
import logging
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TransferSpeedColumn,
)

import re

from .state import StateManager, VideoState
from .config import Config

logger = logging.getLogger(__name__)
console = Console(markup=True)


_yt_dlp_installed = yt_dlp is not None


def ensure_ytdlp() -> bool:
    global _yt_dlp_installed, yt_dlp
    if _yt_dlp_installed:
        return True
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
        import importlib
        yt_dlp = importlib.import_module("yt_dlp")
        _yt_dlp_installed = True
        return True
    except Exception as e:
        logger.error(f"Failed to install yt-dlp: {e}")
        return False


def _embed_author_metadata(file_path: Path, author: str) -> None:
    """Embed author metadata into the video file using ffmpeg."""
    if not author or not file_path.exists():
        return
    temp_path = file_path.with_suffix(".tmp" + file_path.suffix)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(file_path),
                "-c", "copy",
                "-metadata", f"artist={author}",
                "-metadata", f"author={author}",
                str(temp_path),
            ],
            check=True,
            capture_output=True,
        )
        temp_path.replace(file_path)
    except Exception:
        logger.warning(f"Failed to embed metadata into {file_path}")
        if temp_path.exists():
            temp_path.unlink()


def _sanitize_filename(title: str) -> str:
    """Lowercase, strip special chars, replace spaces with underscores."""
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "untitled"


def get_quality_format(quality: str) -> str:
    quality_map = {
        "best": "bestvideo+bestaudio/best",
        "2160p": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
        "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]",
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    }
    return quality_map.get(quality, quality_map["1080p"])


def download_video(
    video_id: str,
    url: str,
    output_dir: Path,
    quality: str,
    state: StateManager,
    progress: Optional[Progress] = None,
    task_id: Optional[str] = None,
    uploader: str = "",
    title: str = "",
) -> Optional[dict]:
    if state.is_downloaded(video_id):
        logger.debug(f"Skipping already downloaded: {video_id}")
        return None

    short_label = f"{uploader} - {title}" if uploader else title or video_id

    def yt_progress_hook(d):
        if progress is None or task_id is None:
            return
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed")
            progress.update(task_id, completed=downloaded, total=total)
            if speed:
                progress.update(task_id, speed=speed)
        elif d["status"] == "finished":
            progress.update(task_id, description=f"[white]✓[/white] {short_label}")

    ydl_opts = {
        "format": get_quality_format(quality),
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "progress_hooks": [yt_progress_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", video_id)
            ext = info.get("ext", "mp4")
            downloaded_path = output_dir / f"{video_id}.{ext}"
            safe_name = _sanitize_filename(title)
            final_path = output_dir / f"{safe_name}.{ext}"
            if downloaded_path.exists():
                downloaded_path.rename(final_path)

            _embed_author_metadata(final_path, uploader or info.get("uploader", "") or info.get("channel", ""))

            video_state = VideoState.create(
                video_id=video_id,
                title=title,
                file_path=str(final_path),
            )
            state.add(video_state)

            if progress is not None and task_id is not None:
                progress.update(task_id, description=f"[white]✓[/white] {short_label}")

            return {
                "video_id": video_id,
                "title": title,
                "status": "downloaded",
                "file_path": str(final_path),
            }
    except Exception as e:
        logger.error(f"Failed to download {video_id}: {e}")
        if progress is not None and task_id is not None:
            progress.update(task_id, description=f"[red]✗[/red] {short_label}")
        return {
            "video_id": video_id,
            "title": "",
            "status": "failed",
            "error": str(e),
        }


def get_playlist_videos(playlist_url: str) -> list[dict]:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            entries = info.get("entries", [])
            return [
                {
                    "video_id": entry.get("id"),
                    "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                    "title": entry.get("title", ""),
                    "uploader": entry.get("uploader", "") or entry.get("channel", ""),
                }
                for entry in entries
                if entry.get("id")
            ]
    except Exception as e:
        logger.error(f"Failed to fetch playlist: {e}")
        return []


def download_playlist(
    config: Config,
    state: StateManager,
    max_downloads: Optional[int] = None,
) -> dict:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    videos = get_playlist_videos(config.playlist_url)
    if not videos:
        return {"downloaded": 0, "failed": 0, "skipped": 0}

    to_download = [
        v for v in videos
        if not state.is_downloaded(v["video_id"])
    ]

    if max_downloads:
        to_download = to_download[:max_downloads]

    if not to_download:
        return {"downloaded": 0, "failed": 0, "skipped": len(videos)}

    downloaded = 0
    failed = 0
    skipped = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold magenta]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TransferSpeedColumn(),
        console=console,
    ) as progress:
        def download_one(video):
            label = f"{video.get('uploader', '')} - {video.get('title', '')}" if video.get("uploader") else video.get("title", video["video_id"])
            task_id = progress.add_task(label, total=None)
            return download_video(
                video_id=video["video_id"],
                url=video["url"],
                output_dir=output_dir,
                quality=config.quality,
                state=state,
                progress=progress,
                task_id=task_id,
                uploader=video.get("uploader", ""),
                title=video.get("title", ""),
            )

        with ThreadPoolExecutor(max_workers=config.parallel) as executor:
            futures = {executor.submit(download_one, v): v for v in to_download}
            for future in as_completed(futures):
                result = future.result()
                if result is None:
                    skipped += 1
                elif result["status"] == "downloaded":
                    downloaded += 1
                else:
                    failed += 1

    return {
        "downloaded": downloaded,
        "failed": failed,
        "skipped": skipped,
    }
