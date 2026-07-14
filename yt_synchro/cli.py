"""CLI entry point for yt-synchro."""

import logging
import sys
import time
from pathlib import Path

import click
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from .cleanup import cleanup_by_count, cleanup_by_storage, cleanup_old_videos
from .config import CONFIG_FILE, Config, ensure_config, load_config
from .downloader import download_playlist, ensure_ytdlp
from .logger import setup_logging
from .state import StateManager

console = Console(markup=True)
logger = logging.getLogger(__name__)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.pass_context
def main(ctx, verbose):
    """yt-synchro - YouTube playlist sync with storage management."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)
    ensure_ytdlp()


@main.command()
@click.option("--playlist", "-p", help="Playlist URL")
@click.option("--max-storage", type=float, help="Max storage in GB")
@click.option("--max-videos", type=int, help="Max videos to keep")
@click.option("--parallel", type=int, help="Max parallel downloads")
@click.option("--quality", help="Video quality (1080p, 720p, etc.)")
@click.option("--output-dir", "-o", type=click.Path(), help="Output directory")
@click.pass_context
def run(ctx, playlist, max_storage, max_videos, parallel, quality, output_dir):
    """Download until one of the max limits is reached, then exit."""
    overrides = _build_overrides(
        playlist, max_storage, max_videos, parallel, quality, output_dir
    )
    config = load_config(overrides)

    if not config.playlist_url:
        console.print(
            "[red]Error: No playlist URL specified. Use --playlist or set in config.[/red]"
        )
        sys.exit(1)

    state = StateManager()
    output_dir_path = Path(config.output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold magenta]yt-synchro[/bold magenta] - Downloading playlist...")
    console.print(f"  Playlist: {config.playlist_url}")
    console.print(f"  Output: {config.output_dir}")
    console.print(
        f"  Limits: {config.max_storage_gb}GB / {config.max_videos} videos / {config.parallel} parallel"
    )
    console.print()

    cleanup_old_videos(state, config)
    cleanup_by_storage(state, config)
    cleanup_by_count(state, config)

    total_downloaded = 0
    total_failed = 0

    while True:
        count = state.get_count()
        size_bytes = state.get_total_size()
        size_gb = size_bytes / (1024 * 1024 * 1024)

        if count >= config.max_videos:
            console.print(
                f"\n[red]Limit reached: {count} videos (max {config.max_videos})[/red]"
            )
            break

        if size_gb >= config.max_storage_gb:
            console.print(
                f"\n[red]Limit reached: {size_gb:.2f}GB (max {config.max_storage_gb}GB)[/red]"
            )
            break

        available_slots = config.max_videos - count
        # available_storage_gb = config.max_storage_gb - size_gb

        console.print(
            f"\n[magenta]--- Batch: {count}/{config.max_videos} videos, {size_gb:.2f}/{config.max_storage_gb}GB ---[/magenta]"
        )

        result = download_playlist(config, state, max_downloads=available_slots)

        total_downloaded += result["downloaded"]
        total_failed += result["failed"]

        if result["downloaded"] == 0:
            console.print("[dim]No new videos available to download.[/dim]")
            break

    console.print()
    console.print("[bold white]Run complete:[/bold white]")
    console.print(f"  Downloaded: {total_downloaded}")
    console.print(f"  Failed: {total_failed}")
    console.print()

    _print_status(state, config)


@main.command()
@click.option("--playlist", "-p", help="Playlist URL")
@click.option("--max-storage", type=float, help="Max storage in GB")
@click.option("--max-videos", type=int, help="Max videos to keep")
@click.option("--parallel", type=int, help="Max parallel downloads")
@click.option("--quality", help="Video quality")
@click.option("--output-dir", "-o", type=click.Path(), help="Output directory")
@click.pass_context
def daemon(ctx, playlist, max_storage, max_videos, parallel, quality, output_dir):
    """Continuous: check playlist periodically, auto-fill."""
    overrides = _build_overrides(
        playlist, max_storage, max_videos, parallel, quality, output_dir
    )
    config = load_config(overrides)

    if not config.playlist_url:
        console.print(
            "[red]Error: No playlist URL specified. Use --playlist or set in config.[/red]"
        )
        sys.exit(1)

    state = StateManager()
    output_dir_path = Path(config.output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    console.print(
        "[bold magenta]yt-synchro daemon[/bold magenta] - Starting continuous sync..."
    )
    console.print(f"  Playlist: {config.playlist_url}")
    console.print(f"  Check interval: {config.daemon_interval_minutes} minutes")
    console.print("  Press Ctrl+C to stop")
    console.print()

    try:
        while True:
            console.print(
                f"[dim]Checking playlist at {time.strftime('%Y-%m-%d %H:%M:%S')}...[/dim]"
            )

            cleanup_old_videos(state, config)
            cleanup_by_storage(state, config)
            cleanup_by_count(state, config)

            # videos = get_playlist_videos(config.playlist_url)
            available_slots = config.max_videos - state.get_count()
            available_storage = (
                config.max_storage_gb * 1024 * 1024 * 1024
            ) - state.get_total_size()

            if available_slots > 0 and available_storage > 0:
                max_downloads = min(available_slots, config.parallel)
                result = download_playlist(config, state, max_downloads)

                if result["downloaded"] > 0:
                    console.print(
                        f"[white]Downloaded {result['downloaded']} new videos[/white]"
                    )
                if result["failed"] > 0:
                    console.print(f"[red]Failed: {result['failed']}[/red]")

            _print_status(state, config)

            console.print(
                f"[dim]Next check in {config.daemon_interval_minutes} minutes...[/dim]"
            )
            time.sleep(config.daemon_interval_minutes * 60)

    except KeyboardInterrupt:
        console.print("\n[magenta]Daemon stopped.[/magenta]")


@main.command()
@click.pass_context
def status(ctx):
    """Show current state: downloads, storage, next cleanup."""
    config = load_config()
    state = StateManager()
    _print_status(state, config)


@main.command()
@click.pass_context
def config_show(ctx):
    """Show current config."""
    config = load_config()
    console.print(
        Panel.fit(
            f"[bold]Current Configuration[/bold]\n\n"
            f"Playlist URL: {config.playlist_url or '(not set)'}\n"
            f"Output Dir: {config.output_dir}\n"
            f"Max Storage: {config.max_storage_gb} GB\n"
            f"Max Videos: {config.max_videos}\n"
            f"Parallel: {config.parallel}\n"
            f"Quality: {config.quality}\n"
            f"Daemon Interval: {config.daemon_interval_minutes} min\n"
            f"Video Max Age: {config.video_max_age_days} days\n\n"
            f"[dim]Config file: {CONFIG_FILE}[/dim]",
            title="[magenta]Config[/magenta]",
        )
    )


@main.command()
@click.pass_context
def config_edit(ctx):
    """Interactive config editor."""
    if not CONFIG_FILE.exists():
        ensure_config()

    config = load_config()
    console.print()
    console.print(
        Panel(
            "[bold magenta]yt-synchro Config Editor[/bold magenta]",
            subtitle="Press Enter to keep current value",
        )
    )
    console.print()

    fields = [
        ("playlist_url", "Playlist URL", str, config.playlist_url or "(not set)"),
        ("output_dir", "Output Directory", str, config.output_dir),
        ("max_storage_gb", "Max Storage (GB)", float, config.max_storage_gb),
        ("max_videos", "Max Videos", int, config.max_videos),
        ("parallel", "Parallel Downloads", int, config.parallel),
        ("quality", "Quality (best/1080p/720p/480p)", str, config.quality),
        (
            "daemon_interval_minutes",
            "Daemon Interval (min)",
            int,
            config.daemon_interval_minutes,
        ),
        ("video_max_age_days", "Video Max Age (days)", int, config.video_max_age_days),
    ]

    for field_name, label, field_type, current_value in fields:
        current_str = str(current_value)
        prompt = f"\033[35m  {label}\033[0m  \033[2m({current_str})\033[0m: "
        sys.stdout.write(prompt)
        sys.stdout.flush()
        new_value = input()

        if new_value.strip() == "":
            continue

        try:
            if field_type == float:
                setattr(config, field_name, float(new_value))
            elif field_type == int:
                setattr(config, field_name, int(new_value))
            else:
                setattr(config, field_name, new_value)
        except (ValueError, TypeError):
            console.print("  [red]Invalid value, keeping current.[/red]")

    config.save(CONFIG_FILE)
    console.print()
    console.print("[white]  Config saved![/white]")
    console.print(f"  [dim]{CONFIG_FILE}[/dim]")
    console.print()


@main.command()
@click.pass_context
def list_videos(ctx):
    """List all tracked videos."""
    state = StateManager()
    videos = state.get_all()

    if not videos:
        console.print("[magenta]No videos tracked yet.[/magenta]")
        return

    table = Table(title="Tracked Videos")
    table.add_column("ID", style="magenta")
    table.add_column("Title", style="white")
    table.add_column("Status", style="white")
    table.add_column("Downloaded", style="dim")

    for v in videos:
        status_style = {
            "downloaded": "[white]Downloaded[/white]",
            "failed": "[red]Failed[/red]",
            "removed": "[magenta]Removed[/magenta]",
        }.get(v.status, v.status)

        table.add_row(
            v.video_id,
            v.title[:50] + "..." if len(v.title) > 50 else v.title,
            status_style,
            v.downloaded_at[:10],
        )

    console.print(table)


@main.command()
@click.argument("video_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_context
def remove(ctx, video_id, force):
    """Manually remove a video."""
    state = StateManager()
    video = state.get(video_id)

    if not video:
        console.print(f"[red]Video not found: {video_id}[/red]")
        sys.exit(1)

    if not force:
        console.print(f"Remove: [magenta]{video.title}[/magenta] ({video_id})?")
        if not click.confirm("Continue?"):
            console.print("[magenta]Cancelled.[/magenta]")
            return

    path = Path(video.file_path)
    if path.exists():
        path.unlink()

    state.remove(video_id)
    console.print(f"[white]Removed: {video.title}[/white]")


def _build_overrides(playlist, max_storage, max_videos, parallel, quality, output_dir):
    overrides = {}
    if playlist:
        overrides["playlist_url"] = playlist
    if max_storage is not None:
        overrides["max_storage_gb"] = max_storage
    if max_videos is not None:
        overrides["max_videos"] = max_videos
    if parallel is not None:
        overrides["parallel"] = parallel
    if quality:
        overrides["quality"] = quality
    if output_dir:
        overrides["output_dir"] = output_dir
    return overrides


def _print_status(state: StateManager, config: Config):
    count = state.get_count()
    size_bytes = state.get_total_size()
    size_gb = size_bytes / (1024 * 1024 * 1024)

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="magenta")
    table.add_column("Value", style="white")

    table.add_row("Videos", f"{count} / {config.max_videos}")
    table.add_row("Storage", f"{size_gb:.2f} GB / {config.max_storage_gb} GB")
    table.add_row("Parallel", f"{config.parallel}")
    table.add_row("Output", config.output_dir)

    console.print(Panel(table, title="[magenta]Status[/magenta]"))


if __name__ == "__main__":
    main()
