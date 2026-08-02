# No Runtime Package Installation

## Problem
`downloader.py` contained `ensure_ytdlp()`, which silently ran `python -m pip install yt-dlp` at runtime if the import was missing. This bypassed the project's dependency declaration, could mutate the user's environment, and introduced a supply-chain risk (arbitrary PyPI install during normal app use).

## Context
The original `AGENTS.md` even documented "Missing yt-dlp: auto-install via pip" as expected behavior. The review flagged this as the highest-severity security issue because unexpected package installation is a privilege-escalation and supply-chain vector.

## Decision
Declare `yt-dlp` as a normal project dependency and fail fast with a clear error if it is missing. Never install packages while the app is running.

## Solution
- Removed `ensure_ytdlp()` and the runtime `subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])` call.
- Added `yt-dlp>=2024.1.0` to `project.dependencies` in `pyproject.toml`.
- Added `_require_ytdlp()` which imports `yt_dlp` and lets the natural `ModuleNotFoundError` surface if it is absent.
- Replaced bare `except Exception` around download/playlist operations with specific exceptions: `yt_dlp.utils.DownloadError`, `OSError`, and `ValueError`.

## Verification
- `uv sync` installs `yt-dlp` as a normal dependency.
- `yt-synchro --help` and `yt-synchro run --help` load without attempting any install.
- `scripts/lint.sh` passes.

## References
- `yt_synchro/downloader.py` (`_require_ytdlp`, `download_video`, `get_playlist_videos`)
- `pyproject.toml` (`project.dependencies`)

## Date
2026-07-15
