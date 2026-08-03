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
- **Deletion:** eager cleanup every cycle, in sequence: (1) age-based — videos older than `video_max_age_days`, (2) storage-based — oldest videos removed until under `max_storage_gb`, (3) count-based — oldest videos removed until at or under `max_videos`. All three use `StateManager.remove_video()` which sandbox-checks each path before unlinking.
- **Manual remove:** `yt-synchro remove <video-id>` unlinks the file and removes the state entry. The path is validated against `output_dir` on state load; no additional sandbox check at remove time.
- **Config missing:** auto-create with defaults
- **Invalid config values:** rejected before saving from the interactive editor

## Security & Hardening

- **Playlist URLs** are validated to HTTPS-only YouTube hosts. The validator uses `urlparse().hostname` and strips the literal `www.` prefix; `str.lstrip` must never be used for host normalization.
- **File paths** are sandboxed to `output_dir` on state load/save and final rename. Tampered paths are rejected with `ValueError`.
- **State writes** are atomic: written to a temp file and `os.replace()`'d into place under a lock.
- **Config serialization** uses `json.dumps()` for strings to guarantee TOML-safe escaping; hand-rolled quoting is not allowed.
- **Security regressions** are covered by the test suite. Run `uv run pytest` and `./scripts/lint.sh` before considering any security-adjacent change complete.

### Security Rules (invariants — do not break these)

1. **No `str.lstrip` / `str.rstrip` for host or prefix normalization.** These strip *characters*, not prefixes. Use `host.startswith("www.")` + slice (`host[4:]`) instead. The old `lstrip("www.")` bug let `wwyoutube.com` bypass the YouTube allowlist.
2. **All `subprocess.run` / `subprocess.Popen` calls must use list arguments, never `shell=True`.** This prevents shell injection via untrusted metadata (e.g., video titles or uploader names passed to ffmpeg).
3. **Never construct file paths from untrusted input without sandbox validation.** Call `_sandbox_path()` (`downloader.py`) or `_sandbox()` (`state.py`) before any filesystem operation on a path derived from yt-dlp metadata or user input.
4. **`Config.validate()` must be called before `Config.save()` in every code path that writes config.** This prevents persisting values that would crash future runs.
5. **State operations are not atomic across multiple calls.** If you need compound read-modify-write logic, either add a new method to `StateManager` that holds `_lock` for the duration, or document why the gap is acceptable.
6. **`StateManager.remove_video()` returns `False` for sandbox-rejected entries but marks them as `"removed"`.** This prevents infinite cleanup loops. Never bypass this by deleting the entry from `_videos` directly.
7. **Untrusted metadata (titles, uploaders, video IDs) must be escaped before Rich output.** Use `rich.markup.escape()` when embedding them in `console.print()`, `Progress` descriptions, or `Table` cells. Untrusted strings are also unsafe for log messages without newline/control-character sanitization.

## Development

### Useful Commands

```bash
# Install dependencies and dev tools
uv sync --group dev

# Lint / format
./scripts/lint.sh

# Run
uv run yt-synchro --help
uv run python -m yt_synchro --help

# Run security-critical tests
uv run pytest -v -k "lookalike or sandbox or atomic or escapes or malicious or persists"
```

### Architecture Decision Records

The `docs/solutions/` directory documents past security and design fixes. Consult these before modifying the affected modules:

| ADR | Covers |
|-----|--------|
| `security-review-follow-up.md` | URL validation, TOML escaping, test repairs, ffmpeg warning |
| `path-sandboxing-and-atomic-state.md` | Path validation, atomic writes, thread safety |
| `no-runtime-pip-install.md` | Why yt-dlp is a normal dependency (no runtime pip) |
| `config-falsy-values.md` | Config serialization, validation, falsy-value preservation |
| `cli-separation-of-concerns.md` | Module layout: cli / runner / display split |

### Security-Critical Tests

When modifying URL validation, path handling, state management, or config serialization, confirm these tests pass:

| Test | What it guards |
|------|----------------|
| `test_get_playlist_videos_rejects_lookalike_domains` | URL bypass via `lstrip` regression |
| `test_get_playlist_videos_rejects_non_youtube_url` | Non-YouTube URL rejection |
| `test_save_escapes_special_characters` | TOML round-trip for quotes/backslashes |
| `test_path_sandbox_rejects_escape` | Path traversal via state |
| `test_cleanup_sandbox_rejects_escape` | Cleanup won't delete outside output_dir |
| `test_atomic_save_keeps_previous_state_on_failure` | Atomic state writes survive disk errors |
| `test_cleanup_by_storage_persists_state` | Storage cleanup persists to disk |
| `test_cleanup_by_count_persists_state` | Count cleanup persists to disk |
| `test_download_video_sandboxes_malicious_id` | Download path stays inside output_dir |
