"""Regression tests for yt_synchro.downloader."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import yt_synchro.downloader as downloader_module
from yt_synchro.config import Config
from yt_synchro.downloader import download_video, get_playlist_videos
from yt_synchro.state import StateManager, VideoState


def make_state(tmp_path):
    state_file = tmp_path / "state.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir(exist_ok=True)
    return StateManager(state_file=state_file, output_dir=output_dir)


def test_ensure_ytdlp_removed():
    assert not hasattr(downloader_module, "ensure_ytdlp")


def test_get_playlist_videos_rejects_non_youtube_url():
    with pytest.raises(ValueError):
        get_playlist_videos("https://example.com/playlist")

    with pytest.raises(ValueError):
        get_playlist_videos("file:///etc/passwd")


def test_get_playlist_videos_rejects_lookalike_domains():
    # These domains are attacker-registerable; the old lstrip("www.") validator
    # incorrectly accepted them as YouTube.
    for malicious in (
        "https://wwyoutube.com/playlist?list=PLfoo",
        "https://wwwyoutube.com/playlist?list=PLfoo",
        "https://wwwyoutu.be/playlist?list=PLfoo",
        "https://youtube.com.evil.com/playlist?list=PLfoo",
    ):
        with pytest.raises(ValueError):
            get_playlist_videos(malicious)


def test_get_playlist_videos_accepts_youtube_url():
    with patch.object(downloader_module, "yt_dlp") as mock_ytdlp:
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            "entries": [
                {"id": "abc123def45", "title": "t", "uploader": "u"},
            ]
        }
        mock_ytdlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl

        result = get_playlist_videos("https://www.youtube.com/playlist?list=PLfoo")
        assert len(result) == 1
        assert result[0]["video_id"] == "abc123def45"


def test_download_video_sandboxes_malicious_id(tmp_path):
    state = make_state(tmp_path)
    output_dir = Path(state._output_dir)

    with patch.object(downloader_module, "yt_dlp") as mock_ytdlp:
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            "title": "safe title",
            "ext": "mp4",
        }
        mock_ytdlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl

        # The video_id looks like path traversal; the download must not
        # produce a tracked file that escapes output_dir.
        result = download_video(
            video_id="../etc/passwd",
            url="https://www.youtube.com/watch?v=abc123def45",
            output_dir=output_dir,
            quality="1080p",
        )

        # Whether it failed-fast or produced a path, nothing may escape the sandbox.
        if result["status"] == "downloaded":
            resolved = Path(result["file_path"]).resolve()
            assert resolved.is_relative_to(output_dir.resolve())


def test_download_video_catches_ytdlp_error(tmp_path):
    state = make_state(tmp_path)
    output_dir = Path(state._output_dir)

    with patch.object(downloader_module, "yt_dlp") as mock_ytdlp:
        mock_ytdlp.utils.DownloadError = Exception
        mock_ytdlp.YoutubeDL.return_value.__enter__ = MagicMock(
            side_effect=Exception("network")
        )

        result = download_video(
            video_id="abc123def45",
            url="https://www.youtube.com/watch?v=abc123def45",
            output_dir=output_dir,
            quality="1080p",
        )

        assert result["status"] == "failed"


def test_download_playlist_batches_state_updates(tmp_path):
    state = make_state(tmp_path)
    output_dir = Path(state._output_dir)
    config = Config(
        playlist_url="https://www.youtube.com/playlist?list=PLfoo",
        output_dir=str(output_dir),
        parallel=2,
    )

    with (
        patch.object(downloader_module, "get_playlist_videos") as mock_get,
        patch.object(downloader_module, "download_video") as mock_download,
    ):
        mock_get.return_value = [
            {"video_id": "v1", "url": "u1", "title": "t1", "uploader": ""},
            {"video_id": "v2", "url": "u2", "title": "t2", "uploader": ""},
        ]

        def fake_download(video_id, url, **kwargs):
            file_path = str(output_dir / f"{video_id}.mp4")
            return {
                "video_id": video_id,
                "title": video_id,
                "status": "downloaded",
                "file_path": file_path,
                "video_state": VideoState.create(
                    video_id=video_id, title=video_id, file_path=file_path
                ),
            }

        mock_download.side_effect = fake_download

        result = downloader_module.download_playlist(config, state, max_downloads=2)
        assert result["downloaded"] == 2
        assert state.get("v1") is not None
        assert state.get("v2") is not None
