# Security Review Follow-up: URL Validation, Config Serialization, and Test Coverage

## Problem

A security review of the codebase identified a cluster of correctness issues that all weakened the same defensive intent: keep untrusted input from escaping the tool's intended boundaries. The highest-severity finding was a bypass in the YouTube URL allowlist, and the most damaging latent bug was a broken regression-test suite that was supposed to catch sandbox violations.

## Context

- `downloader.py` validated playlist URLs with `netloc.lower().lstrip("www.")`, a classic Python pitfall: `lstrip` strips *characters*, not the prefix. This let attacker-registerable domains such as `wwyoutube.com` and `wwwyoutu.be` pass as YouTube.
- `config.py` serialized strings with `f'"{value}"'`, so quotes, backslashes, and newlines in user-edited values could corrupt `config.toml` or inject extra keys.
- `display.py` saved the config after editing without calling `config.validate()`, allowing invalid values to persist and crash future runs.
- `tests/test_downloader.py` and `tests/test_cleanup.py` had signature/expectation bugs that prevented the very sandbox tests they were supposed to run from running at all.
- `StateManager.remove_video()` did not persist the "removed" status for sandbox-rejected entries, causing the cleanup loop to re-process them forever.

## Decision

Fix the validation primitives, make serialization robust, validate before saving, and ensure the security tests actually exercise the protections.

## Solution

- URL validation (`downloader.py`):
  - Use `urlparse(url).hostname` instead of `.netloc`.
  - Strip the literal prefix `www.` with `host.startswith("www.")` and `host = host[4:]` instead of `lstrip("www.")`.
  - Added regression tests for lookalike domains: `wwyoutube.com`, `wwwyoutube.com`, `wwwyoutu.be`, `youtube.com.evil.com`, and trailing-dot `www.youtube.com.`.
- Config serialization (`config.py`):
  - Replaced the hand-rolled `f'"{value}"'` with `json.dumps(value)` for strings, which gives correct TOML-compatible escaping.
  - Added a round-trip test with quotes, backslashes, and newlines.
- Config editing (`display.py`):
  - `edit_config()` now calls `config.validate()` before `config.save()` and refuses to save invalid values.
- Test repairs (`tests/test_downloader.py`, `tests/test_cleanup.py`):
  - Removed the non-existent `state=` keyword from `download_video` calls in tests.
  - Changed the cleanup-sandbox test to assert that `StateManager.add()` raises `ValueError` for an escaping path, matching the real security boundary.
- Cleanup infinite loop (`state.py`):
  - `remove_video()` marks sandbox-rejected entries as removed and persists state immediately so they are skipped on subsequent cleanup passes.

## Additional Hardening

- `cli.py` now checks `shutil.which("ffmpeg")` at launch and logs a warning if the binary is missing. Metadata embedding will still be skipped at runtime, but users are told up front.
- `scripts/lint.sh` was fixed to reference the real package directories (`yt_synchro/` and `tests/`) instead of the non-existent `yt-synchro/`.

## Verification

- `uv run pytest` passes with 24 tests.
- `scripts/lint.sh` passes.
- New regression tests specifically target the URL lookalike bypass and the TOML special-character round-trip.

## References

- `yt_synchro/downloader.py` (`_validate_playlist_url`, `download_video`)
- `yt_synchro/config.py` (`toml_repr`, `validate`, `save`)
- `yt_synchro/display.py` (`edit_config`)
- `yt_synchro/state.py` (`remove_video`, `add`, `_sandbox`)
- `yt_synchro/cli.py` (`main`)
- `tests/test_downloader.py`, `tests/test_cleanup.py`, `tests/test_config.py`, `tests/test_cli.py`
- `scripts/lint.sh`

## Date

2026-08-03
