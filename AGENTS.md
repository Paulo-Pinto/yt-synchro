# yt-synchro

## Project Overview

Python CLI app that downloads YouTube playlist videos to a local folder, managing storage limits and auto-cleaning old content.

## Architecture

```
CLI (click) → Runner (orchestration) → Downloader (yt-dlp) → File System
     ↓              ↓                        ↓                    ↓
  Config (TOML)  Display (UI)            State (JSON)        Logs (Rotating)
```

### Modules

| Module | Purpose |
|--------|---------|
| `cli.py` | Click command definitions and dispatch only |
| `runner.py` | Run / daemon orchestration loops |
| `display.py` | Terminal UI helpers (tables, panels, prompts) |
| `downloader.py` | yt-dlp wrapper with parallel download support |
| `config.py` | TOML config file management with defaults and validation |
| `state.py` | JSON state tracking with path sandboxing and atomic writes |
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
yt-synchro config-show
yt-synchro config-edit

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
- **Sandboxing:** `file_path` is validated on load and write; paths outside `output_dir` are rejected
- **Atomic writes:** state is written to a temp file and renamed into place

## Logging

- **Location:** `~/.config/yt-synchro/yt-synchro.log`
- **Rotation:** 10MB / 5 backups

## Dependencies

- `yt-dlp` - YouTube downloading (declared as a normal dependency)
- `rich` - Pretty terminal output
- `click` - CLI framework
- stdlib `tomllib` - Config parsing (Python 3.11+)
- `ffmpeg` - System binary used for embedding author metadata (warned about at launch if missing)

## Limits

All limits active simultaneously, first-hit-wins:

- `--max-storage` (e.g., 50GB) - disk space cap
- `--max-videos` (e.g., 20) - max videos on disk
- `--parallel` (e.g., 3) - max concurrent downloads

## Behavior

- **Failed downloads:** log error, skip, continue
- **Missing yt-dlp:** fails fast with a clear error; never installs at runtime
- **Missing ffmpeg:** warns at launch; metadata embedding is skipped for that run
- **Deletion:** eager cleanup every cycle (videos older than `video_max_age_days`)
- **Config missing:** auto-create with defaults
- **Invalid config values:** rejected before saving from the interactive editor

## Security & Hardening

- **Playlist URLs** are validated to HTTPS-only YouTube hosts. The validator uses `urlparse().hostname` and strips the literal `www.` prefix; `str.lstrip` must never be used for host normalization.
- **File paths** are sandboxed to `output_dir` on state load/save and final rename. Tampered paths are rejected with `ValueError`.
- **State writes** are atomic: written to a temp file and `os.replace()`'d into place under a lock.
- **Config serialization** uses `json.dumps()` for strings to guarantee TOML-safe escaping; hand-rolled quoting is not allowed.
- **Security regressions** are covered by the test suite. Run `uv run pytest` and `./scripts/lint.sh` before considering any security-adjacent change complete.

## Development

```bash
# Install dependencies and dev tools
uv sync --group dev

# Lint / format
./scripts/lint.sh

# Run
uv run yt-synchro --help
uv run python -m yt_synchro --help
```
