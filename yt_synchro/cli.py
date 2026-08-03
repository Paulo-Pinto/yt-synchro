"""CLI entry point for yt-synchro."""

import logging
import shutil
import sys
from pathlib import Path

import click

from .config import CONFIG_FILE, ensure_config, load_config
from .display import (
    console,
    edit_config,
    list_videos,
    print_status,
    prompt_remove,
    show_config,
)
from .logger import setup_logging
from .runner import _build_overrides, do_daemon, do_run
from .state import StateManager

logger = logging.getLogger(__name__)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.pass_context
def main(ctx, verbose):
    """yt-synchro - YouTube playlist sync with storage management."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)
    if shutil.which("ffmpeg") is None:
        logger.warning(
            "ffmpeg is not installed or not on PATH. "
            "Author metadata embedding will be skipped."
        )


@main.command()
@click.option("--playlist", "-p", help="Playlist URL")
@click.option("--max-storage", type=float, help="Max storage in GB")
@click.option("--max-videos", type=int, help="Max videos to keep")
@click.option("--parallel", type=int, help="Max parallel downloads")
@click.option("--quality", help="Video quality (1080p, 720p, etc.)")
@click.option("--output-dir", "-o", type=click.Path(), help="Output directory")
def run(playlist, max_storage, max_videos, parallel, quality, output_dir):
    """Download until one of the max limits is reached, then exit."""
    overrides = _build_overrides(
        playlist, max_storage, max_videos, parallel, quality, output_dir
    )
    config = load_config(overrides)
    do_run(config)


@main.command()
@click.option("--playlist", "-p", help="Playlist URL")
@click.option("--max-storage", type=float, help="Max storage in GB")
@click.option("--max-videos", type=int, help="Max videos to keep")
@click.option("--parallel", type=int, help="Max parallel downloads")
@click.option("--quality", help="Video quality")
@click.option("--output-dir", "-o", type=click.Path(), help="Output directory")
def daemon(playlist, max_storage, max_videos, parallel, quality, output_dir):
    """Continuous: check playlist periodically, auto-fill."""
    overrides = _build_overrides(
        playlist, max_storage, max_videos, parallel, quality, output_dir
    )
    config = load_config(overrides)
    do_daemon(config)


@main.command()
def status():
    """Show current state: downloads, storage, next cleanup."""
    config = load_config()
    state = StateManager(output_dir=Path(config.output_dir))
    print_status(state, config)


@main.command("config-show")
def config_show():
    """Show current config."""
    config = load_config()
    show_config(config)


@main.command("config-edit")
def config_edit():
    """Interactive config editor."""
    if not CONFIG_FILE.exists():
        ensure_config()
    config = load_config()
    edit_config(config)


@main.command("list")
def list_videos_cmd():
    """List all tracked videos."""
    config = load_config()
    state = StateManager(output_dir=Path(config.output_dir))
    list_videos(state)


@main.command()
@click.argument("video_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def remove(video_id, force):
    """Manually remove a video."""
    config = load_config()
    state = StateManager(output_dir=Path(config.output_dir))
    video = state.get(video_id)

    if not video:
        console.print(f"[red]Video not found: {video_id}[/red]")
        sys.exit(1)

    if not force and not prompt_remove(video):
        console.print("[magenta]Cancelled.[/magenta]")
        return

    path = Path(video.file_path)
    if path.exists():
        path.unlink()

    state.remove(video_id)
    console.print(f"[white]Removed: {video.title}[/white]")


if __name__ == "__main__":
    main()
