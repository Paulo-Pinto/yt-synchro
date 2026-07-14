# yt-synchro

## Project Overview

Python CLI app that downloads YouTube playlist videos to a local folder, managing storage limits and auto-cleaning old content.

## Architecture

```
CLI (click) → Downloader (yt-dlp) → File System
     ↓              ↓                    ↓
  Config (TOML)  State (JSON)        Logs (Rotating)
```

### Modules

| Module | Purpose |
|--------|---------|
| `cli.py` | Click CLI with run, daemon, status, config, list, remove commands |
| `downloader.py` | yt-dlp wrapper with parallel download support |
| `config.py` | TOML config file management with defaults |
| `state.py` | JSON state tracking for downloaded videos |
| `cleanup.py` | Age-based and limit-based video deletion |
| `logger.py` | Rotating file logging (10MB / 30 days) |

## CLI Commands

```bash
# One-shot download
yt-synchro run --playlist URL --max-storage 50GB --max-videos 20 --parallel 3

# Continuous daemon
yt-synchro daemon --playlist URL [same flags]

# Status
yt-synchro status

# Config
yt-synchro config show
yt-synchro config edit

# List videos
yt-synchro list

# Remove video
yt-synchro remove <video-id>
```

## Configuration

- **Location:** `~/.config/yt-synchro/config.toml`
- **Auto-created** with defaults on first run
- **CLI flags override** config values per-run

### Defaults

```toml
playlist_url = ""
output_dir = "~/Downloads/yt-synchro"
max_storage_gb = 50.0
max_videos = 20
parallel = 3
quality = "1080p"
daemon_interval_minutes = 60
video_max_age_days = 14
```

## State Tracking

- **Location:** `~/.config/yt-synchro/state.json`
- **Tracks:** video ID, title, file path, download date, status

## Logging

- **Location:** `~/.config/yt-synchro/yt-synchro.log`
- **Rotation:** 10MB or 30 days

## Dependencies

- `yt-dlp` - YouTube downloading
- `rich` - Pretty terminal output
- `click` - CLI framework
- stdlib `tomllib` - Config parsing (Python 3.11+)

## Limits

All limits active simultaneously, first-hit-wins:

- `--max-storage` (e.g., 50GB) - disk space cap
- `--max-videos` (e.g., 20) - max videos on disk
- `--parallel` (e.g., 3) - max concurrent downloads

## Behavior

- **Failed downloads:** log error, skip, continue
- **Missing yt-dlp:** auto-install via pip
- **Deletion:** eager cleanup every cycle (2+ week old videos)
- **Config missing:** auto-create with defaults

## Development

```bash
# Install dependencies
pip install -e .

# Run
yt-synchro --help
python -m yt_synchro --help
```
