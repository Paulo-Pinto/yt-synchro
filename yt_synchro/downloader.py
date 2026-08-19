"""YouTube downloader module for yt-synchro."""

import logging
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TransferSpeedColumn,
)

from .config import Config
from .state import StateManager, VideoState

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

logger = logging.getLogger(__name__)
console = Console(markup=True)

_MAX_RETRIES = 3


_YOUTUBE_HOSTS = {"youtube.com", "youtu.be", "youtube-nocookie.com"}


def _require_ytdlp() -> None:
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is not installed. Install it with: pip install yt-dlp")


def _validate_playlist_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Playlist URL must use HTTPS, got {parsed.scheme!r}")
    # Use hostname (not netloc) so ports/userinfo are ignored, and strip the
    # literal "www." prefix. str.lstrip("www.") would strip *characters*,
    # allowing attacker-controlled lookalike domains such as "wwyoutube.com".
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host not in _YOUTUBE_HOSTS and not host.endswith(".youtube.com"):
        raise ValueError(f"Playlist URL must point to YouTube, got {url!r}")


def _sandbox_path(path: Path, base_dir: Path) -> Path:
    resolved = path.expanduser().resolve()
    base_resolved = base_dir.expanduser().resolve()
    if not resolved.is_relative_to(base_resolved):
        raise ValueError(f"Path escapes output directory: {resolved}")
    return resolved


def _embed_author_metadata(
    file_path: Path, author: str, title: str = "", duration: Optional[float] = None
) -> None:
    """Embed author, title, and duration metadata into the video file using ffmpeg."""
    if not file_path.exists():
        return
    if not author and not title and duration is None:
        return
    temp_path = file_path.with_suffix(".tmp" + file_path.suffix)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(file_path),
        "-c",
        "copy",
    ]
    if author:
        cmd.extend(["-metadata", f"artist={author}"])
        cmd.extend(["-metadata", f"author={author}"])
    if title:
        cmd.extend(["-metadata", f"title={title}"])
    if duration is not None:
        # duration in seconds as string for ffmpeg metadata
        cmd.extend(["-metadata", f"duration={duration}"])
    cmd.append(str(temp_path))
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        temp_path.replace(file_path)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        logger.warning(f"Failed to embed metadata into {file_path}: {stderr}")
        if temp_path.exists():
            temp_path.unlink()
    except (FileNotFoundError, OSError) as exc:
        logger.warning(f"Failed to embed metadata into {file_path}: {exc}")
        if temp_path.exists():
            temp_path.unlink()


def _sanitize_filename(title: str) -> str:
    """Lowercase, strip special chars, replace spaces with underscores."""
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "untitled"


def get_quality_format(quality: str) -> str:
    # Prefer m3u8 (HLS) streams to avoid YouTube's DASH 403 blocks.
    # Format: best HLS at quality / best DASH separate / best combined fallback
    quality_map = {
        "best": "best[protocol=m3u8_native]/bestvideo+bestaudio/best",
        "2160p": "best[protocol=m3u8_native][height<=2160]/bestvideo[height<=2160]+bestaudio/best[height<=2160]",
        "1440p": "best[protocol=m3u8_native][height<=1440]/bestvideo[height<=1440]+bestaudio/best[height<=1440]",
        "1080p": "best[protocol=m3u8_native][height<=1080]/bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p": "best[protocol=m3u8_native][height<=720]/bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p": "best[protocol=m3u8_native][height<=480]/bestvideo[height<=480]+bestaudio/best[height<=480]",
        "360p": "best[protocol=m3u8_native][height<=360]/bestvideo[height<=360]+bestaudio/best[height<=360]",
    }
    return quality_map.get(quality, quality_map["1080p"])


def _finish_progress_failed(
    progress: Optional[Progress], task_id: Optional[str], label: str
) -> None:
    """Mark a progress task as failed: red X, bar at 0%."""
    if progress is None or task_id is None:
        return
    progress.update(
        task_id,
        description=f"[red]✗[/red] {label}",
        completed=0,
        total=1,
        refresh=False,
    )


def download_video(
    video_id: str,
    url: str,
    output_dir: Path,
    quality: str,
    progress: Optional[Progress] = None,
    task_id: Optional[str] = None,
    uploader: str = "",
    title: str = "",
    duration: Optional[float] = None,
) -> dict:
    _require_ytdlp()
    short_label = f"{uploader} - {title}" if uploader else title or video_id

    def yt_progress_hook(d):
        if progress is None or task_id is None:
            return
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed")
            progress.update(task_id, completed=downloaded, total=total, refresh=False)
            if speed:
                progress.update(task_id, speed=speed, refresh=False)
        elif d["status"] == "finished":
            progress.update(task_id, description=f"[white]✓[/white] {short_label}", refresh=False)
        elif d["status"] == "error":
            _finish_progress_failed(progress, task_id, short_label)

    ydl_opts = {
        "format": get_quality_format(quality),
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "retries": _MAX_RETRIES,
        "progress_hooks": [yt_progress_hook],
        "postprocessors": [
            {"key": "FFmpegMetadata", "add_metadata": True},
        ],
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", video_id)
            ext = info.get("ext", "mp4")
            if duration is None:
                duration = info.get("duration")
            downloaded_path = output_dir / f"{video_id}.{ext}"
            safe_name = _sanitize_filename(title)
            final_path = output_dir / f"{safe_name}.{ext}"
            _sandbox_path(final_path, output_dir)

            if downloaded_path.exists():
                counter = 1
                original_final_path = final_path
                while final_path.exists():
                    final_path = original_final_path.with_suffix(
                        f".{counter}{original_final_path.suffix}"
                    )
                    counter += 1
                downloaded_path.rename(final_path)

            _embed_author_metadata(
                final_path,
                uploader or info.get("uploader", "") or info.get("channel", ""),
                title,
                duration,
            )

            video_state = VideoState.create(
                video_id=video_id,
                title=title,
                file_path=str(final_path),
                duration=duration,
            )

            if progress is not None and task_id is not None:
                progress.update(
                    task_id, description=f"[white]✓[/white] {short_label}", refresh=False
                )

            return {
                "video_id": video_id,
                "title": title,
                "status": "downloaded",
                "file_path": str(final_path),
                "video_state": video_state,
            }
    except (yt_dlp.utils.DownloadError, OSError, ValueError) as e:
        logger.error(f"Failed to download {video_id}: {e}")
        _finish_progress_failed(progress, task_id, short_label)
        return {
            "video_id": video_id,
            "title": title or "",
            "status": "failed",
            "error": str(e),
        }


def get_playlist_videos(playlist_url: str) -> list[dict]:
    _require_ytdlp()
    _validate_playlist_url(playlist_url)
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            entries = info.get("entries", []) if info else []
            return [
                {
                    "video_id": entry.get("id"),
                    "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                    "title": entry.get("title", ""),
                    "uploader": entry.get("uploader", "") or entry.get("channel", ""),
                    "duration": entry.get("duration"),
                }
                for entry in entries
                if entry and entry.get("id")
            ]
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Failed to fetch playlist: {e}")
        return []


def download_playlist(
    config: Config,
    state: StateManager,
    max_downloads: Optional[int] = None,
) -> dict:
    _require_ytdlp()
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    videos = get_playlist_videos(config.playlist_url)
    if not videos:
        return {"downloaded": 0, "failed": 0, "skipped": 0}

    to_download = [v for v in videos if not state.is_downloaded(v["video_id"])]

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
            label = (
                f"{video.get('uploader', '')} - {video.get('title', '')}"
                if video.get("uploader")
                else video.get("title", video["video_id"])
            )
            task_id = progress.add_task(label, total=None)
            return download_video(
                video_id=video["video_id"],
                url=video["url"],
                output_dir=output_dir,
                quality=config.quality,
                progress=progress,
                task_id=task_id,
                uploader=video.get("uploader", ""),
                title=video.get("title", ""),
                duration=video.get("duration"),
            )

        with ThreadPoolExecutor(max_workers=config.parallel) as executor:
            futures = {executor.submit(download_one, v): v for v in to_download}
            for future in as_completed(futures):
                result = future.result()
                if result is None:
                    skipped += 1
                elif result["status"] == "downloaded":
                    state.add(result["video_state"])
                    downloaded += 1
                else:
                    failed += 1

    return {
        "downloaded": downloaded,
        "failed": failed,
        "skipped": skipped,
    }
