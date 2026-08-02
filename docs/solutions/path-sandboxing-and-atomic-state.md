# Path Sandboxing and Atomic State Writes

## Problem
The original code trusted paths that came from external metadata (`yt-dlp` JSON) and from the persisted `state.json` file. A malicious or tampered value could escape the configured output directory and overwrite or delete arbitrary files. Concurrent parallel downloads also rewrote `state.json` from multiple threads, creating a race condition that could corrupt the state file.

## Context
- `downloader.py` built final file paths from `video_id` and `ext` returned by `yt-dlp`.
- `cleanup.py` called `Path(oldest.file_path).unlink()` without verifying the path lived under `output_dir`.
- `state.py` wrote directly to `state.json`, and `downloader.py` called `_save()` from worker threads.

## Decision
Treat every file path as untrusted once it crosses a process boundary. Validate paths against the configured `output_dir` before any filesystem operation, and make all state file writes atomic and serialized.

## Solution
- Added `_sandbox()` validation in `state.py` that rejects any `file_path` whose resolved path is not inside `output_dir.resolve()`.
- Added `_sandbox_path()` in `downloader.py` for the final renamed output file.
- Changed `state.py` `_save()` to write to a temp file in the same directory and `os.replace()` it into place.
- Added a `threading.Lock` around `StateManager` reads and writes so parallel downloads serialize state access.
- Batched state updates in `download_playlist()`: worker threads return results, and the main thread updates state once after all futures complete.

## Verification
- Manual QA confirmed that `StateManager` rejects a path like `/etc/passwd` with `ValueError`.
- `scripts/lint.sh` passes after the changes.
- `yt-synchro status`, `list`, and `remove --help` all work on the real user state file.

## References
- `yt_synchro/state.py` (`_sandbox`, `_save`, `_lock`)
- `yt_synchro/downloader.py` (`_sandbox_path`, `download_playlist` result batching)
- `yt_synchro/cleanup.py` (`state.remove_video`)

## Date
2026-07-15
