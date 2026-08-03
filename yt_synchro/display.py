"""Terminal UI helpers for yt-synchro."""

import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import CONFIG_FILE, Config
from .state import StateManager

console = Console(markup=True)


def print_status(state: StateManager, config: Config) -> None:
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


def show_config(config: Config) -> None:
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


def edit_config(config: Config) -> None:
    """Interactive config editor."""
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

    try:
        config.validate()
    except ValueError as exc:
        console.print(f"  [red]Config invalid: {exc}[/red]")
        return

    config.save(CONFIG_FILE)
    console.print()
    console.print("[white]  Config saved![/white]")
    console.print(f"  [dim]{CONFIG_FILE}[/dim]")
    console.print()


def list_videos(state: StateManager) -> None:
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

        title = v.title[:50] + "..." if len(v.title) > 50 else v.title
        table.add_row(
            v.video_id,
            title,
            status_style,
            v.downloaded_at[:10],
        )

    console.print(table)


def prompt_remove(video) -> bool:
    console.print(f"Remove: [magenta]{video.title}[/magenta] ({video.video_id})?")
    return click.confirm("Continue?")
