"""Orchestration layer for yt-synchro run and daemon loops."""

import sys
import time
from pathlib import Path

from rich.console import Console

from .cleanup import cleanup_by_count, cleanup_by_storage, cleanup_old_videos
from .config import Config
from .downloader import download_playlist
from .state import StateManager

console = Console(markup=True)


def _build_overrides(playlist, max_storage, max_videos, parallel, quality, output_dir):
    overrides = {}
    if playlist is not None:
        overrides["playlist_url"] = playlist
    if max_storage is not None:
        overrides["max_storage_gb"] = max_storage
    if max_videos is not None:
        overrides["max_videos"] = max_videos
    if parallel is not None:
        overrides["parallel"] = parallel
    if quality is not None:
        overrides["quality"] = quality
    if output_dir is not None:
        overrides["output_dir"] = output_dir
    return overrides


def _ensure_playlist(config: Config) -> None:
    if not config.playlist_url:
        console.print(
            "[red]Error: No playlist URL specified. Use --playlist or set in config.[/red]"
        )
        sys.exit(1)


def _print_run_header(config: Config) -> None:
    console.print("[bold magenta]yt-synchro[/bold magenta] - Downloading playlist...")
    console.print(f"  Playlist: {config.playlist_url}")
    console.print(f"  Output: {config.output_dir}")
    console.print(
        f"  Limits: {config.max_storage_gb}GB / {config.max_videos} videos / "
        f"{config.parallel} parallel"
    )
    console.print()


def do_run(config: Config) -> None:
    """One-shot download until a limit is reached."""
    _ensure_playlist(config)

    output_dir_path = Path(config.output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    state = StateManager(output_dir=output_dir_path)

    _print_run_header(config)

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
                f"\n[red]Limit reached: {size_gb:.2f}GB "
                f"(max {config.max_storage_gb}GB)[/red]"
            )
            break

        available_slots = config.max_videos - count

        console.print(
            f"\n[magenta]--- Batch: {count}/{config.max_videos} videos, "
            f"{size_gb:.2f}/{config.max_storage_gb}GB ---[/magenta]"
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

    from .display import print_status

    print_status(state, config)


def do_daemon(config: Config) -> None:
    """Continuous playlist sync."""
    _ensure_playlist(config)

    output_dir_path = Path(config.output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    state = StateManager(output_dir=output_dir_path)

    console.print(
        "[bold magenta]yt-synchro daemon[/bold magenta] - Starting continuous sync..."
    )
    console.print(f"  Playlist: {config.playlist_url}")
    console.print(f"  Check interval: {config.daemon_interval_minutes} minutes")
    console.print("  Press Ctrl+C to stop")
    console.print()

    from .display import print_status

    try:
        while True:
            console.print(
                f"[dim]Checking playlist at {time.strftime('%Y-%m-%d %H:%M:%S')}...[/dim]"
            )

            cleanup_old_videos(state, config)
            cleanup_by_storage(state, config)
            cleanup_by_count(state, config)

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

            print_status(state, config)

            console.print(
                f"[dim]Next check in {config.daemon_interval_minutes} minutes...[/dim]"
            )
            time.sleep(config.daemon_interval_minutes * 60)

    except KeyboardInterrupt:
        console.print("\n[magenta]Daemon stopped.[/magenta]")
