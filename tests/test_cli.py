"""Regression tests for yt_synchro.cli."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from yt_synchro.cli import main


def _invoke_config_show():
    runner = CliRunner()
    config = MagicMock()
    config.playlist_url = ""
    config.output_dir = "/tmp/yt-synchro"
    config.max_storage_gb = 50.0
    config.max_videos = 20
    config.parallel = 3
    config.quality = "1080p"
    config.daemon_interval_minutes = 60
    config.video_max_age_days = 14
    with (
        patch("yt_synchro.cli.load_config", return_value=config),
        patch("yt_synchro.cli.show_config"),
    ):
        return runner.invoke(main, ["config-show"])


def test_main_warns_when_ffmpeg_missing():
    with patch("yt_synchro.cli.shutil.which", return_value=None):
        result = _invoke_config_show()

    assert result.exit_code == 0
    assert "ffmpeg is not installed" in result.output


def test_main_no_ffmpeg_warning_when_present():
    with patch("yt_synchro.cli.shutil.which", return_value="/usr/bin/ffmpeg"):
        result = _invoke_config_show()

    assert result.exit_code == 0
    assert "ffmpeg is not installed" not in result.output
